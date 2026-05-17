"""
orgaudi.data_processing
═══════════════════════
Motor de processamento da auditoria. Não tem dependência de PDF/ReportLab.

Conteúdo:
  • ResumoFiscal (apuração F1-F6 + alíquotas Funrural por categoria/data)
  • PlanilhaMensal (linha mensal de vendas/remessas/compras)
  • classificar_nota() — Regra 1 OrgAudi 1.0 (Receita / Trânsito / Despesa)
  • apurar_resumo() — calcula F1-F6 e tributos derivados
  • construir_planilha_mensal() — agrupa notas por mês
  • Testes forenses T-01 (concentração), T-02 (smurfing), T-04 (concentração PF),
    T-07 (documental — dígito verificador)
  • hash_laudo() — SHA-256 determinístico para auditabilidade

Dependências internas: orgaudi.domain, orgaudi.validators
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .domain import (
    CategoriaContabil,
    Contribuinte,
    NaturezaNota,
    NotaFiscal,
    Periodo,
    PFRecorrente,
)
from .validators import (
    mascara_cnpj,
    mascara_cpf,
    validar_cnpj,
    validar_cpf,
)


logger = logging.getLogger("orgaudi")


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

# Regra 1 — meses em pt-BR
MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


# ═══════════════════════════════════════════════════════════════════════════════
#  RESUMO FISCAL — F1-F6 e tributos derivados (Funrural por categoria/data)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResumoFiscal:
    """Apuração F1-F6 e tributos derivados, calculados a partir das notas."""
    F1_receita_imediata: Decimal = Decimal("0")
    F2_transito: Decimal = Decimal("0")
    F3_receita_realizada_leilao: Decimal = Decimal("0")
    F4_receita_bruta: Decimal = Decimal("0")
    F5_resultado_rural: Decimal = Decimal("0")
    F6_despesa: Decimal = Decimal("0")

    qtd_vendas: int = 0
    qtd_remessas: int = 0
    qtd_compras: int = 0
    qtd_total_saidas: int = 0           # F1+F2 (vendas + remessas)
    valor_bruto_saidas: Decimal = Decimal("0")  # F1+F2
    cabecas_vendas: int = 0
    cabecas_remessas: int = 0
    cabecas_compras: int = 0

    # Data de referência para escolher a alíquota correta de Funrural
    # (default = última data conhecida do período auditado, injetada por apurar_resumo)
    data_referencia: Optional[date] = None

    # Categoria previdenciária do contribuinte (afeta alíquota Funrural — LC 224/2025)
    # Default = PF Patronal (mais comum). Ajustar via Contribuinte ao chamar apurar_resumo.
    eh_pj: bool = False
    eh_segurado_especial: bool = False

    # Marco regulatório da LC 224/2025 — Funrural muda em 01/04/2026
    LIMITE_FUNRURAL_NOVA_ALIQUOTA: date = field(
        default_factory=lambda: date(2026, 4, 1), repr=False)

    @property
    def aliquota_funrural(self) -> Decimal:
        """
        Retorna a alíquota Funrural vigente para o período auditado e a
        categoria previdenciária do contribuinte.

        Marco regulatório:
          - Lei 8.212/91 e Lei 8.870/94: alíquotas até 31/03/2026
          - LC 224/2025: majoração de 10% sobre Previdência+RAT a partir de 01/04/2026
          - Orientação RFB de 03/2026: segurado especial NÃO majorado (mantém 1,5%)

        Tabela aplicada:
          ┌──────────────────────────────┬────────────────┬──────────────┐
          │ Categoria                    │ Até 31/03/2026 │ ≥ 01/04/2026 │
          ├──────────────────────────────┼────────────────┼──────────────┤
          │ PF Patronal                  │ 1,50%          │ 1,63%        │
          │ PF Segurado Especial         │ 1,50%          │ 1,50%        │
          │ PJ                           │ 2,05%          │ 2,23%        │
          └──────────────────────────────┴────────────────┴──────────────┘
        """
        ref = self.data_referencia or date.today()
        majorou = ref >= self.LIMITE_FUNRURAL_NOVA_ALIQUOTA

        if self.eh_pj:
            return Decimal("0.0223") if majorou else Decimal("0.0205")
        if self.eh_segurado_especial:
            # Excepcionado da majoração da LC 224/2025
            return Decimal("0.015")
        # PF Patronal (default)
        return Decimal("0.0163") if majorou else Decimal("0.015")

    @property
    def funrural(self) -> Decimal:
        """Funrural sobre receita imediata (F1), com alíquota vigente no período."""
        return (self.F1_receita_imediata * self.aliquota_funrural).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def aliquota_funrural_pct(self) -> str:
        """Representação percentual em pt-BR (ex: '1,50%' ou '1,63%')."""
        pct = self.aliquota_funrural * Decimal("100")
        return f"{pct:.2f}%".replace(".", ",")

    @property
    def categoria_previdenciaria(self) -> str:
        """Rótulo legível da categoria previdenciária aplicada."""
        if self.eh_pj:
            return "PJ"
        if self.eh_segurado_especial:
            return "PF Segurado Especial"
        return "PF Patronal"

    @property
    def base_legal_funrural(self) -> str:
        """Base legal da alíquota aplicada — para citação em laudos."""
        ref = self.data_referencia or date.today()
        majorou = ref >= self.LIMITE_FUNRURAL_NOVA_ALIQUOTA
        if self.eh_segurado_especial:
            if majorou:
                return "Lei 8.212/91; LC 224/2025 (excepcionado pela RFB em 03/2026)"
            return "Lei 8.212/91"
        if self.eh_pj:
            return "LC 224/2025; Lei 8.870/94" if majorou else "Lei 8.870/94"
        # PF Patronal
        return "LC 224/2025; Lei 8.212/91" if majorou else "Lei 8.212/91"

    @property
    def irpf_estimado(self) -> Decimal:
        """20% × resultado da atividade rural (≥ 0; prejuízo rural → R$0)."""
        base = max(self.F5_resultado_rural, Decimal("0"))
        return (base * Decimal("0.20")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class PlanilhaMensal:
    """Linha mensal de uma planilha (vendas/remessas/compras)."""
    mes: str
    qtd_notas: int
    cabecas: int
    valor: Decimal


# ═══════════════════════════════════════════════════════════════════════════════
#  REGRA 1 — Classificação contábil das NFA-e
# ═══════════════════════════════════════════════════════════════════════════════

def classificar_nota(nota: NotaFiscal, contribuinte_cpf: str) -> CategoriaContabil:
    """Aplica Regra 1 OrgAudi 1.0 — classificação contábil."""
    cpf_c = re.sub(r"\D", "", contribuinte_cpf)
    rem = re.sub(r"\D", "", nota.remetente_cpf or "")
    dest = re.sub(r"\D", "", nota.destinatario_cpf or "")

    # Mesmo CPF nos dois lados → transferência
    if rem == dest == cpf_c and rem:
        return CategoriaContabil.TRANSFERENCIA

    # Cliente como remetente
    if rem == cpf_c:
        if nota.natureza == NaturezaNota.VENDA:
            return CategoriaContabil.RECEITA
        if nota.natureza in (NaturezaNota.REMESSA, NaturezaNota.LEILAO):
            return CategoriaContabil.TRANSITO
        # Edge case: contribuinte como remetente em natureza incomum (COMPRA, TRANSFERENCIA)
        logger.warning(
            "Nota %s: contribuinte é REMETENTE com natureza %s — caso atípico, "
            "classificada como TRANSFERÊNCIA (revisar manualmente).",
            nota.numero, nota.natureza.value)
        return CategoriaContabil.TRANSFERENCIA

    # Cliente como destinatário — classifica como DESPESA independente da natureza.
    # Em NFA-e brasileiras a natureza reflete a perspectiva do REMETENTE (vendedor);
    # notas exportadas como "VENDA" pelo sistema SEFAZ-GO aparecem com natureza=VENDA
    # mesmo quando o contribuinte auditado é o COMPRADOR (destinatário). A Regra 1
    # OrgAudi trata qualquer entrada de gado no plantel como DESPESA/COMPRA.
    if dest == cpf_c:
        if nota.natureza not in (NaturezaNota.REMESSA, NaturezaNota.LEILAO):
            return CategoriaContabil.DESPESA
        # Remessa/leilão recebida pelo contribuinte = trânsito de entrada (não conta F6)
        return CategoriaContabil.TRANSITO

    # Edge case: nota não envolve o contribuinte em nenhuma ponta reconhecível
    if cpf_c not in (rem, dest):
        logger.warning(
            "Nota %s: CPF do contribuinte (%s) não consta como remetente nem "
            "destinatário (rem=%s, dest=%s) — classificada como TRANSFERÊNCIA.",
            nota.numero, mascara_cpf(cpf_c) if cpf_c else "?",
            mascara_cpf(rem) if rem else "vazio",
            mascara_cpf(dest) if dest else "vazio")

    return CategoriaContabil.TRANSFERENCIA


# ═══════════════════════════════════════════════════════════════════════════════
#  REGRA 2 — Apuração F1-F6 e construção de planilhas mensais
# ═══════════════════════════════════════════════════════════════════════════════

def apurar_resumo(
    notas: list[NotaFiscal],
    contribuinte: "str | Contribuinte",
    data_referencia: Optional[date] = None,
) -> ResumoFiscal:
    """
    Calcula F1-F6 e tributos a partir da lista de notas (Regra 2).

    Args:
      notas: lista de NFA-e do período.
      contribuinte: aceita um objeto Contribuinte (preferencial — propaga
        categoria previdenciária para a alíquota Funrural correta) ou apenas
        a string do CPF/CNPJ (retrocompatível — assume PF Patronal).
      data_referencia: última data do período auditado (ou outra data relevante).
        Determina qual alíquota de Funrural aplicar (LC 224/2025).
        Se não fornecida, usa a maior data observada nas notas; se ainda assim
        não houver, cai em date.today().
    """
    # Normaliza: aceita Contribuinte ou string para retrocompatibilidade
    if isinstance(contribuinte, Contribuinte):
        contribuinte_doc = contribuinte.cpf
        eh_pj = contribuinte.eh_pj
        eh_segurado_especial = contribuinte.eh_segurado_especial
    else:
        contribuinte_doc = contribuinte
        # Heurística: 14 dígitos = PJ, 11 dígitos = PF Patronal (default)
        doc_num = re.sub(r"\D", "", contribuinte_doc or "")
        eh_pj = (len(doc_num) == 14)
        eh_segurado_especial = False

    r = ResumoFiscal(eh_pj=eh_pj, eh_segurado_especial=eh_segurado_especial)
    for n in notas:
        cat = classificar_nota(n, contribuinte_doc)
        if cat == CategoriaContabil.RECEITA:
            r.F1_receita_imediata += n.valor
            r.qtd_vendas += 1
            r.cabecas_vendas += n.cabecas
        elif cat == CategoriaContabil.TRANSITO:
            r.F2_transito += n.valor
            r.qtd_remessas += 1
            r.cabecas_remessas += n.cabecas
        elif cat == CategoriaContabil.DESPESA:
            r.F6_despesa += n.valor
            r.qtd_compras += 1
            r.cabecas_compras += n.cabecas

    r.F4_receita_bruta = r.F1_receita_imediata + r.F3_receita_realizada_leilao
    r.F5_resultado_rural = r.F4_receita_bruta - r.F6_despesa
    r.qtd_total_saidas = r.qtd_vendas + r.qtd_remessas
    r.valor_bruto_saidas = r.F1_receita_imediata + r.F2_transito

    # Injeta data de referência para o cálculo correto da alíquota Funrural
    if data_referencia is not None:
        r.data_referencia = data_referencia
    elif notas:
        r.data_referencia = max(n.data for n in notas)
    else:
        r.data_referencia = date.today()

    return r


def construir_planilha_mensal(
    notas: list[NotaFiscal],
    categoria_alvo: CategoriaContabil,
    contribuinte_cpf: str
) -> list[PlanilhaMensal]:
    """Agrupa notas por mês (apenas as da categoria alvo)."""
    bucket: dict[int, list[NotaFiscal]] = defaultdict(list)
    for n in notas:
        if classificar_nota(n, contribuinte_cpf) == categoria_alvo:
            bucket[n.data.month].append(n)

    out: list[PlanilhaMensal] = []
    for mes in range(1, 13):
        if mes in bucket:
            grp = bucket[mes]
            out.append(PlanilhaMensal(
                mes=MESES_PT[mes - 1],
                qtd_notas=len(grp),
                cabecas=sum(n.cabecas for n in grp),
                valor=sum((n.valor for n in grp), Decimal("0")),
            ))
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  TESTES FORENSES T-01 a T-08 (resultados estruturados)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResultadoT01:
    """T-01 Concentração: notas que individualmente representam ≥ 10% da receita."""
    notas_concentradoras: list[tuple[NotaFiscal, float]] = field(default_factory=list)

    def detectado(self) -> bool:
        return len(self.notas_concentradoras) > 0


@dataclass
class GrupoSmurfing:
    """Grupo de notas detectadas como smurfing (T-02)."""
    data: date
    destinatario_cpf: str
    destinatario_nome: str
    notas: list[NotaFiscal]
    valor_total: Decimal
    valor_repetido: Optional[Decimal] = None
    qtd_repeticoes: int = 0


@dataclass
class ResultadoT02:
    grupos: list[GrupoSmurfing] = field(default_factory=list)

    def detectado(self) -> bool:
        return any(g.qtd_repeticoes >= 3 for g in self.grupos)


@dataclass
class ResultadoT04:
    """Concentração em PFs com perfil de revenda."""
    pfs_recorrentes: list[PFRecorrente] = field(default_factory=list)
    pct_vendas_pf: float = 0.0

    def detectado(self) -> bool:
        return self.pct_vendas_pf >= 90.0 and len(self.pfs_recorrentes) > 0


@dataclass
class ResultadoT07:
    """Validação de dígitos verificadores."""
    cpfs_invalidos: list[str] = field(default_factory=list)
    cnpjs_invalidos: list[str] = field(default_factory=list)
    total_documentos_verificados: int = 0


def teste_t01_concentracao(
    notas: list[NotaFiscal], cpf: str, threshold_pct: float = 10.0
) -> ResultadoT01:
    """T-01: 1 nota com ≥ threshold% da receita anual."""
    receita = sum(
        (n.valor for n in notas
         if classificar_nota(n, cpf) == CategoriaContabil.RECEITA),
        Decimal("0"))
    if receita == 0:
        return ResultadoT01()

    out: list[tuple[NotaFiscal, float]] = []
    for n in notas:
        if classificar_nota(n, cpf) == CategoriaContabil.RECEITA:
            pct = float(n.valor / receita * 100)
            if pct >= threshold_pct:
                out.append((n, pct))
    out.sort(key=lambda x: x[1], reverse=True)
    return ResultadoT01(notas_concentradoras=out)


def teste_t02_smurfing(
    notas: list[NotaFiscal], cpf: str, min_repeticoes: int = 3
) -> ResultadoT02:
    """T-02: ≥ N notas no mesmo dia/destinatário com valores idênticos."""
    bucket: dict[tuple, list[NotaFiscal]] = defaultdict(list)
    for n in notas:
        if classificar_nota(n, cpf) != CategoriaContabil.RECEITA:
            continue
        if not n.destinatario_cpf:
            continue
        bucket[(n.data, re.sub(r"\D", "", n.destinatario_cpf))].append(n)

    grupos: list[GrupoSmurfing] = []
    for (dt, dest_cpf), notas_dia in bucket.items():
        if len(notas_dia) < 2:
            continue
        valores = Counter(str(n.valor) for n in notas_dia)
        valor_top, qtd_top = valores.most_common(1)[0]
        if qtd_top >= min_repeticoes:
            grupos.append(GrupoSmurfing(
                data=dt,
                destinatario_cpf=mascara_cpf(dest_cpf),
                destinatario_nome=notas_dia[0].destinatario_nome,
                notas=sorted(notas_dia, key=lambda x: x.numero),
                valor_total=sum((n.valor for n in notas_dia), Decimal("0")),
                valor_repetido=Decimal(valor_top),
                qtd_repeticoes=qtd_top,
            ))
    return ResultadoT02(grupos=grupos)


def teste_t04_concentracao_pf(
    notas: list[NotaFiscal], cpf: str, min_aquisicoes: int = 3
) -> ResultadoT04:
    """T-04: ≥ 90% das vendas a PF + PFs com 3+ aquisições."""
    vendas = [n for n in notas
              if classificar_nota(n, cpf) == CategoriaContabil.RECEITA]
    if not vendas:
        return ResultadoT04()

    # Quantas vendas para PF (CPF — 11 dígitos)
    qtd_pf = sum(
        1 for n in vendas
        if len(re.sub(r"\D", "", n.destinatario_cpf or "")) == 11)
    pct_pf = qtd_pf / len(vendas) * 100

    # PFs com 3+ aquisições
    pf_bucket: dict[str, list[NotaFiscal]] = defaultdict(list)
    for n in vendas:
        c = re.sub(r"\D", "", n.destinatario_cpf or "")
        if len(c) == 11:
            pf_bucket[c].append(n)

    pfs: list[PFRecorrente] = []
    for cpf_pf, notas_pf in pf_bucket.items():
        if len(notas_pf) >= min_aquisicoes:
            pfs.append(PFRecorrente(
                nome=notas_pf[0].destinatario_nome,
                cpf=mascara_cpf(cpf_pf),
                qtd_notas=len(notas_pf),
                valor_total=sum((n.valor for n in notas_pf), Decimal("0")),
            ))
    pfs.sort(key=lambda p: p.valor_total, reverse=True)
    return ResultadoT04(pfs_recorrentes=pfs, pct_vendas_pf=pct_pf)


def teste_t07_documental(notas: list[NotaFiscal]) -> ResultadoT07:
    """T-07: dígitos verificadores de todos os CPF/CNPJ envolvidos."""
    docs: set[str] = set()
    for n in notas:
        for d in (n.remetente_cpf, n.destinatario_cpf):
            if d:
                docs.add(re.sub(r"\D", "", d))

    cpfs_inv = []
    cnpjs_inv = []
    for d in docs:
        if len(d) == 11:
            if not validar_cpf(d):
                cpfs_inv.append(mascara_cpf(d))
        elif len(d) == 14:
            if not validar_cnpj(d):
                cnpjs_inv.append(mascara_cnpj(d))
    return ResultadoT07(
        cpfs_invalidos=cpfs_inv,
        cnpjs_invalidos=cnpjs_inv,
        total_documentos_verificados=len(docs))


# ═══════════════════════════════════════════════════════════════════════════════
#  HASH DO LAUDO — para auditabilidade
# ═══════════════════════════════════════════════════════════════════════════════

def hash_laudo(contribuinte: Contribuinte, periodo: Periodo,
               resumo: ResumoFiscal, notas: list[NotaFiscal]) -> str:
    """SHA-256 completo (64 chars) dos dados estruturados do laudo."""
    h = hashlib.sha256()
    h.update(f"{contribuinte.cpf}|{contribuinte.nome}".encode())
    h.update(f"|{periodo.inicio}|{periodo.fim}".encode())
    h.update(f"|{periodo.data_auditoria}".encode())
    h.update(f"|F1={resumo.F1_receita_imediata}".encode())
    h.update(f"|F2={resumo.F2_transito}".encode())
    h.update(f"|F3={resumo.F3_receita_realizada_leilao}".encode())
    h.update(f"|F4={resumo.F4_receita_bruta}".encode())
    h.update(f"|F5={resumo.F5_resultado_rural}".encode())
    h.update(f"|F6={resumo.F6_despesa}".encode())
    h.update(f"|N={len(notas)}".encode())
    return h.hexdigest()  # 64 chars — SHA-256 completo


def hash_laudo_completo(contribuinte: Contribuinte, periodo: Periodo,
                        resumo: ResumoFiscal, notas: list[NotaFiscal],
                        achados: list) -> str:
    """SHA-256 expandido — cobre dados estruturados + conteúdo narrativo dos achados."""
    h = hashlib.sha256()
    h.update(f"{contribuinte.cpf}|{contribuinte.nome}".encode())
    h.update(f"|{periodo.inicio}|{periodo.fim}".encode())
    h.update(f"|{periodo.data_auditoria}".encode())
    h.update(f"|F1={resumo.F1_receita_imediata}".encode())
    h.update(f"|F2={resumo.F2_transito}".encode())
    h.update(f"|F3={resumo.F3_receita_realizada_leilao}".encode())
    h.update(f"|F4={resumo.F4_receita_bruta}".encode())
    h.update(f"|F5={resumo.F5_resultado_rural}".encode())
    h.update(f"|F6={resumo.F6_despesa}".encode())
    h.update(f"|N={len(notas)}".encode())
    for a in sorted(achados, key=lambda x: x.codigo):
        h.update(f"|ACHADO:{a.codigo}".encode())
        h.update(f"|SEV:{a.severidade.value}".encode())
        h.update(f"|TITULO:{a.titulo}".encode())
        if a.descricao:
            h.update(f"|DESC:{a.descricao}".encode())
        for cruz in sorted(a.cruzamentos or []):
            h.update(f"|CRUZ:{cruz}".encode())
    return h.hexdigest()
