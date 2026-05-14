import re
import pdfplumber
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from .constants import REGEX

logger = logging.getLogger('NFA_Extractor')

# --- MODELS (Pydantic V2) ---

class Parte(BaseModel):
        nome: str = ""
        ie: Optional[str] = None
        cpf_cnpj: Optional[str] = None
        municipio: Optional[str] = None

class Produto(BaseModel):
        codigo: str = ""
        descricao: str = ""
        quantidade: float = 0.0
        vlr_icms: float = 0.0
        vlr_unitario: float = 0.0
        vlr_total: float = 0.0

class NFA(BaseModel):
        numero: str = ""
        natureza: str = "OUTRAS"
        emissao: str = ""
        valor_total: float = 0.0
        valor_icms: float = 0.0
        quantidade_total: float = 0.0
        # P1-B: campo cabecas adicionado — ausencia causava distorcao silenciosa no XGBoost
        # xgboost_scorer.py usa n.get("cabecas", 0) — sem este campo, score era sempre 0
        cabecas: float = 0.0
        chave_acesso: Optional[str] = None
        local_emissao: Optional[str] = None
        cfop: Optional[str] = None  # P1-B: CFOP adicionado para feature de consistencia_cfop no XGBoost
        destinatario_cpf: Optional[str] = None  # P1-B: alias para xgboost_scorer (proporcao_pf, concentracao_dest)
        regra_aplicada: Optional[str] = None  # rastreabilidade RE-1

    remetente: Parte = Field(default_factory=Parte)
    destinatario: Parte = Field(default_factory=Parte)
    transportador: Parte = Field(default_factory=Parte)
    produtos: List[Produto] = Field(default_factory=list)

    # Confidence score da extracao (0.0-1.0) — usado pelo ExtractionOrchestrator
    confidence_score: float = 1.0

    @field_validator("valor_total", "valor_icms", mode="before")
    @classmethod
    def parse_currency(cls, v: Any) -> float:
                if isinstance(v, str):
                                v = v.replace("R$", "").replace(".", "").replace(",", ".").strip()
                                try: return float(v)
                                                except: return 0.0
                                                            return float(v or 0.0)

            @field_validator("cabecas", "quantidade_total", mode="before")
    @classmethod
    def parse_quantity(cls, v: Any) -> float:
                if isinstance(v, str):
                                v = v.replace(".", "").replace(",", ".").strip()
                                try: return float(v)
                                                except: return 0.0
                                                            return float(v or 0.0)

            def sync_destinatario_cpf(self) -> None:
                        """Sincroniza destinatario_cpf a partir do destinatario.cpf_cnpj para uso no XGBoost."""
                        if self.destinatario and self.destinatario.cpf_cnpj:
                                        object.__setattr__(self, 'destinatario_cpf', self.destinatario.cpf_cnpj)

                # --- LOGIC ---

# P1-B: mapa de natureza expandido para alinhar com nfa_parser_ai.py (8+ naturezas vs 3 anteriores)
_NATUREZA_MAP: dict[str, str] = {
        "VENDA": "VENDA",
        "REMESSA/LEILAO": "LEILAO",
        "REMESSA LEILAO": "LEILAO",
        "LEILAO": "LEILAO",
        "REMESSA": "REMESSA",
        "OUTRA REMESSA": "REMESSA",
        "OUTRAS REMESSAS": "REMESSA",
        "TRANSFERENCIA": "TRANSFERENCIA",
        "TRANSFERÊNCIA": "TRANSFERENCIA",
        "COMPRA": "COMPRA",
        "DEVOLUCAO": "DEVOLUCAO",
        "DEVOLUÇÃO": "DEVOLUCAO",
}

def classificar_natureza(natureza: str) -> str:
        """Classifica natureza da NFA — alinhado com nfa_parser_ai._normalizar_natureza."""
        s = natureza.upper().strip()
        for k, v in _NATUREZA_MAP.items():
                    if k in s:
                                    return v
                            return "OUTRAS"

def _calcular_confidence(nfa: NFA) -> float:
        """
            Calcula score de confianca da extracao (0.0-1.0).
                Usado pelo ExtractionOrchestrator para decidir se aciona parser AI.
                    Criterios: presenca de campos criticos.
                        """
    score = 0.0
    if nfa.numero: score += 0.20
            if nfa.emissao: score += 0.15
                    if nfa.natureza and nfa.natureza != "OUTRAS": score += 0.10
                            if nfa.chave_acesso and len(nfa.chave_acesso) == 44: score += 0.20
                                    if nfa.valor_total > 0: score += 0.15
                                            if nfa.remetente.cpf_cnpj: score += 0.10
                                                    if nfa.destinatario.cpf_cnpj: score += 0.10
                                                            if nfa.produtos: score += 0.10
                                                                    # cabecas: bonus se presente e coerente com quantidade_total
    if nfa.cabecas > 0 or nfa.quantidade_total > 0: score = min(score + 0.05, 1.0)
            return round(score, 2)

def extrair_notas(caminho_pdf: str) -> tuple[List[NFA], str, str]:
        """Extrai notas fiscais do PDF usando os padroes de constants.py.

            Retorna: (lista_de_nfas, nome_produtor, cpf_produtor)
                Cada NFA agora inclui:
                    - cabecas: quantidade de animais (P1-B — corrige distorcao silenciosa no XGBoost)
                        - destinatario_cpf: alias para xgboost_scorer
                            - cfop: codigo fiscal de operacoes (feature consistencia_cfop)
                                - confidence_score: 0.0-1.0 para uso pelo ExtractionOrchestrator
                                    """
    notas = []
    nome_produtor = ""
    cpf_produtor = ""

    try:
                with pdfplumber.open(caminho_pdf) as pdf:
                                texto_completo = ""
                                for page in pdf.pages:
                                                    texto_completo += page.extract_text() + "\n"

                                # Identificacao do Produtor (Contribuinte)
                                match_nome = re.search(r"CONTRIBUINTE:\s*(.*)", texto_completo, re.IGNORECASE)
            if match_nome:
                                nome_produtor = match_nome.group(1).split("CPF/CNPJ")[0].strip()

            match_cpf = REGEX['cpf_ou_cnpj'].search(texto_completo)
            if match_cpf:
                                cpf_produtor = match_cpf.group(1)

            # Divisao por notas (cada nota comeca com IDENTIFICACAO DA NOTA)
            pattern_id = re.compile(r'IDENTIFICA.{1,3}O DA NOTA', re.IGNORECASE)
            blocos = pattern_id.split(texto_completo)

            for bloco in blocos[1:]:
                                try:
                                                        nfa = NFA()

                                    # Numero, Data e Natureza
                                                        m_num = re.search(r'(\d{6,10})\s+(\d{2}/\d{2}/\d{4})\s+(.+)', bloco)
                                                        if m_num:
                                                                                    nfa.numero = m_num.group(1)
                                                                                    nfa.emissao = m_num.group(2)
                                                                                    nfa.natureza = classificar_natureza(m_num.group(3))

                                                        # Chave de Acesso (44 digitos)
                                                        m_chave = re.search(r'\b(\d{44})\b', bloco)
                                                        if m_chave:
                                                                                    nfa.chave_acesso = m_chave.group(0)

                                                        # CFOP — P1-B: extraido para feature consistencia_cfop do XGBoost
                                                        m_cfop = re.search(r'\bCFOP[:\s]*(\d{4})\b', bloco, re.IGNORECASE)
                                                        if m_cfop:
                                                                                    nfa.cfop = m_cfop.group(1)

                                                        # Partes (Remetente, Destinatario, Transportador)
                                                        def extrair_parte_flex(termo_inicio: str, proximo_bloco: str, texto: str) -> Parte:
                                                                                    match_start = re.search(termo_inicio, texto, re.IGNORECASE)
                                                                                    if not match_start:
                                                                                                                    return Parte()
                                                                                                                sub = texto[match_start.end():]
                                                                                    match_end = re.search(proximo_bloco, sub, re.IGNORECASE)
                                                                                    if match_end:
                                                                                                                    sub = sub[:match_end.start()]
                                                                                                                linhas = [l.strip() for l in sub.split('\n') if l.strip()]
                                                                                    p = Parte()
                                                                                    if len(linhas) > 1:
                                                                                                                    p.nome = linhas[0]
                                                                                                                    # Busca CPF/CNPJ nas linhas seguintes
                                                                                                                    for linha in linhas[1:]:
                                                                                                                                                        m_doc = re.search(r'(\d{2,3}[\.\s]?\d{3}[\.\s]?\d{3}[/\s]?\d{0,4}-?\d{2}|\d{11}|\d{14})', linha)
                                                                                                                                                        if m_doc:
                                                                                                                                                                                                p.cpf_cnpj = m_doc.group(1)
                                                                                                                                                                                            # Municipio — linhas tipicamente curtas sem numeros
                                                                                                                                                                                            if not p.municipio and len(linha) > 3 and not re.search(r'\d{5}', linha):
                                                                                                                                                                                                                                    p.municipio = linha
                                                                                                                                                                                                                        return p
                                                                                                                        
                                                                                                            nfa.remetente = extrair_parte_flex(r'REMETENTE', r'DESTINAT', bloco)
                                                                                nfa.destinatario = extrair_parte_flex(r'DESTINAT.{1,3}RIO', r'TRANSPORTADOR|PRODUTOS|PRODUTO', bloco)
                                                        nfa.transportador = extrair_parte_flex(r'TRANSPORTADOR', r'PRODUTO|ITEM|TOTAL', bloco)

                                    # P1-B: sync destinatario_cpf para xgboost_scorer
                                                        nfa.sync_destinatario_cpf()

                                    # Valores monetarios
                                                        m_total = re.search(r'VALOR\s+TOTAL[:\s]+([\d.,]+)', bloco, re.IGNORECASE)
                                                        if m_total:
                                                                                    nfa.valor_total = NFA.parse_currency(m_total.group(1))

                                                        m_icms = re.search(r'(?:VALOR\s+)?ICMS[:\s]+([\d.,]+)', bloco, re.IGNORECASE)
                                                        if m_icms:
                                                                                    nfa.valor_icms = NFA.parse_currency(m_icms.group(1))

                                                        # P1-B: Cabecas — numero de animais (critico para XGBoost score)
                                                        # Tenta extrair de varios formatos: "CABECAS: 10", "10 CABECAS", "QTD ANIMAIS: 10"
                                                        m_cabecas = re.search(
                                                            r'(?:CAB[EE]?[CÇ]AS?|QTD\.?\s*ANIMAIS?|QUANTIDADE\s+ANIMAIS?)[:\s]+([\d.,]+)',
                                                            bloco, re.IGNORECASE
                                                        )
                                                        if m_cabecas:
                                                                                    nfa.cabecas = NFA.parse_quantity(m_cabecas.group(1))
elif nfa.quantidade_total > 0:
                        # Fallback: usa quantidade_total como proxy de cabecas para rurais
                        nfa.cabecas = nfa.quantidade_total

                    # Quantidade total de produtos
                    m_qtd = re.search(r'QUANTIDADE\s+TOTAL[:\s]+([\d.,]+)', bloco, re.IGNORECASE)
                    if m_qtd:
                                                nfa.quantidade_total = NFA.parse_quantity(m_qtd.group(1))

                    # Calcular confidence score para ExtractionOrchestrator
                    nfa.confidence_score = _calcular_confidence(nfa)

                    notas.append(nfa)

except Exception as e:
                    logger.warning(f"Erro ao processar bloco NFA: {e}")
                    continue

except Exception as e:
        logger.error(f"Erro ao abrir PDF {caminho_pdf}: {e}")

    return notas, nome_produtor, cpf_produtor


def resumo_geral(notas: List[NFA], nome_contribuinte: str = "") -> Dict[str, Any]:
        """Gera resumo agregado das NFAs para consumo pelos agentes LangGraph.

            Inclui metricas por natureza, top destinatarios e indicadores de risco.
                Usado por agents_engine.py::_extrair_metricas_compactas().
                    """
    if not notas:
                return {
                    "contribuinte": nome_contribuinte,
                    "total_notas": 0,
                    "total_valor": 0.0,
                    "total_cabecas": 0.0,
                    "ticket_medio": 0.0,
                    "vendas_notas": 0,
                    "vendas_valor": 0.0,
                    "vendas_cabecas": 0.0,
                    "por_natureza": {},
                    "top_dest": [],
    }

    total_valor = sum(n.valor_total for n in notas)
    total_cabecas = sum(n.cabecas for n in notas)
    total_notas = len(notas)

    # Agrupamento por natureza
    por_natureza: Dict[str, Dict[str, Any]] = {}
    for nfa in notas:
                nat = nfa.natureza
        if nat not in por_natureza:
                        por_natureza[nat] = {"qtd_notas": 0, "valor": 0.0, "cabecas": 0.0}
                    por_natureza[nat]["qtd_notas"] += 1
        por_natureza[nat]["valor"] += nfa.valor_total
        por_natureza[nat]["cabecas"] += nfa.cabecas

    # Vendas especificas
    vendas = por_natureza.get("VENDA", {})
    vendas_notas = vendas.get("qtd_notas", 0)
    vendas_valor = vendas.get("valor", 0.0)
    vendas_cabecas = vendas.get("cabecas", 0.0)

    # Top destinatarios (por valor)
    dest_map: Dict[str, Dict[str, Any]] = {}
    for nfa in notas:
                cpf = nfa.destinatario_cpf or nfa.destinatario.cpf_cnpj or "desconhecido"
        nome = nfa.destinatario.nome or "Desconhecido"
        if cpf not in dest_map:
                        dest_map[cpf] = {"nome": nome, "valor": 0.0, "cabecas": 0.0}
                    dest_map[cpf]["valor"] += nfa.valor_total
        dest_map[cpf]["cabecas"] += nfa.cabecas

    top_dest = sorted(dest_map.values(), key=lambda x: x["valor"], reverse=True)[:10]

    return {
                "contribuinte": nome_contribuinte,
                "total_notas": total_notas,
                "total_valor": round(total_valor, 2),
                "total_cabecas": round(total_cabecas, 2),
                "ticket_medio": round(total_valor / total_notas, 2) if total_notas else 0.0,
                "vendas_notas": vendas_notas,
                "vendas_valor": round(vendas_valor, 2),
                "vendas_cabecas": round(vendas_cabecas, 2),
                "por_natureza": por_natureza,
                "top_dest": top_dest,
    }
