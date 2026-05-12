"""
nfa_parser_ai.py
════════════════
Parser semântico de NFA-e SEFAZ-GO com fallback para Claude API.

Estratégia híbrida (custo-eficiente):
  1. PyMuPDF  → extração de texto bruto (rápido, gratuito)
  2. Regex    → parse estruturado (≈ 90% das notas)
  3. Claude   → fallback para blocos ambíguos (tool_use, structured output)

Modelos recomendados:
  • claude-haiku-4-5  → produção (barato, rápido — ~$0.003/1k tokens input)
  • claude-sonnet-4-6 → alta-precisão (notas complexas / auditoria forense)

Fluxo:
  extrair_pdf()
    ├─ _extrair_texto_pymupdf()    ← PyMuPDF, por página
    ├─ _split_blocos()             ← divide por "IDENTIFICAÇÃO DA NOTA"
    ├─ _parse_bloco_regex()        ← tenta regex em cada bloco
    │    └─ confiança >= LIMIAR_CONFIANCA → aceito
    ├─ _parse_lote_claude()        ← envia os reprovados em batch
    │    └─ tool_use → NFAExtraida[]
    └─ ResultadoExtracaoPDF
"""

from __future__ import annotations

import logging
import os
import re
import time
from decimal import Decimal
from pathlib import Path

import fitz  # PyMuPDF

from .nfa_ai_schemas import (
    TOOL_EXTRAIR_NOTAS,
    NFAExtraida,
    ParteAI,
    ProdutoAI,
    ResultadoExtracaoPDF,
)

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────

# Confiança mínima para aceitar resultado do regex (0–1)
LIMIAR_CONFIANCA: float = 0.70

# Máximo de blocos por chamada Claude (context window ≈ 4k tokens por bloco)
MAX_BLOCOS_POR_CHAMADA: int = 20

# Padrão de separação de notas no PDF GIEF
RE_SEPARADOR = re.compile(r"IDENTIFICA.{1,3}O DA NOTA", re.IGNORECASE)

# Padrão do cabeçalho de cada nota: número  data  natureza
RE_CABECALHO_NOTA = re.compile(
    r"(\d{6,10})\s+(\d{2}/\d{2}/\d{4})\s+(.+?)(?:\n|REMETENTE|$)",
    re.IGNORECASE,
)

# Chave de acesso (44 dígitos)
RE_CHAVE = re.compile(r"\b(\d{44})\b")

# CPF (11 dígitos) ou CNPJ (14 dígitos) — sem máscara ou com
RE_DOC = re.compile(
    r"(\d{2,3}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{0,4}-?\d{2}|\d{11}|\d{14})"
)

# Valor monetário BR: 1.234,56 ou 1234,56 ou 1234.56
RE_VALOR = re.compile(
    r"(?<!\d)(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+\.\d{2})(?!\d)"
)

# Mapeamento de natureza → enum
_NATUREZA_MAP: dict[str, str] = {
    "VENDA":          "VENDA",
    "REMESSA/LEILAO": "LEILAO",
    "REMESSA LEILAO": "LEILAO",
    "LEILAO":         "LEILAO",
    "REMESSA":        "REMESSA",
    "OUTRA REMESSA":  "REMESSA",
    "OUTRAS REMESSAS":"REMESSA",
    "OUTRA REMESSAS": "REMESSA",
    "TRANSFERENCIA":  "TRANSFERENCIA",
    "TRANSFERÊNCIA":  "TRANSFERENCIA",
    "COMPRA":         "COMPRA",
}


def _normalizar_natureza(raw: str) -> str:
    s = raw.strip().upper()
    for k, v in _NATUREZA_MAP.items():
        if k in s:
            return v
    return "OUTRAS"


def _limpar_doc(doc: str | None) -> str:
    return re.sub(r"\D", "", str(doc or ""))


def _parse_valor_br(s: str) -> Decimal:
    """Converte '1.234,56' ou '1234.56' → Decimal."""
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0")


# ─── Extração de texto com PyMuPDF ──────────────────────────────────────────

def _extrair_texto_pymupdf(caminho: str | Path) -> tuple[str, str, str]:
    """
    Extrai texto completo do PDF GIEF com PyMuPDF.

    Retorna:
        (texto_completo, nome_produtor, cpf_produtor)
    """
    doc = fitz.open(str(caminho))
    texto_completo = ""
    nome_produtor = ""
    cpf_produtor  = ""

    for page in doc:
        page_text = page.get_text("text", sort=True)
        texto_completo += page_text + "\n"

    doc.close()

    # Identifica contribuinte no cabeçalho (primeiras 2000 chars)
    cabecalho = texto_completo[:2000]

    # CPF: padrão XXX.XXX.XXX-XX (pode ter espaços no PDF escaneado)
    m_cpf = re.search(r"(\d{3}[. ]\d{3}[. ]\d{3}[-. ]\d{2})", cabecalho)
    if m_cpf:
        cpf_produtor = _limpar_doc(m_cpf.group(1))

    # Nome: linha após "NOME OU RAZ" ou imediatamente antes do CPF
    m_nome = re.search(
        r"(?:NOME OU RAZ[^\n]*\n\s*)([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{5,60})",
        cabecalho, re.IGNORECASE
    )
    if not m_nome:
        # Fallback: linha que tem muitas maiúsculas e contém nome comum de produtor
        m_nome = re.search(
            r"\n([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{10,60})\n",
            cabecalho
        )
    if m_nome:
        nome_produtor = m_nome.group(1).strip()

    return texto_completo, nome_produtor, cpf_produtor


# ─── Split em blocos de nota ─────────────────────────────────────────────────

def _split_blocos(texto: str) -> list[str]:
    """Divide o texto completo em blocos, um por NFA-e."""
    blocos = RE_SEPARADOR.split(texto)
    return [b.strip() for b in blocos[1:] if b.strip()]  # descarta cabeçalho


# ─── Parser de linha de parte GIEF ──────────────────────────────────────────
# Formato GIEF: NOME    IE    CPF/CNPJ    MUNICÍPIO (colunas separadas por 2+ espaços)

# CPF com máscara: XXX.XXX.XXX-XX
_RE_CPF_MASK  = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
# CNPJ com máscara: XX.XXX.XXX/XXXX-XX
_RE_CNPJ_MASK = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
# IE: sequência de dígitos com 6–12 chars (entre espaços duplos)
_RE_IE        = re.compile(r"(?<!\d)(\d{6,12})(?!\d)")


def _parse_parte_linha(linha: str) -> tuple[ParteAI, float]:
    """
    Analisa uma linha de dados de Parte no formato GIEF:
      NOME    IE    CPF/CNPJ    MUNICÍPIO

    Retorna (ParteAI, confiança).
    """
    if not linha.strip():
        return ParteAI(), 0.0

    parte = ParteAI()
    conf  = 1.0

    # 1) Localiza CPF ou CNPJ (padrão mais fácil de achar)
    m_cpf  = _RE_CPF_MASK.search(linha)
    m_cnpj = _RE_CNPJ_MASK.search(linha)
    m_doc  = m_cpf or m_cnpj

    if m_doc:
        parte.cpf_cnpj = _limpar_doc(m_doc.group(0))
        antes  = linha[:m_doc.start()].strip()
        depois = linha[m_doc.end():].strip()

        # 2) Separa nome de IE em "antes" (IE = último token todo-dígitos)
        tokens = re.split(r"\s{2,}", antes)
        if tokens:
            ultimo = tokens[-1].strip()
            if re.match(r"^\d{6,12}$", ultimo):
                parte.ie   = ultimo
                parte.nome = " ".join(tokens[:-1]).strip()
            else:
                parte.nome = " ".join(tokens).strip()

        # 3) Município = primeiro token em "depois" (antes do próximo campo)
        mun_tokens = depois.split()
        if mun_tokens:
            parte.municipio = mun_tokens[0]
    else:
        # CPF/CNPJ não encontrado — tenta CPF só com dígitos (11 ou 14)
        m_dig = re.search(r"\b(\d{11}|\d{14})\b", linha)
        if m_dig:
            parte.cpf_cnpj = m_dig.group(1)
            parte.nome     = linha[:m_dig.start()].strip()
        else:
            # Sem doc — extrai só o nome (primeira "palavra" longa)
            parte.nome = linha.strip().split("  ")[0].strip()
            conf -= 0.3

    if not parte.nome:
        conf -= 0.2

    return parte, conf


# ─── Parser de linha de produto GIEF ────────────────────────────────────────
# Formato: CODIGO   DESCRIÇÃO   QTD   VLR_ICMS   VLR_UNIT   VLR_TOTAL
# Exemplo: 1070  GADO BOVINO ...  14,00  R$ 0,00  2394,9700  R$ 33.529,58

_RE_PRODUTO_LINHA = re.compile(
    r"^\s*(\d{3,6})"                        # código (3–6 dígitos)
    r"\s{2,}(.+?)\s{2,}"                   # descrição (2+ espaços de cada lado)
    r"(\d+[.,]\d{2,4})"                    # quantidade
    r"\s+R\$\s*([\d.,]+)"                  # vlr ICMS
    r"\s+([\d.,]+)"                        # vlr unitário
    r"\s+R\$\s*([\d.,]+)",                 # vlr total
    re.IGNORECASE,
)

# Valor "R$ XX.XXX,XX" no final da linha (para soma manual de produtos)
_RE_VLR_TOTAL_ITEM = re.compile(r"R\$\s*([\d.]+,\d{2})\s*$")


def _parse_produtos_bloco(bloco: str) -> list[ProdutoAI]:
    """Extrai produtos do bloco. Só lê linhas após o cabeçalho 'Código  Descrição'."""
    produtos: list[ProdutoAI] = []
    # Localiza início da seção de produtos
    m_header = re.search(
        r"C.{1,3}digo\s+Descri.{1,3}o.+?Quantidade.+?Vlr\.\s*Total",
        bloco, re.IGNORECASE
    )
    if not m_header:
        return produtos

    linhas_prod = bloco[m_header.end():].split("\n")
    for linha in linhas_prod:
        if not linha.strip():
            continue
        m = _RE_PRODUTO_LINHA.match(linha)
        if m:
            produtos.append(ProdutoAI(
                codigo       = m.group(1),
                descricao    = m.group(2).strip(),
                quantidade   = float(m.group(3).replace(",", ".")),
                vlr_icms     = float(_parse_valor_br(m.group(4))),
                vlr_unitario = float(_parse_valor_br(m.group(5))),
                vlr_total    = float(_parse_valor_br(m.group(6))),
            ))

    return produtos


# ─── Parser Regex (rápido) — formato GIEF ────────────────────────────────────

def _parse_bloco_regex(bloco: str) -> tuple[NFAExtraida | None, float]:
    """
    Extrai uma NFA-e de um bloco GIEF via regex otimizado para o formato real.

    Estrutura do bloco GIEF (PyMuPDF):
      [vazio]
      CHAVE DE ACESSO
      <44 dígitos>
      NÚMERO DA NFA    EMISSÃO    NATUREZA
      <número>         DD/MM/YYYY <natureza>
      Local de Emissão
      <local>
      REMETENTE        INSCRIÇÃO ESTADUAL    CNPJ/CPF    MUNICÍPIO
      <nome>  <IE>  <cpf/cnpj>  <município>     ← dados na PRÓXIMA linha
      DESTINATÁRIO     INSCRIÇÃO ESTADUAL    CNPJ/CPF    MUNICÍPIO
      <nome>  <IE>  <cpf/cnpj>  <município>     ← dados na PRÓXIMA linha
      TRANSPORTADOR    ...
      [vazio]
      Descrição dos Produtos
      Código  Descrição  Quantidade  Vlr.ICMS  Vlr.Unitário  Vlr.Total
      <produto1>
      <produto2>

    Retorna (nota, confiança). confiança < LIMIAR_CONFIANCA → manda para Claude.
    """
    linhas = bloco.split("\n")
    confianca = 1.0
    nota = NFAExtraida()

    # ── Chave de acesso (linha inteira de 44 dígitos) ────────────────────────
    m_chave = RE_CHAVE.search(bloco)
    if m_chave:
        nota.chave_acesso = m_chave.group(1)
    else:
        confianca -= 0.05

    # ── Número, data e natureza ───────────────────────────────────────────────
    # Padrão: "24925316    19/02/2025    REMESSA/LEILAO"
    m_cab = RE_CABECALHO_NOTA.search(bloco)
    if not m_cab:
        return None, 0.0

    nota.numero  = m_cab.group(1).strip()
    nota.emissao = m_cab.group(2).strip()
    nota.natureza = _normalizar_natureza(m_cab.group(3))  # type: ignore[assignment]

    # ── Partes (REMETENTE e DESTINATÁRIO) ────────────────────────────────────
    # O header "REMETENTE  INSCRIÇÃO ESTADUAL  CNPJ/CPF  MUNICÍPIO" fica em uma linha.
    # A PRÓXIMA linha não-vazia contém os dados reais.
    def _extrair_linha_apos(marcador: str) -> str:
        """Retorna a primeira linha não-vazia após a linha que contém `marcador`."""
        for i, linha in enumerate(linhas):
            if re.search(marcador, linha, re.IGNORECASE):
                for j in range(i + 1, min(i + 4, len(linhas))):
                    candidata = linhas[j].strip()
                    if candidata and not re.search(
                        r"INSCRI|CNPJ/CPF|MUNIC|TRANSPOR|DESTINAT|^Local de",
                        candidata, re.IGNORECASE
                    ):
                        return candidata
        return ""

    linha_rem  = _extrair_linha_apos(r"^\s*REMETENTE\b")
    linha_dest = _extrair_linha_apos(r"^\s*DESTINAT")

    remetente,    c_rem  = _parse_parte_linha(linha_rem)
    destinatario, c_dest = _parse_parte_linha(linha_dest)

    nota.remetente    = remetente
    nota.destinatario = destinatario

    if c_rem < 0.5:
        confianca -= 0.2
    if c_dest < 0.5:
        confianca -= 0.2

    # ── Produtos ─────────────────────────────────────────────────────────────
    nota.produtos = _parse_produtos_bloco(bloco)

    # ── Valor total = soma dos produtos ──────────────────────────────────────
    if nota.produtos:
        nota.valor_total = Decimal(str(sum(p.vlr_total for p in nota.produtos))).quantize(
            Decimal("0.01")
        )
        nota.valor_icms = Decimal(str(sum(p.vlr_icms for p in nota.produtos))).quantize(
            Decimal("0.01")
        )
    else:
        # Fallback: "R$ XX.XXX,XX" no final do bloco (último valor encontrado)
        matches_vt = _RE_VLR_TOTAL_ITEM.findall(bloco)
        if matches_vt:
            nota.valor_total = _parse_valor_br(matches_vt[-1])
            confianca -= 0.05
        else:
            confianca -= 0.20

    nota.confianca       = round(max(0.0, min(1.0, confianca)), 3)
    nota.origem_extracao = "regex"
    return nota, nota.confianca


# ─── Parser Claude (fallback semântico) ──────────────────────────────────────

def _parse_lote_claude(
    blocos: list[str],
    client,  # anthropic.Anthropic
    modelo: str,
) -> tuple[list[NFAExtraida], int, int]:
    """
    Envia lote de blocos para Claude via tool_use.

    Retorna:
        (notas_extraidas, tokens_input, tokens_output)
    """
    if not blocos:
        return [], 0, 0

    # Monta prompt com todos os blocos numerados
    blocos_txt = "\n\n---NOTA---\n".join(
        f"[BLOCO {i+1}]\n{b[:1500]}"  # limita por bloco para caber no context
        for i, b in enumerate(blocos)
    )

    prompt = (
        "Analise os blocos de texto abaixo, cada um representando uma "
        "Nota Fiscal Avulsa Eletrônica (NFA-e) do SEFAZ-GO. "
        "Extraia os dados de TODAS as notas usando a ferramenta extrair_notas_nfa. "
        "Para a natureza: 'REMESSA/LEILAO' → LEILAO, "
        "'OUTRA REMESSAS' → REMESSA, 'TRANSFERÊNCIA' → TRANSFERENCIA. "
        "Use EXATAMENTE os valores do texto; não invente dados.\n\n"
        f"{blocos_txt}"
    )

    t0 = time.monotonic()
    resp = client.messages.create(
        model=modelo,
        max_tokens=4096,
        tools=[TOOL_EXTRAIR_NOTAS],
        tool_choice={"type": "tool", "name": "extrair_notas_nfa"},
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.monotonic() - t0
    logger.info(
        "Claude [%s] lote=%d blocos em %.1fs | in=%d out=%d tokens",
        modelo, len(blocos), elapsed,
        resp.usage.input_tokens, resp.usage.output_tokens,
    )

    notas: list[NFAExtraida] = []
    for block in resp.content:
        if block.type != "tool_use":
            continue
        raw_notas = block.input.get("notas", [])
        for r in raw_notas:
            try:
                nota = NFAExtraida(
                    numero        = str(r.get("numero", "")),
                    emissao       = str(r.get("emissao", "")),
                    natureza      = r.get("natureza", "OUTRAS"),
                    valor_total   = r.get("valor_total", 0),
                    valor_icms    = r.get("valor_icms", 0),
                    chave_acesso  = str(r.get("chave_acesso", "")),
                    remetente     = ParteAI(
                        nome      = str(r.get("remetente_nome", "")),
                        cpf_cnpj  = _limpar_doc(r.get("remetente_cpf_cnpj", "")),
                        municipio = str(r.get("remetente_municipio", "")),
                        ie        = str(r.get("remetente_ie", "")),
                    ),
                    destinatario  = ParteAI(
                        nome      = str(r.get("destinatario_nome", "")),
                        cpf_cnpj  = _limpar_doc(r.get("destinatario_cpf_cnpj", "")),
                        municipio = str(r.get("destinatario_municipio", "")),
                    ),
                    produtos      = [
                        ProdutoAI(
                            codigo       = str(p.get("codigo", "")),
                            descricao    = str(p.get("descricao", "")),
                            quantidade   = float(p.get("quantidade", 0)),
                            vlr_unitario = float(p.get("vlr_unitario", 0)),
                            vlr_total    = float(p.get("vlr_total", 0)),
                            vlr_icms     = float(p.get("vlr_icms", 0)),
                        )
                        for p in r.get("produtos", [])
                    ],
                    confianca        = 0.85,   # Claude processou
                    origem_extracao  = "claude",
                )
                notas.append(nota)
            except Exception as e:
                logger.warning("Nota Claude inválida ignorada: %s — %s", r, e)

    return notas, resp.usage.input_tokens, resp.usage.output_tokens


# ─── Deduplicação ────────────────────────────────────────────────────────────

def _deduplicar(notas: list[NFAExtraida]) -> list[NFAExtraida]:
    """
    Remove duplicatas por chave_acesso (prioridade) ou número+data.
    Quando duplicada, mantém a de maior confiança.
    """
    visto: dict[str, NFAExtraida] = {}
    for nota in notas:
        chave = nota.chave_acesso or f"{nota.numero}_{nota.emissao}"
        if not chave:
            visto[id(nota)] = nota  # sem chave: aceita todas
            continue
        existente = visto.get(chave)
        if existente is None or nota.confianca > existente.confianca:
            visto[chave] = nota
    return list(visto.values())


# ─── API pública ─────────────────────────────────────────────────────────────

class NFAParserAI:
    """
    Parser semântico híbrido de NFA-e GIEF/SEFAZ-GO.

    Exemplo:
        parser = NFAParserAI()   # usa ANTHROPIC_API_KEY do env
        resultado = parser.extrair_pdf("GENIS REM.pdf")
        print(resultado.total_extraidas)  # 175
    """

    def __init__(
        self,
        api_key:  str | None = None,
        modelo:   str = "claude-haiku-4-5-20251001",
        limiar:   float = LIMIAR_CONFIANCA,
        max_claude: int = MAX_BLOCOS_POR_CHAMADA,
    ):
        self.modelo    = modelo
        self.limiar    = limiar
        self.max_blocos = max_claude
        self._client   = None
        self._api_key  = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def client(self):
        """Lazy init do cliente Anthropic (não instancia se só regex for usado)."""
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def extrair_pdf(
        self,
        caminho_pdf:  str | Path,
        usar_claude:  bool = True,
        max_erros:    int  = 10,
    ) -> ResultadoExtracaoPDF:
        """
        Extrai todas as NFA-e de um PDF GIEF/SEFAZ-GO.

        Args:
            caminho_pdf: Caminho para o PDF GIEF.
            usar_claude: Se False, usa apenas regex (mais rápido, menos preciso).
            max_erros:   Número máximo de erros tolerados antes de abortar.

        Returns:
            ResultadoExtracaoPDF com todas as notas e estatísticas.
        """
        caminho_pdf = Path(caminho_pdf)
        logger.info("Iniciando extração: %s", caminho_pdf.name)

        resultado = ResultadoExtracaoPDF(notas=[])
        erros: list[str] = []
        tokens_in = tokens_out = 0

        # ── 1. Extração de texto ────────────────────────────────────────────
        try:
            texto, resultado.nome_produtor, resultado.cpf_produtor = \
                _extrair_texto_pymupdf(caminho_pdf)
        except Exception as e:
            resultado.erros.append(f"PyMuPDF falhou: {e}")
            return resultado

        # ── 2. Split em blocos ──────────────────────────────────────────────
        blocos = _split_blocos(texto)
        logger.info("%d blocos encontrados", len(blocos))

        if not blocos:
            resultado.erros.append("Nenhum bloco IDENTIFICAÇÃO DA NOTA encontrado.")
            return resultado

        # ── 3. Regex pass ───────────────────────────────────────────────────
        notas_ok:     list[NFAExtraida] = []
        blocos_falhos: list[str]        = []

        for i, bloco in enumerate(blocos):
            try:
                nota, confianca = _parse_bloco_regex(bloco)
                if nota is not None and confianca >= self.limiar:
                    notas_ok.append(nota)
                elif nota is not None:
                    # Regex extraiu algo mas confiança baixa → manda para Claude
                    blocos_falhos.append(bloco)
                    logger.debug("Bloco %d confiança %.2f < %.2f → Claude", i, confianca, self.limiar)
                else:
                    blocos_falhos.append(bloco)
            except Exception as e:
                erros.append(f"Bloco {i}: {e}")
                if usar_claude:
                    blocos_falhos.append(bloco)
                if len(erros) >= max_erros:
                    logger.error("Muitos erros (%d), abortando.", len(erros))
                    break

        logger.info(
            "Regex: %d OK / %d para Claude / %d erros",
            len(notas_ok), len(blocos_falhos), len(erros)
        )

        # ── 4. Claude pass (lotes) ──────────────────────────────────────────
        notas_claude: list[NFAExtraida] = []
        if usar_claude and blocos_falhos and self._api_key:
            for i in range(0, len(blocos_falhos), self.max_blocos):
                lote = blocos_falhos[i: i + self.max_blocos]
                try:
                    notas_lote, t_in, t_out = _parse_lote_claude(lote, self.client, self.modelo)
                    notas_claude.extend(notas_lote)
                    tokens_in  += t_in
                    tokens_out += t_out
                except Exception as e:
                    erros.append(f"Claude lote {i//self.max_blocos}: {e}")
                    logger.error("Erro no lote Claude: %s", e)

        # ── 5. Merge + deduplicação ─────────────────────────────────────────
        todas = notas_ok + notas_claude
        todas = _deduplicar(todas)

        # ── 6. Ordena por data de emissão ───────────────────────────────────
        from datetime import datetime
        def _sort_key(n: NFAExtraida):
            try:
                return datetime.strptime(n.emissao, "%d/%m/%Y")
            except ValueError:
                return datetime.min

        todas.sort(key=_sort_key)

        # Calcula totais explicitamente (model_validator roda no __init__ com notas=[])
        resultado.notas          = todas
        resultado.total_extraidas = len(todas)
        resultado.por_regex      = sum(1 for n in todas if n.origem_extracao == "regex")
        resultado.por_claude     = sum(1 for n in todas if "claude" in n.origem_extracao)
        resultado.descartadas    = len(blocos) - len(todas)
        resultado.erros          = erros
        resultado.tokens_input   = tokens_in
        resultado.tokens_output  = tokens_out

        # Período
        from datetime import datetime as _dt
        _datas = []
        for n in todas:
            try:
                _datas.append(_dt.strptime(n.emissao, "%d/%m/%Y"))
            except ValueError:
                pass
        if _datas:
            resultado.periodo_inicio = min(_datas).strftime("%d/%m/%Y")
            resultado.periodo_fim    = max(_datas).strftime("%d/%m/%Y")

        logger.info(
            "Extração concluída: %d notas | %d regex | %d claude | "
            "%d descartadas | tokens in=%d out=%d",
            len(todas),
            sum(1 for n in todas if n.origem_extracao == "regex"),
            sum(1 for n in todas if "claude" in n.origem_extracao),
            resultado.descartadas,
            tokens_in, tokens_out,
        )
        return resultado

    def extrair_multiplos(
        self,
        caminhos: list[str | Path],
        usar_claude: bool = True,
    ) -> ResultadoExtracaoPDF:
        """
        Extrai NFA-e de múltiplos PDFs (ex: REM + DEST) e faz merge com deduplicação.
        """
        todas_notas: list[NFAExtraida] = []
        nome = cpf = ""
        t_in = t_out = 0
        todos_erros: list[str] = []

        for caminho in caminhos:
            r = self.extrair_pdf(caminho, usar_claude=usar_claude)
            todas_notas.extend(r.notas)
            if r.nome_produtor and not nome:
                nome = r.nome_produtor
            if r.cpf_produtor and not cpf:
                cpf = r.cpf_produtor
            t_in  += r.tokens_input
            t_out += r.tokens_output
            todos_erros.extend(r.erros)

        todas_notas = _deduplicar(todas_notas)

        resultado = ResultadoExtracaoPDF(notas=todas_notas)
        resultado.nome_produtor = nome
        resultado.cpf_produtor  = cpf
        resultado.tokens_input  = t_in
        resultado.tokens_output = t_out
        resultado.erros         = todos_erros
        return resultado
