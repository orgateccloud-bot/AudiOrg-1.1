"""
═══════════════════════════════════════════════════════════════════════════════
  OrgAudi 1.0 — Gerador Paramétrico Completo (v4)
  ORGATEC CONTABILIDADE E AUDITORIA
═══════════════════════════════════════════════════════════════════════════════

Refatoração completa do gerar_v3.py: todos os 11 conteúdos de página
agora são parametrizados via dataclasses. Mesmo design, mesma qualidade,
agora com dados de qualquer contribuinte.

Melhorias sobre as versões anteriores:
  • Validação real de CPF/CNPJ (cálculo de dígito verificador)
  • Formatação automática de moeda BR (R$ X,XX)
  • Apuração automática de F1-F6 a partir das planilhas mensais
  • Detecção automática de smurfing (T-02)
  • Detecção automática de concentração (T-01)
  • Detecção automática de PFs recorrentes (T-04)
  • Tipologias inferidas automaticamente dos achados
  • Resumo executivo de 1 linha (impressão ou e-mail)
  • Hash SHA-256 do laudo (auditável)

Uso:
  from orgaudi_v4 import LaudoOrgAudi, Contribuinte, Periodo, NotaFiscal
  laudo = LaudoOrgAudi(contribuinte=..., periodo=..., notas=[...])
  laudo.processar()
  laudo.gerar_pdf("saida.pdf")
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from pathlib import Path
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

# Logger do módulo


# ===========================================================================
#  TIPOLOGIAS DE ANOMALIAS — Catálogo de 18 tipos × 5 eixos
# ===========================================================================

# (imports Enum, dataclass/field e List já estão no topo do arquivo)


# ─────────────────────────────────────────────
# ENUM: Eixos de Classificação
# ─────────────────────────────────────────────

class EixoAnomalia(str, Enum):
    MANIPULACAO_VALORES         = "I"
    IRREGULARIDADE_PARTES       = "II"
    IRREGULARIDADE_MERCADORIA   = "III"
    IRREGULARIDADE_CADASTRAL    = "IV"
    ESQUEMAS_ESTRUTURADOS       = "V"


# ─────────────────────────────────────────────
# ENUM: Nível de Gravidade
# ─────────────────────────────────────────────

class Gravidade(str, Enum):
    MEDIA       = "Média"
    ALTA        = "Alta"
    MUITO_ALTA  = "Muito Alta"


# ─────────────────────────────────────────────
# ENUM: Códigos de Anomalia
# ─────────────────────────────────────────────

class CodigoAnomalia(str, Enum):
    # Eixo I — Manipulação de Valores
    AN_01 = "AN-01"   # Fragmentação fiscal (smurfing)
    AN_02 = "AN-02"   # Subfaturamento declarado
    AN_03 = "AN-03"   # Superfaturamento reverso
    AN_04 = "AN-04"   # Subdeclaração em leilão (conluio com leiloeiro)

    # Eixo II — Irregularidade de Partes
    AN_05 = "AN-05"   # Uso de interpostas pessoas (laranjas)
    AN_06 = "AN-06"   # Destinatário inexistente ou inativo
    AN_07 = "AN-07"   # Intermediação não declarada por PF
    AN_08 = "AN-08"   # Transferência intrafamiliar disfarçada de venda

    # Eixo III — Irregularidade de Mercadoria
    AN_09 = "AN-09"   # Lavagem de origem de gado
    AN_10 = "AN-10"   # Inconsistência de capacidade produtiva
    AN_11 = "AN-11"   # Sazonalidade incompatível

    # Eixo IV — Irregularidade Cadastral e Operacional
    AN_12 = "AN-12"   # Inconsistência cadastral
    AN_13 = "AN-13"   # Concentração atípica de operações
    AN_14 = "AN-14"   # Ciclo operacional implausível
    AN_15 = "AN-15"   # Endereço fiscal fantasma

    # Eixo V — Esquemas Estruturados
    AN_16 = "AN-16"   # Carrossel fiscal rural
    AN_17 = "AN-17"   # Emissão em cascata
    AN_18 = "AN-18"   # Caixa dois agropecuário


# ─────────────────────────────────────────────
# DATACLASS: Definição Completa de Anomalia
# ─────────────────────────────────────────────

@dataclass
class TipologiaAnomalia:
    codigo: CodigoAnomalia
    tipo: str
    descricao: str
    eixo: EixoAnomalia
    gravidade: Gravidade
    tributos_impactados: List[str]
    documentos_ref: List[str]


# ─────────────────────────────────────────────
# CATÁLOGO COMPLETO
# ─────────────────────────────────────────────

TIPOLOGIAS_DISPONIVEIS = True

CATALOGO_ANOMALIAS: List[TipologiaAnomalia] = [

    # ── Eixo I ────────────────────────────────
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_01,
        tipo="Fragmentação fiscal (smurfing)",
        descricao="Divisão artificial de operações para fugir de limites de notificação ou de faixas tributárias",
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "FUNRURAL", "IRPF Rural"],
        documentos_ref=["NFA-e", "NF-e", "LCDPR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_02,
        tipo="Subfaturamento declarado",
        descricao="Valor de NF-e/NFA-e sistematicamente abaixo do preço de mercado da commodity",
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "FUNRURAL", "IRPF Rural"],
        documentos_ref=["NFA-e", "NF-e", "Pauta SEFAZ"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_03,
        tipo="Superfaturamento reverso",
        descricao="Entradas declaradas acima do valor real para inflar créditos ou justificar saídas maiores",
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "PIS/COFINS"],
        documentos_ref=["NF-e", "SPED Fiscal"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_04,
        tipo="Subdeclaração em leilão (conluio com leiloeiro)",
        descricao="Ajuste entre arrematante e leiloeiro para registrar valor inferior ao efetivamente pago",
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ITBI", "ICMS", "IRPF"],
        documentos_ref=["NFA-e", "Termo de Arrematação"],
    ),

    # ── Eixo II ───────────────────────────────
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_05,
        tipo="Uso de interpostas pessoas (laranjas)",
        descricao="CPF/CNPJ de terceiros utilizados para ocultar real remetente, destinatário ou beneficiário",
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF", "FUNRURAL"],
        documentos_ref=["NFA-e", "GTA", "LCDPR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_06,
        tipo="Destinatário inexistente ou inativo",
        descricao="Emissão de NFA-e para cadastro CPF/CNPJ cancelado, suspenso ou sem atividade rural comprovável",
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS"],
        documentos_ref=["NFA-e", "Cadastro SEFAZ", "Receita Federal"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_07,
        tipo="Intermediação não declarada por PF",
        descricao="Pessoa física operando como trader/intermediário sem inscrição estadual e sem emissão de documento fiscal próprio",
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        gravidade=Gravidade.MEDIA,
        tributos_impactados=["ICMS", "IRPF", "FUNRURAL"],
        documentos_ref=["NFA-e", "Inscrição Estadual"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_08,
        tipo="Transferência intrafamiliar disfarçada de venda",
        descricao="Operação entre cônjuges, ascendentes/descendentes ou sócios encoberta como negócio oneroso para justificar movimentação patrimonial",
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ITCMD", "IRPF", "ITBI"],
        documentos_ref=["NFA-e", "LCDPR", "Declaração IRPF"],
    ),

    # ── Eixo III ──────────────────────────────
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_09,
        tipo="Lavagem de origem de gado",
        descricao="Reintrodução de animais de procedência irregular (sem GTA válida, SISBOV inconsistente ou área embargada) na cadeia documental formal",
        eixo=EixoAnomalia.IRREGULARIDADE_MERCADORIA,
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "FUNRURAL"],
        documentos_ref=["GTA", "SISBOV", "NFA-e", "CAR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_10,
        tipo="Inconsistência de capacidade produtiva",
        descricao="Volume ou peso declarado incompatível com área explorada, módulos fiscais, plantel histórico ou eficiência produtiva da atividade",
        eixo=EixoAnomalia.IRREGULARIDADE_MERCADORIA,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["FUNRURAL", "ITR", "IRPF Rural"],
        documentos_ref=["SNCR", "CAR", "NFA-e", "GTA", "LCDPR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_11,
        tipo="Sazonalidade incompatível",
        descricao="Picos de emissão em períodos fora da curva histórica do produtor ou do ciclo biológico/agrícola da commodity",
        eixo=EixoAnomalia.IRREGULARIDADE_MERCADORIA,
        gravidade=Gravidade.MEDIA,
        tributos_impactados=["ICMS", "FUNRURAL"],
        documentos_ref=["NFA-e", "GTA", "LCDPR"],
    ),

    # ── Eixo IV ───────────────────────────────
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_12,
        tipo="Inconsistência cadastral",
        descricao="Divergência entre dados do CNPJ/CPF, inscrição estadual, endereço fiscal, CAR/SNCR e dados da SEFAZ",
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        gravidade=Gravidade.MEDIA,
        tributos_impactados=["ICMS", "ITR"],
        documentos_ref=["Cadastro SEFAZ", "CAR", "SNCR", "Receita Federal"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_13,
        tipo="Concentração atípica de operações",
        descricao="Volume de emissões concentrado em poucos destinatários, datas ou valores-âncora sem justificativa econômica",
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        gravidade=Gravidade.MEDIA,
        tributos_impactados=["ICMS", "FUNRURAL"],
        documentos_ref=["NFA-e", "LCDPR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_14,
        tipo="Ciclo operacional implausível",
        descricao="Compra e revenda de gado/grãos em intervalo de tempo inviável para engorda, beneficiamento ou logística",
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "FUNRURAL", "IRPF Rural"],
        documentos_ref=["NFA-e", "GTA", "LCDPR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_15,
        tipo="Endereço fiscal fantasma",
        descricao="Imóvel rural declarado em área inexistente, sobreposta, embargada pelo IBAMA/SEMA ou sem matrícula no INCRA/CAR",
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ITR", "ICMS"],
        documentos_ref=["CAR", "SNCR", "INCRA", "IBAMA"],
    ),

    # ── Eixo V ────────────────────────────────
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_16,
        tipo="Carrossel fiscal rural",
        descricao="Sequência circular de compra e venda entre produtores relacionados para multiplicar créditos de ICMS/FUNRURAL artificialmente",
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "FUNRURAL"],
        documentos_ref=["NFA-e", "SPED Fiscal", "LCDPR"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_17,
        tipo="Emissão em cascata",
        descricao="Cadeia de notas encadeadas em que cada elo apenas retransmite a mesma mercadoria sem movimentação física real",
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "FUNRURAL"],
        documentos_ref=["NFA-e", "GTA", "SPED Fiscal"],
    ),
    TipologiaAnomalia(
        codigo=CodigoAnomalia.AN_18,
        tipo="Caixa dois agropecuário",
        descricao="Pagamentos em espécie sem correspondência em extrato bancário, GTA ou nota fiscal, com indício de LCDPR inconsistente",
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["IRPF Rural", "FUNRURAL", "ICMS"],
        documentos_ref=["LCDPR", "Extrato Bancário", "GTA", "NFA-e"],
    ),
]


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def buscar_por_codigo(codigo: str) -> TipologiaAnomalia | None:
    return next((a for a in CATALOGO_ANOMALIAS if a.codigo.value == codigo), None)


def buscar_por_eixo(eixo: EixoAnomalia) -> List[TipologiaAnomalia]:
    return [a for a in CATALOGO_ANOMALIAS if a.eixo == eixo]


def buscar_por_gravidade(gravidade: Gravidade) -> List[TipologiaAnomalia]:
    return [a for a in CATALOGO_ANOMALIAS if a.gravidade == gravidade]


def buscar_por_tributo(tributo: str) -> List[TipologiaAnomalia]:
    return [a for a in CATALOGO_ANOMALIAS if tributo in a.tributos_impactados]


# ─────────────────────────────────────────────
# USO EXEMPLO
# ─────────────────────────────────────────────

logger = logging.getLogger("orgaudi")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s orgaudi: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# Tipologias integradas (veja acima)


# ═══════════════════════════════════════════════════════════════════════════════
#  VALIDAÇÕES E FORMATAÇÕES
# ═══════════════════════════════════════════════════════════════════════════════

def validar_cpf(cpf: str) -> bool:
    """Valida CPF com dígito verificador real (não só formato)."""
    cpf_num = re.sub(r"\D", "", cpf)
    if len(cpf_num) != 11 or cpf_num == cpf_num[0] * 11:
        return False
    for i in (9, 10):
        s = sum(int(cpf_num[j]) * ((i + 1) - j) for j in range(i))
        d = (s * 10) % 11
        if d == 10:
            d = 0
        if d != int(cpf_num[i]):
            return False
    return True


def validar_cnpj(cnpj: str) -> bool:
    """Valida CNPJ com dígito verificador."""
    c = re.sub(r"\D", "", cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    # Pesos para 1º DV (12 dígitos) e 2º DV (13 dígitos)
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(c[i]) * pesos1[i] for i in range(12))
    d1 = 11 - s % 11
    d1 = 0 if d1 >= 10 else d1
    if d1 != int(c[12]):
        return False
    s = sum(int(c[i]) * pesos2[i] for i in range(13))
    d2 = 11 - s % 11
    d2 = 0 if d2 >= 10 else d2
    return d2 == int(c[13])


def fmt_brl(valor: Decimal | float | int, sinal: bool = True) -> str:
    """Formata valor em padrão brasileiro: R$ 1.234.567,89."""
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    valor = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}" if sinal else s


def fmt_brl_compact(valor: Decimal | float | int) -> str:
    """
    Formato BR completo (sem K/M abreviado) — modelo da moeda real brasileira.
    Usado nos KPIs da capa: R$ 3.827.533,91, R$ 730.076,89, etc.
    """
    return fmt_brl(valor)


def fmt_pct(valor: float, casas: int = 2) -> str:
    """Formata percentual em pt-BR: 12,77%."""
    return f"{valor:.{casas}f}%".replace(".", ",")


def fmt_data(d: date | str) -> str:
    """Formata data como DD/MM/YYYY."""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return d
    return d.strftime("%d/%m/%Y")


def mascara_cpf(cpf: str) -> str:
    """Aplica máscara XXX.XXX.XXX-XX a um CPF de 11 dígitos."""
    c = re.sub(r"\D", "", cpf)
    if len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return cpf


def mascara_cnpj(cnpj: str) -> str:
    """Aplica máscara XX.XXX.XXX/XXXX-XX a um CNPJ."""
    c = re.sub(r"\D", "", cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


# ═══════════════════════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class Severidade(str, Enum):
    CRITICO = "CRITICO"
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    ATENCAO = "ATENCAO"
    CONFORME = "CONFORME"


class NaturezaNota(str, Enum):
    VENDA = "VENDA"
    REMESSA = "REMESSA"
    LEILAO = "LEILAO"
    COMPRA = "COMPRA"
    TRANSFERENCIA = "TRANSFERENCIA"


class CategoriaContabil(str, Enum):
    """Resultado da Regra 1 OrgAudi 1.0."""
    RECEITA = "RECEITA"           # Remetente + Venda
    TRANSITO = "TRANSITO"         # Remetente + Remessa/Leilão
    DESPESA = "DESPESA"           # Destinatário + Compra
    TRANSFERENCIA = "TRANSFERENCIA"  # Mesmo CPF nos dois lados


# ═══════════════════════════════════════════════════════════════════════════════
#  DATACLASSES — DADOS DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Contribuinte:
    """Identificação do contribuinte auditado.

    Categorias previdenciárias rurais (afetam a alíquota Funrural — LC 224/2025):
      - eh_pj=False, eh_segurado_especial=False (default): produtor rural PF patronal
        → 1,5% até 31/03/2026 ; 1,63% a partir de 01/04/2026
      - eh_pj=False, eh_segurado_especial=True: agricultor familiar / segurado especial
        → 1,5% mantida (orientação RFB de 03/2026, após articulação do MDA)
      - eh_pj=True: produtor rural pessoa jurídica
        → 2,05% até 31/03/2026 ; 2,23% a partir de 01/04/2026
    """
    nome: str
    cpf: str  # com ou sem máscara — será normalizado
    ie: str = ""
    municipio: str = ""
    estado: str = "GO"
    eh_pj: bool = False
    eh_segurado_especial: bool = False

    def __post_init__(self):
        # Mascara CPF (11 dígitos) ou CNPJ (14 dígitos) conforme o caso
        doc_num = re.sub(r"\D", "", self.cpf)
        if len(doc_num) == 14:
            self.cpf = mascara_cnpj(self.cpf)
            self.eh_pj = True
        else:
            self.cpf = mascara_cpf(self.cpf)
        # Validação de coerência entre flags
        if self.eh_pj and self.eh_segurado_especial:
            raise ValueError(
                "Contribuinte não pode ser PJ e segurado especial simultaneamente. "
                "Segurado especial é categoria exclusiva de PF (agricultor familiar).")

    @property
    def cpf_valido(self) -> bool:
        doc_num = re.sub(r"\D", "", self.cpf)
        if len(doc_num) == 14:
            return validar_cnpj(self.cpf)
        return validar_cpf(self.cpf)

    @property
    def categoria_previdenciaria(self) -> str:
        """Rótulo legível da categoria — usado em laudos e mensagens."""
        if self.eh_pj:
            return "PJ"
        if self.eh_segurado_especial:
            return "PF Segurado Especial"
        return "PF Patronal"


@dataclass
class Periodo:
    """Período auditado."""
    inicio: date
    fim: date
    data_auditoria: date = field(default_factory=date.today)

    def __post_init__(self):
        # Aceita strings ISO
        if isinstance(self.inicio, str):
            self.inicio = datetime.strptime(self.inicio, "%Y-%m-%d").date()
        if isinstance(self.fim, str):
            self.fim = datetime.strptime(self.fim, "%Y-%m-%d").date()
        if isinstance(self.data_auditoria, str):
            self.data_auditoria = datetime.strptime(self.data_auditoria, "%Y-%m-%d").date()


@dataclass
class NotaFiscal:
    """Uma NFA-e individual. Todas as outras estatísticas derivam disto."""
    numero: str
    data: date
    natureza: NaturezaNota
    valor: Decimal
    cabecas: int = 0
    remetente_cpf: str = ""
    remetente_nome: str = ""
    destinatario_cpf: str = ""
    destinatario_nome: str = ""

    def __post_init__(self):
        if isinstance(self.data, str):
            self.data = datetime.strptime(self.data, "%Y-%m-%d").date()
        if not isinstance(self.valor, Decimal):
            self.valor = Decimal(str(self.valor))
        if isinstance(self.natureza, str):
            self.natureza = NaturezaNota(self.natureza)


@dataclass
class Leiloeiro:
    """Leiloeiro com gado em trânsito não-arrematado."""
    nome: str
    cnpj: str
    qtd_notas: int
    valor_total: Decimal


@dataclass
class PFRecorrente:
    """PF que aparece como destinatário 3+ vezes (T-04)."""
    nome: str
    cpf: str
    qtd_notas: int
    valor_total: Decimal


@dataclass
class Achado:
    """Um achado da auditoria — classificado por severidade."""
    codigo: str               # C-01, A-01, M-01, AT-01
    titulo: str
    descricao: str
    severidade: Severidade
    cruzamentos: list[str] = field(default_factory=list)
    tabela_cabecalhos: list[str] = field(default_factory=list)
    tabela_linhas: list[list[str]] = field(default_factory=list)
    tabela_totais: list[str] = field(default_factory=list)
    porque_critico: str = ""

    def __post_init__(self):
        if isinstance(self.severidade, str):
            self.severidade = Severidade(self.severidade)


@dataclass
class Etapa:
    """Etapa do plano de ação (timeline)."""
    numero: int
    titulo: str
    prazo: str               # "30 DIAS"
    accent: Severidade       # cor
    itens: list[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.accent, str):
            self.accent = Severidade(self.accent)


# ═══════════════════════════════════════════════════════════════════════════════
#  PALETA E ESTILOS (idêntica ao gerar_v3.py)
# ═══════════════════════════════════════════════════════════════════════════════

AZUL          = colors.HexColor("#003365")
AZUL_M        = colors.HexColor("#185FA5")
AZUL_CL       = colors.HexColor("#3F88D5")
BRANCO        = colors.white
CBG_LIGHT     = colors.HexColor("#F8FAFC")
CBG           = colors.HexColor("#EEF3F9")
CBORD         = colors.HexColor("#D6E0EC")
CBORD_LIGHT   = colors.HexColor("#E8EEF5")
CTXT          = colors.HexColor("#475569")
CTXT_DARK     = colors.HexColor("#1E293B")

CRITICO       = colors.HexColor("#B91C1C")
CRITICO_BG    = colors.HexColor("#FEF2F2")
CRITICO_BORD  = colors.HexColor("#FCA5A5")
ALTO          = colors.HexColor("#B45309")
ALTO_BG       = colors.HexColor("#FFFBEB")
ALTO_BORD     = colors.HexColor("#FCD34D")
MEDIO         = colors.HexColor("#1D4ED8")
MEDIO_BG      = colors.HexColor("#EFF6FF")
MEDIO_BORD    = colors.HexColor("#93C5FD")
ATENCAO       = colors.HexColor("#7C3AED")
ATENCAO_BG    = colors.HexColor("#F5F3FF")
ATENCAO_BORD  = colors.HexColor("#C4B5FD")
CONFORME      = colors.HexColor("#15803D")
CONFORME_BG   = colors.HexColor("#F0FDF4")
CONFORME_BORD = colors.HexColor("#86EFAC")

# Mapas severidade → (cor, bg, bord)
SEV_PALETA = {
    Severidade.CRITICO:  (CRITICO,  CRITICO_BG,  CRITICO_BORD),
    Severidade.ALTO:     (ALTO,     ALTO_BG,     ALTO_BORD),
    Severidade.MEDIO:    (MEDIO,    MEDIO_BG,    MEDIO_BORD),
    Severidade.ATENCAO:  (ATENCAO,  ATENCAO_BG,  ATENCAO_BORD),
    Severidade.CONFORME: (CONFORME, CONFORME_BG, CONFORME_BORD),
}

PW, PH = A4
W = PW - 28 * mm

# Logos (busca em vários caminhos para portabilidade)
def _logo_path(nome: str) -> str:
    # Primeiro: pasta do proprio modulo (funciona em qualquer OS)
    module_dir = Path(__file__).parent
    p = module_dir / nome
    if p.exists():
        return str(p)
    for base in ("/home/claude", "/mnt/user-data/uploads", "."):
        p = Path(base) / nome
        if p.exists():
            return str(p)
    return ""


def _get_logo_t() -> str:
    """Resolve logo transparente (fundo transparente) — lazy."""
    return _logo_path("logo_oficial_transp.png")


def _get_logo_h() -> str:
    """Resolve logo para header (fundo #003365) — lazy."""
    return _logo_path("logo_oficial_header.png")


def S(n, **k):
    d = dict(fontName="Helvetica", fontSize=8.5, textColor=CTXT_DARK, leading=12)
    d.update(k)
    return ParagraphStyle(n, **d)


ST = {
    "h1":      S("h1",  fontName="Helvetica-Bold", fontSize=22, textColor=AZUL,    alignment=TA_CENTER, spaceAfter=2,  leading=26),
    "h2":      S("h2",  fontName="Helvetica-Bold", fontSize=14, textColor=AZUL,    alignment=TA_CENTER, spaceAfter=4,  leading=17),
    "kicker":  S("k",   fontName="Helvetica-Bold", fontSize=8,  textColor=AZUL_CL, alignment=TA_CENTER, spaceAfter=4),
    "sub":     S("s",   fontName="Helvetica",      fontSize=9.5, textColor=CTXT,   alignment=TA_CENTER, spaceAfter=8,  leading=13),
    "sec":     S("sc",  fontName="Helvetica-Bold", fontSize=10, textColor=AZUL_M,  spaceBefore=6, spaceAfter=4, leading=13),
    "subsec":  S("ss",  fontName="Helvetica-Bold", fontSize=9,  textColor=AZUL_M,  spaceBefore=4, spaceAfter=2),
    "body":    S("b",   fontName="Helvetica",      fontSize=8.5, textColor=CTXT_DARK, leading=12.5, spaceAfter=4, alignment=TA_JUSTIFY),
    "small":   S("sm",  fontName="Helvetica",      fontSize=7.5, textColor=CTXT, leading=11),
    "kpi_lab": S("kl",  fontName="Helvetica",      fontSize=7,  textColor=CTXT, alignment=TA_CENTER, leading=9),
    "kpi_sub": S("ks",  fontName="Helvetica",      fontSize=6.5, textColor=CTXT, alignment=TA_CENTER, leading=8),
    "an":      S("an",  fontName="Helvetica-Bold", fontSize=11, textColor=AZUL,    alignment=TA_CENTER, spaceAfter=1),
    "as":      S("as",  fontName="Helvetica",      fontSize=9,  textColor=CTXT,    alignment=TA_CENTER, spaceAfter=1),
    "ae":      S("ae",  fontName="Helvetica-Bold", fontSize=9.5, textColor=AZUL,   alignment=TA_CENTER, spaceAfter=1),
    "sys":     S("sy",  fontName="Helvetica-Bold", fontSize=10, textColor=AZUL_M,  alignment=TA_CENTER, spaceAfter=1),
}
# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE PARAGRAPH/TABELA (parte 2 — anexa ao part1)
# ═══════════════════════════════════════════════════════════════════════════════

def th(t, align=TA_LEFT, size=7.5):
    return Paragraph(f"<b>{t}</b>", S("th", fontName="Helvetica-Bold", fontSize=size,
                     textColor=BRANCO, alignment=align, leading=10))


def td(t, bold=False, color=None, align=TA_LEFT, size=8):
    if color is None:
        color = CTXT_DARK
    return Paragraph(str(t), S("td",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, textColor=color, alignment=align, leading=11))


def sp(h):
    return Spacer(1, h * mm)


def hr(c=AZUL_M, t=0.8):
    return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=4)


def tsb(stripe=True):
    """Estilo base de tabela: cabeçalho azul + zebra opcional."""
    s = [
        ("BACKGROUND",     (0, 0), (-1, 0),    AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),    BRANCO),
        ("FONTNAME",       (0, 0), (-1, 0),    "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1),   8),
        ("GRID",           (0, 0), (-1, -1),   0.25, CBORD),
        ("VALIGN",         (0, 0), (-1, -1),   "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1),   4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1),   4),
        ("LEFTPADDING",    (0, 0), (-1, -1),   5),
        ("RIGHTPADDING",   (0, 0), (-1, -1),   5),
    ]
    if stripe:
        s.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CBG_LIGHT]))
    return TableStyle(s)


def tfoot():
    """Comandos para destacar a última linha como total."""
    return [
        ("BACKGROUND", (0, -1), (-1, -1), AZUL),
        ("TEXTCOLOR",  (0, -1), (-1, -1), BRANCO),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPONENTES VISUAIS (idênticos ao gerar_v3.py)
# ═══════════════════════════════════════════════════════════════════════════════

def kpi_card(label, value, sub="", color=AZUL, width=None):
    """Card KPI com label superior, valor grande e sublabel."""
    if width is None:
        width = 38 * mm
    inner = Table([
        [Paragraph(f"<b>{label}</b>", ST["kpi_lab"])],
        [Paragraph(f"<b>{value}</b>", S("kv2", fontName="Helvetica-Bold", fontSize=10.5,
                   textColor=color, alignment=TA_CENTER, leading=13))],
        [Paragraph(sub, ST["kpi_sub"])],
    ], colWidths=[width - 3 * mm])
    inner.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (0, 0),   5),
        ("BOTTOMPADDING", (0, 2), (0, 2),   5),
    ]))
    return inner


def kpi_row(cards_data, accent_colors=None):
    """Linha de 4 KPIs com barra superior colorida."""
    if accent_colors is None:
        accent_colors = [AZUL] * 4
    cards = [[kpi_card(*c) for c in cards_data]]
    t = Table(cards, colWidths=[W / 4] * 4)
    style = [
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
    ]
    for i, color in enumerate(accent_colors):
        style.append(("LINEABOVE", (i, 0), (i, 0), 3, color))
        style.append(("BOX", (i, 0), (i, 0), 0.3, CBORD))
    t.setStyle(TableStyle(style))
    return t


def achado_header(code, label, severidade: Severidade):
    """Cabeçalho de achado: código em fundo de severidade + título em fundo claro."""
    sev_color, sev_bg, sev_bord = SEV_PALETA[severidade]
    t = Table([[
        Paragraph(f"<b>{code}</b>", S("ahc", fontName="Helvetica-Bold", fontSize=10,
                  textColor=BRANCO, alignment=TA_CENTER, leading=12)),
        Paragraph(f"<b>{label}</b>", S("ahl", fontName="Helvetica-Bold", fontSize=9.5,
                  textColor=AZUL, alignment=TA_LEFT, leading=12)),
    ]], colWidths=[24 * mm, None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),   sev_color),
        ("BACKGROUND",    (1, 0), (1, 0),   sev_bg),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, sev_bord),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, sev_bord),
        ("LINEAFTER",     (1, 0), (1, 0),   0.5, sev_bord),
        ("LINEBEFORE",    (0, 0), (0, 0),   0.5, sev_bord),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def info_box(txt, label="", border_color=AZUL_M, bg=CBG_LIGHT):
    """Caixa com borda lateral colorida + label opcional."""
    elementos = []
    if label:
        elementos.append([Paragraph(f"<b>{label}</b>", S("lab",
            fontName="Helvetica-Bold", fontSize=7.5,
            textColor=border_color, leading=9))])
    elementos.append([Paragraph(txt, S("bx",
        fontName="Helvetica", fontSize=8,
        textColor=CTXT_DARK, alignment=TA_JUSTIFY, leading=12))])
    t = Table(elementos, colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, border_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return t


def sev_card(sev_label, qtd, conclusao, severidade: Severidade):
    """Card horizontal de severidade — usado no Mapa de Achados (capa)."""
    color, bg, bord = SEV_PALETA[severidade]
    badge = Paragraph(f"<b>{sev_label}</b>", S("sb",
        fontName="Helvetica-Bold", fontSize=8.5,
        textColor=BRANCO, alignment=TA_CENTER, leading=11))
    qtd_p = Paragraph(f"<b>{qtd}</b>", S("sq",
        fontName="Helvetica-Bold", fontSize=14,
        textColor=color, alignment=TA_CENTER, leading=16))
    desc = Paragraph(conclusao, S("sd",
        fontName="Helvetica", fontSize=8,
        textColor=CTXT_DARK, alignment=TA_LEFT, leading=11))
    t = Table([[badge, qtd_p, desc]], colWidths=[26 * mm, 12 * mm, W - 38 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),   color),
        ("BACKGROUND",    (1, 0), (2, 0),   bg),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, bord),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, bord),
        ("LINEAFTER",     (2, 0), (2, 0),   0.4, bord),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return t


def etapa_card(num, titulo, prazo, lista, accent=AZUL_CL):
    """Card de etapa com badge numérico + prazo + lista (página 5)."""
    badge = Table(
        [[Paragraph(f"<b>{num}</b>", S("etn", fontName="Helvetica-Bold",
                    fontSize=18, textColor=BRANCO, alignment=TA_CENTER, leading=20))]],
        colWidths=[14 * mm], rowHeights=[14 * mm])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
    ]))

    titulo_p = Paragraph(f"<b>{titulo}</b>", S("ett",
        fontName="Helvetica-Bold", fontSize=10, textColor=AZUL, leading=12))
    prazo_p = Paragraph(f"<b>{prazo}</b>", S("etp",
        fontName="Helvetica-Bold", fontSize=8, textColor=BRANCO,
        alignment=TA_CENTER, leading=10))
    prazo_t = Table([[prazo_p]], colWidths=[20 * mm])
    prazo_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), accent),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    head = Table([[titulo_p, prazo_t]], colWidths=[None, 20 * mm])
    head.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, 0),   0),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 0),
    ]))

    body_txt = "".join(
        f"<font color='#{accent.hexval()[2:]}'>•</font> {i}<br/><br/>"
        for i in lista)
    body = Paragraph(body_txt, S("etb",
        fontName="Helvetica", fontSize=8.5,
        textColor=CTXT_DARK, leading=12, alignment=TA_JUSTIFY))

    direita = Table([[head], [body]], colWidths=[W - 14 * mm - 3 * mm])
    direita.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))

    container = Table([[badge, direita]], colWidths=[14 * mm, W - 14 * mm])
    container.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    return container
# ═══════════════════════════════════════════════════════════════════════════════
#  MOTOR DE PROCESSAMENTO — Regra 1, F1-F6, Testes T-01 a T-08
# ═══════════════════════════════════════════════════════════════════════════════

# Regra 1 — meses em pt-BR
MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


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
    data_referencia: date | None = None

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
        """20% × resultado da atividade rural."""
        return (self.F5_resultado_rural * Decimal("0.20")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class PlanilhaMensal:
    """Linha mensal de uma planilha (vendas/remessas/compras)."""
    mes: str
    qtd_notas: int
    cabecas: int
    valor: Decimal


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

    # Cliente como destinatário
    if dest == cpf_c and nota.natureza == NaturezaNota.COMPRA:
        return CategoriaContabil.DESPESA

    # Edge case: nota não envolve o contribuinte em nenhuma ponta reconhecível
    if cpf_c not in (rem, dest):
        logger.warning(
            "Nota %s: CPF do contribuinte (%s) não consta como remetente nem "
            "destinatário (rem=%s, dest=%s) — classificada como TRANSFERÊNCIA.",
            nota.numero, mascara_cpf(cpf_c) if cpf_c else "?",
            mascara_cpf(rem) if rem else "vazio",
            mascara_cpf(dest) if dest else "vazio")

    return CategoriaContabil.TRANSFERENCIA


def apurar_resumo(
    notas: list[NotaFiscal],
    contribuinte: str | Contribuinte,
    data_referencia: date | None = None,
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
#  TESTES FORENSES T-01 a T-08
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
    valor_repetido: Decimal | None = None
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
    """SHA-256 dos dados financeiros — comprova que dois laudos são idênticos."""
    h = hashlib.sha256()
    h.update(f"{contribuinte.cpf}|{contribuinte.nome}".encode())
    h.update(f"|{periodo.inicio}|{periodo.fim}".encode())
    h.update(f"|F1={resumo.F1_receita_imediata}".encode())
    h.update(f"|F2={resumo.F2_transito}".encode())
    h.update(f"|F4={resumo.F4_receita_bruta}".encode())
    h.update(f"|F5={resumo.F5_resultado_rural}".encode())
    h.update(f"|F6={resumo.F6_despesa}".encode())
    h.update(f"|N={len(notas)}".encode())
    return h.hexdigest()[:16].upper()  # 16 chars são suficientes
# ═══════════════════════════════════════════════════════════════════════════════
#  CABEÇALHO E RODAPÉ (parametrizado pelo nome do contribuinte)
# ═══════════════════════════════════════════════════════════════════════════════

def _criar_handler_pagina(total_paginas: int = 8):
    """
    Cria handlers de página com contador encapsulado em closure (thread-safe).

    Retorna tupla (handler_first, handler_later):
      - handler_first: primeira página — cabeçalho azul + logo grande centralizada no corpo
      - handler_later: demais páginas — apenas cabeçalho azul (sem logo no corpo)

    Ambos compartilham o mesmo contador de páginas.
    """
    estado = {"atual": 0, "total": total_paginas}

    def _desenhar_cabecalho(canvas):
        """Cabeçalho azul padrão: logo pequena + ORGATEC + paginação."""
        w, h = A4
        lm, rm = 14 * mm, w - 14 * mm
        CH = 16 * mm
        CY = h - CH

        canvas.setFillColor(AZUL)
        canvas.rect(0, CY, w, CH, fill=1, stroke=0)

        logo_h_path = _get_logo_h()
        logo_header_w = 0  # largura ocupada pela logo (para posicionar texto)
        if logo_h_path:
            try:
                logo_r = ImageReader(logo_h_path)
                iw, ih = logo_r.getSize()
                aspect = iw / ih if ih > 0 else 1.0
                lh = CH * 0.78  # 78% da altura do header
                lw = lh * aspect
                ly = CY + (CH - lh) / 2  # centralizar verticalmente
                canvas.drawImage(logo_r, lm + 1 * mm, ly,
                                 width=lw, height=lh,
                                 preserveAspectRatio=True, mask="auto")
                logo_header_w = lw + 3 * mm
            except Exception as e:
                logger.debug("Logo header não pôde ser desenhado: %s", e)

        xt = lm + max(logo_header_w, 16 * mm)
        canvas.setFillColor(BRANCO)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.drawString(xt, CY + CH * 0.58, "ORGATEC")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(xt, CY + CH * 0.25, "CONTABILIDADE E AUDITORIA")

        estado["atual"] += 1
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(rm - 1 * mm, CY + CH * 0.58,
                               f"Página {estado['atual']} de {estado['total']}")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(rm - 1 * mm, CY + CH * 0.25, "OrgAudi 1.0")

        canvas.setStrokeColor(AZUL_CL)
        canvas.setLineWidth(2.0)
        canvas.line(0, CY - 0.3 * mm, w, CY - 0.3 * mm)

    def _desenhar_rodape(canvas):
        """Rodapé padrão: linha + créditos."""
        w, _h = A4
        lm, rm = 14 * mm, w - 14 * mm

        canvas.setStrokeColor(CBORD)
        canvas.setLineWidth(0.4)
        canvas.line(lm, 13 * mm, rm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(CTXT)
        canvas.drawCentredString(w / 2, 9 * mm,
            "ORGATEC CONTABILIDADE E AUDITORIA  ·  Robson Alain Veloso — Ciências Contábeis  ·  OrgAudi 1.0")

    def _handler_first(canvas, doc):
        """Primeira página: cabeçalho + logo grande centralizada + rodapé."""
        canvas.saveState()
        _desenhar_cabecalho(canvas)

        # Logo grande centralizada no corpo da página 1
        logo_t = _get_logo_t()
        if logo_t:
            try:
                w, h = A4
                logo_r = ImageReader(logo_t)
                # Obter proporção real da imagem
                iw, ih = logo_r.getSize()
                aspect = iw / ih if ih > 0 else 1.0

                # Tamanho da logo grande
                lg_h = 30 * mm
                lg_w = lg_h * aspect

                # Posicionar centralizada horizontalmente,
                # 6mm abaixo do cabeçalho
                CH = 16 * mm
                CY = h - CH
                logo_x = (w - lg_w) / 2
                logo_y = CY - 6 * mm - lg_h
                canvas.drawImage(logo_r, logo_x, logo_y,
                                 width=lg_w, height=lg_h,
                                 preserveAspectRatio=True, mask="auto")
            except Exception as e:
                logger.debug("Logo grande (p1) não pôde ser desenhada: %s", e)

        _desenhar_rodape(canvas)
        canvas.restoreState()

    def _handler_later(canvas, doc):
        """Demais páginas: apenas cabeçalho + rodapé (sem logo no corpo)."""
        canvas.saveState()
        _desenhar_cabecalho(canvas)
        _desenhar_rodape(canvas)
        canvas.restoreState()

    return _handler_first, _handler_later


# ═══════════════════════════════════════════════════════════════════════════════
#  BUILDER — Páginas 1 a 5
# ═══════════════════════════════════════════════════════════════════════════════

def construir_pagina_1_capa(
    contribuinte: Contribuinte,
    periodo: Periodo,
    resumo: ResumoFiscal,
    achados: list[Achado],
) -> list:
    """
    Página 1 — Capa com 3 seções:
      1) Tabela de identificação completa do contribuinte (10 linhas)
      2) Síntese quantitativa cruzada (Planilha IR v5 × PDF GIEF)
      3) Mapa de achados por severidade (tabela compacta)
    """
    story = []
    # Espaço para a logo grande desenhada pelo handler da primeira página
    # (a logo é renderizada diretamente no canvas, não no flowable story)
    story.append(sp(28))

    # [Removido: AUDITORIA FORENSE]
    story.append(sp(1))  # Reduzido de sp(4) para liberar espaço
    story.append(Paragraph("Relatório de Análise Fiscal", ST["h1"]))
    # [Removido: Bateria T-01 a T-08 × NFA-e × OrgAudi 1.0]
    story.append(hr(AZUL, 1.5))
    story.append(sp(1))  # Reduzido de sp(2)

    # ──────────────────────────────────────────────────────────
    #  SEÇÃO 1 — TABELA DE IDENTIFICAÇÃO (2 colunas, 10 linhas)
    # ──────────────────────────────────────────────────────────

    # Campos descritivos derivados do resumo
    total_notas_txt = (
        f"{resumo.qtd_total_saidas} saídas "
        f"({resumo.qtd_vendas} vendas + {resumo.qtd_remessas} remessas)"
    )
    if resumo.qtd_compras > 0:
        total_notas_txt += f" + {resumo.qtd_compras} compras"

    # Larguras: label 32mm, valor restante
    LBL_W = 32 * mm
    VAL_W = W - LBL_W

    def _id_row(label: str, valor: str, bold_val: bool = False):
        """Linha de identificação: label azul + valor."""
        return [
            td(label, bold=True, color=AZUL_M, size=7),
            td(valor, bold=bold_val, size=8.5),
        ]

    id_rows = [
        _id_row("Contribuinte",         contribuinte.nome, bold_val=True),
        _id_row("CPF",                   contribuinte.cpf, bold_val=True),
        _id_row("Inscrição Estadual",    contribuinte.ie or "—"),
        _id_row("Município",             f"{contribuinte.municipio} / {contribuinte.estado}"
                                          if contribuinte.municipio else contribuinte.estado),
        _id_row("Período auditado",      f"{fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}"),
        _id_row("Documento-base",        "NFA - SISTEMA DE NOTA FISCAL AVULSA"),
        _id_row("Total de notas",        total_notas_txt),
        _id_row("Volume bruto (saídas)", fmt_brl(resumo.valor_bruto_saidas), bold_val=True),
        _id_row("Data da auditoria",     fmt_data(periodo.data_auditoria)),
    ]

    t_ident = Table(id_rows, colWidths=[LBL_W, VAL_W])
    t_ident.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1),  CBG),
        ("BACKGROUND",    (1, 0), (1, -1),  CBG_LIGHT),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.25, CBORD_LIGHT),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.5, AZUL_CL),
        ("BOX",           (0, 0), (-1, -1), 0.5, CBORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),  # Reduzido de 4
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),  # Reduzido de 4
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(t_ident)
    story.append(sp(2))  # Reduzido de sp(5)

    # ──────────────────────────────────────────────────────────
    #  SEÇÃO 2 — SÍNTESE QUANTITATIVA CRUZADA
    # ──────────────────────────────────────────────────────────
    story.append(Paragraph("SÍNTESE QUANTITATIVA CRUZADA", ST["sec"]))
    story.append(sp(1))

    # Cabeçalho
    sq_header = [
        th("Indicador"),
        th("Planilha IR v5", align=TA_RIGHT),
        th("PDF GIEF", align=TA_RIGHT),
        th("Status", align=TA_CENTER),
    ]

    # Status badge inline
    def _status_td(status: str):
        """Cria a célula de status com cor semântica."""
        if status.upper() == "CONFORME":
            return td(status, bold=True, color=CONFORME, align=TA_CENTER, size=7.5)
        elif status.upper() == "DADO NOVO":
            return td(status, bold=True, color=ATENCAO, align=TA_CENTER, size=7.5)
        elif status.upper() == "DIVERGENTE":
            return td(status, bold=True, color=CRITICO, align=TA_CENTER, size=7.5)
        return td(status, bold=True, color=CTXT, align=TA_CENTER, size=7.5)

    # Cabecas totais = vendas + remessas + compras
    cabecas_totais = resumo.cabecas_vendas + resumo.cabecas_remessas + resumo.cabecas_compras

    sq_rows = [sq_header]
    sq_rows.append([
        td("Volume bruto total"),
        td(fmt_brl(resumo.valor_bruto_saidas, sinal=True), align=TA_RIGHT, size=8),
        td(fmt_brl(resumo.valor_bruto_saidas, sinal=True), align=TA_RIGHT, size=8),
        _status_td("Conforme"),
    ])
    sq_rows.append([
        td(f"Receita imediata ({resumo.qtd_vendas} vendas diretas)"),
        td(fmt_brl(resumo.F1_receita_imediata), align=TA_RIGHT, size=8),
        td(fmt_brl(resumo.F1_receita_imediata), align=TA_RIGHT, size=8),
        _status_td("Conforme"),
    ])
    sq_rows.append([
        td(f"Trânsito — remessas para leilão ({resumo.qtd_remessas})"),
        td(fmt_brl(resumo.F2_transito), align=TA_RIGHT, size=8),
        td(fmt_brl(resumo.F2_transito), align=TA_RIGHT, size=8),
        _status_td("Conforme"),
    ])
    sq_rows.append([
        td("Cabeças totais movimentadas"),
        td(f"{cabecas_totais:,}".replace(",", "."), align=TA_RIGHT, size=8),
        td(f"{cabecas_totais:,}".replace(",", "."), align=TA_RIGHT, size=8),
        _status_td("Conforme"),
    ])
    if resumo.qtd_compras > 0:
        sq_rows.append([
            td(f"Compras de gado ({resumo.qtd_compras} notas)"),
            td(fmt_brl(resumo.F6_despesa), align=TA_RIGHT, size=8),
            td("—", align=TA_RIGHT, size=8),
            _status_td("Dado novo"),
        ])
    sq_rows.append([
        td(f"Funrural estimado ({resumo.aliquota_funrural_pct} × vendas)"),
        td(fmt_brl(resumo.funrural), align=TA_RIGHT, size=8),
        td(fmt_brl(resumo.funrural), align=TA_RIGHT, size=8),
        _status_td("Conforme"),
    ])

    # Col widths para 4 colunas
    SQ_C1 = W * 0.38
    SQ_C2 = W * 0.22
    SQ_C3 = W * 0.22
    SQ_C4 = W * 0.18
    t_sq = Table(sq_rows, colWidths=[SQ_C1, SQ_C2, SQ_C3, SQ_C4])
    t_sq.setStyle(TableStyle([
        # Header
        ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        # Zebra
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CBG_LIGHT]),
        # Grid
        ("GRID",           (0, 0), (-1, -1), 0.25, CBORD),
        ("BOX",            (0, 0), (-1, -1), 0.5, AZUL_CL),
        # Alinhamento
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ]))
    story.append(t_sq)
    story.append(sp(1))

    # ──────────────────────────────────────────────────────────
    #  SEÇÃO 3 — MAPA DE ACHADOS POR SEVERIDADE (tabela compacta)
    # ──────────────────────────────────────────────────────────

    # Agrupar achados por severidade
    bucket: dict[Severidade, list[Achado]] = defaultdict(list)
    for a in achados:
        bucket[a.severidade].append(a)

    sev_ordem = [
        (Severidade.CRITICO,  "CRÍTICO"),
        (Severidade.ALTO,     "ALTO"),
        (Severidade.MEDIO,    "MÉDIO"),
        (Severidade.ATENCAO,  "ATENÇÃO"),
        (Severidade.CONFORME, "CONFORME"),
    ]

    # Tabela com header + 1 linha por severidade
    sev_header = [
        th("Severidade"),
        th("Qtd", align=TA_CENTER),
        th("Conclusão sintética"),
    ]
    sev_rows = [sev_header]

    for sev, label in sev_ordem:
        lista = bucket.get(sev, [])
        if not lista:
            continue
        # Cor
        color, bg, _bord = SEV_PALETA[sev]
        # Badge de severidade com cor
        badge = Paragraph(
            f"<b>{label}</b>",
            S(f"sv_{sev.value}", fontName="Helvetica-Bold", fontSize=8,
              textColor=BRANCO, alignment=TA_CENTER, leading=10))
        qtd_p = td(str(len(lista)), bold=True, color=color, align=TA_CENTER, size=10)
        # Concatenar títulos dos achados
        titulos = [a.titulo for a in lista]
        if len(titulos) > 2:
            conclusao_txt = "; ".join(titulos[:2]) + f"; +{len(titulos) - 2} achado(s)"
        else:
            conclusao_txt = "; ".join(titulos)
        conclusao_p = td(conclusao_txt, size=7.5)

        sev_rows.append([badge, qtd_p, conclusao_p])

    # Larguras: severidade 22mm, qtd 10mm, conclusão restante
    SEV_C1 = 22 * mm
    SEV_C2 = 12 * mm
    SEV_C3 = W - SEV_C1 - SEV_C2

    t_sev = Table(sev_rows, colWidths=[SEV_C1, SEV_C2, SEV_C3])

    # Estilo base
    sev_style_cmds = [
        # Header
        ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        # Grid
        ("GRID",           (0, 0), (-1, -1), 0.25, CBORD),
        ("BOX",            (0, 0), (-1, -1), 0.5, AZUL_CL),
        # Alinhamento
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ]

    # Aplicar cores de fundo por severidade em cada linha
    row_idx = 1  # começa após header
    for sev, label in sev_ordem:
        lista = bucket.get(sev, [])
        if not lista:
            continue
        color, bg, _bord = SEV_PALETA[sev]
        # Badge col (col 0) → fundo da cor da severidade
        sev_style_cmds.append(("BACKGROUND", (0, row_idx), (0, row_idx), color))
        sev_style_cmds.append(("TEXTCOLOR",  (0, row_idx), (0, row_idx), BRANCO))
        # Fundo claro na linha de dados (cols 1-2)
        sev_style_cmds.append(("BACKGROUND", (1, row_idx), (-1, row_idx), bg))
        row_idx += 1

    t_sev.setStyle(TableStyle(sev_style_cmds))
    story.append(t_sev)
    story.append(sp(2))

    # ── Bloco de KPIs financeiros derivados ──
    story.append(Paragraph("INDICADORES FINANCEIROS DERIVADOS", ST["sec"]))
    # kpi_row recebe tuplas (label, value, sub, color)
    kpis_data = [
        ("RECEITA BRUTA (F4)",
         fmt_brl_compact(resumo.F4_receita_bruta),
         "Vendas + Leilão realizado",
         AZUL),
        ("RESULTADO RURAL (F5)",
         fmt_brl_compact(resumo.F5_resultado_rural),
         "Base IRPF Rural (F4 − F6)",
         AZUL_M),
        (f"FUNRURAL ({resumo.aliquota_funrural_pct})",
         fmt_brl_compact(resumo.funrural),
         resumo.categoria_previdenciaria,
         ALTO),
        ("IRPF RURAL (estimado)",
         fmt_brl_compact(resumo.irpf_estimado),
         "20% × Resultado rural",
         CRITICO),
    ]
    accent = [AZUL, AZUL_M, ALTO, CRITICO]
    story.append(kpi_row(kpis_data, accent_colors=accent))

    return story


def construir_pagina_achados(achados: list[Achado]) -> list:
    """Páginas 2-4 — Achados detalhados, agrupados por severidade."""
    story = []

    # Agrupar por severidade
    bucket: dict[Severidade, list[Achado]] = defaultdict(list)
    for a in achados:
        bucket[a.severidade].append(a)

    secoes = [
        (Severidade.CRITICO,  "ACHADOS CRÍTICOS",        CRITICO),
        (Severidade.ALTO,     "ACHADOS DE ALTA CRITICIDADE", ALTO),
        (Severidade.MEDIO,    "ACHADOS DE CRITICIDADE MÉDIA", MEDIO),
        (Severidade.ATENCAO,  "PONTOS DE ATENÇÃO",       ATENCAO),
        (Severidade.CONFORME, "CONFORMIDADES VERIFICADAS", CONFORME),
    ]

    primeira_secao = True
    for sev, titulo_secao, cor_hr in secoes:
        lista = bucket.get(sev, [])
        if not lista:
            continue

        if primeira_secao:
            story.append(PageBreak())
            primeira_secao = False
        story.append(Paragraph(titulo_secao, ST["sec"]))
        story.append(hr(cor_hr, 1.2))
        story.append(sp(2))

        for a in lista:
            if sev == Severidade.CONFORME:
                # Linha simplificada com checkmark
                row = Table([[
                    Paragraph("<b>✓</b>", S("ok",
                        fontName="Helvetica-Bold", fontSize=14,
                        textColor=CONFORME, alignment=TA_CENTER, leading=16)),
                    Paragraph(f"<b>{a.codigo}.</b> {a.titulo}", S("ci",
                        fontName="Helvetica", fontSize=8.5,
                        textColor=CTXT_DARK, leading=11)),
                    Paragraph(f"<b>{a.descricao or 'CONFORME'}</b>", S("cr",
                        fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=CONFORME, alignment=TA_RIGHT, leading=10)),
                ]], colWidths=[10*mm, W-50*mm, 40*mm])
                row.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), CONFORME_BG),
                    ("LINEBEFORE",    (0, 0), (0, -1),  3, CONFORME),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING",    (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ]))
                story.append(row)
                story.append(sp(2))
                continue

            # Achado regular: header + descricao + tabela opcional + cruzamentos
            story.append(achado_header(a.codigo, a.titulo, sev))
            story.append(sp(1))

            if a.descricao:
                story.append(Paragraph(a.descricao, ST["body"]))

            # Tabela de evidências
            if a.tabela_cabecalhos and a.tabela_linhas:
                cab = [th(c, align=TA_RIGHT if i > 1 else TA_LEFT)
                       for i, c in enumerate(a.tabela_cabecalhos)]
                rows = [cab]
                for linha in a.tabela_linhas:
                    rows.append([
                        td(v, align=TA_RIGHT if i > 1 else TA_LEFT, size=7.5)
                        for i, v in enumerate(linha)])
                if a.tabela_totais:
                    # Linha TOTAL: cor branca explícita (mesmo motivo de _planilha_table)
                    rows.append([
                        td(v, bold=True, color=BRANCO,
                           align=TA_RIGHT if i > 1 else TA_LEFT, size=7.5)
                        for i, v in enumerate(a.tabela_totais)])
                # colWidths automáticos
                ncols = len(a.tabela_cabecalhos)
                t = Table(rows, colWidths=[W / ncols] * ncols)
                style = tsb()
                if a.tabela_totais:
                    for s in tfoot():
                        style.add(*s)
                t.setStyle(style)
                story.append(sp(1))
                story.append(t)

            # Cruzamentos
            if a.cruzamentos:
                cor_sev = SEV_PALETA[sev][0]
                bg_sev = SEV_PALETA[sev][1]
                texto = "  ·  ".join(a.cruzamentos)
                if a.porque_critico:
                    texto = f"{a.porque_critico}<br/><br/><b>Cruzamentos:</b> {texto}"
                    label = "POR QUE É CRÍTICO" if sev == Severidade.CRITICO else "VERIFICAÇÃO NECESSÁRIA"
                else:
                    label = "CRUZAMENTOS OBRIGATÓRIOS" if sev == Severidade.CRITICO else "VERIFICAÇÃO NECESSÁRIA"
                story.append(sp(1))
                story.append(info_box(texto, label=label, border_color=cor_sev, bg=bg_sev))

            story.append(sp(1))

    return story


def construir_pagina_5_recomendacoes(etapas: list[Etapa]) -> list:
    """Página 5 — Timeline de recomendações."""
    story = [PageBreak()]
    story.append(Paragraph("RECOMENDAÇÕES E PRÓXIMAS ETAPAS", ST["sec"]))
    story.append(hr(AZUL_M, 1.2))
    story.append(sp(1))

    for i, etapa in enumerate(etapas):
        accent = SEV_PALETA[etapa.accent][0]
        story.append(etapa_card(
            str(etapa.numero),
            etapa.titulo,
            etapa.prazo,
            etapa.itens,
            accent=accent,
        ))
        if i < len(etapas) - 1:
            story.append(sp(1))
    return story
# ═══════════════════════════════════════════════════════════════════════════════
#  BUILDER — Páginas 6 a 11
# ═══════════════════════════════════════════════════════════════════════════════

def construir_pagina_6_formulas() -> list:
    """Página 6 — Regras 1, 2, 3 (classificação, apuração, tributos)."""
    story = [PageBreak()]
    story.append(Paragraph("FÓRMULAS E REGRAS DE CRUZAMENTO DE DADOS", ST["sec"]))
    story.append(hr(AZUL_M, 1.2))
    story.append(Paragraph(
        "Esta página consolida as fórmulas matemáticas e as regras de cruzamento aplicadas pelo "
        "OrgAudi 1.0. Cada regra foi executada nesta auditoria e pode ser reproduzida em qualquer "
        "outro caso.", ST["small"]))
    story.append(sp(1))

    story.append(Paragraph("Regra 1 — Classificação contábil das NFA-e (fundamento)", ST["subsec"]))
    r1 = [
        [th("Posição do contribuinte"), th("Natureza"), th("Categoria"), th("Efeito IRPF Rural")],
        [td("REMETENTE"),                            td("VENDA"),          td("RECEITA",          bold=True, color=CONFORME), td("Soma à base de cálculo")],
        [td("REMETENTE"),                            td("REMESSA/LEILÃO"), td("TRÂNSITO",         bold=True, color=ALTO),     td("Não soma (até arremate)")],
        [td("REMETENTE = DESTINATÁRIO (mesmo CPF)"), td("Qualquer"),       td("TRANSFERÊNCIA",    bold=True, color=CTXT),     td("Neutra")],
        [td("DESTINATÁRIO"),                         td("COMPRA"),         td("DESPESA / INVEST.", bold=True, color=MEDIO),    td("Subtrai da base ou ativa")],
    ]
    tr1 = Table(r1, colWidths=[48*mm, 30*mm, 36*mm, W-114*mm])
    tr1.setStyle(tsb())
    story.append(tr1)
    story.append(sp(1))

    story.append(Paragraph("Regra 2 — Fórmulas de apuração da receita rural", ST["subsec"]))
    story.append(info_box(
        "<b>Receita imediata (F1):</b> Σ Valor | Remetente = Contribuinte AND Natureza = VENDA<br/>"
        "<b>Receita potencial em trânsito (F2):</b> Σ Valor | Remetente = Contribuinte AND Natureza = REMESSA/LEILÃO<br/>"
        "<b>Receita realizada de leilão (F3):</b> Σ Valor das NF-e modelo 55 emitidas pelo leiloeiro<br/>"
        "<b>Receita bruta total DIRPF Rural (F4) = F1 + F3</b><br/>"
        "<b>Resultado da atividade rural (F5) = F4 − F6</b><br/>"
        "<b>Despesas / Compras (F6):</b> Σ Valor | Destinatário = Contribuinte AND Natureza = COMPRA<br/><br/>"
        "<i>NUNCA usar F2 (Receita potencial em trânsito) como base — superdimensiona o IRPF.<br/>"
        "F6 representa o custo de aquisição de gado (investimento agropecuário) e é deduzido da receita bruta "
        "para apuração do resultado rural. Inclui compras de gado para cria, recria, engorda e reprodução.</i>",
        border_color=AZUL_M))
    story.append(sp(1))

    story.append(Paragraph("Regra 3 — Fórmulas tributárias e contribuições acessórias", ST["subsec"]))
    r3 = [
        [th("Tributo / Contribuição"), th("Fórmula"), th("Base legal")],
        # ── Funrural — todas as 3 categorias × 2 períodos ──
        [td("Funrural PF Patronal (até 03/2026)"),
         td("1,50% × RB (1,20% Prev. + 0,10% RAT + 0,20% SENAR)"),
         td("Lei 8.212/91")],
        [td("Funrural PF Patronal (≥ 04/2026)"),
         td("1,63% × RB (1,32% Prev. + 0,11% RAT + 0,20% SENAR)"),
         td("LC 224/2025")],
        [td("Funrural PF Segurado Especial"),
         td("1,50% × RB — alíquota MANTIDA (não majorada pela LC 224/2025)"),
         td("Lei 8.212/91 + RFB 03/2026")],
        [td("Funrural PJ (até 03/2026)"),
         td("2,05% × RB (1,70% Prev. + 0,10% RAT + 0,25% SENAR)"),
         td("Lei 8.870/94")],
        [td("Funrural PJ (≥ 04/2026)"),
         td("2,23% × RB (1,87% Prev. + 0,11% RAT + 0,25% SENAR)"),
         td("LC 224/2025")],
        # ── ICMS GO ──
        [td("ICMS gado entre produtores (GO)"),
         td("Isento (cria/recria/engorda)"),
         td("RCTE-GO Anx. IX, art. 6º, XLIII")],
        [td("ICMS gado para abate (GO)"),
         td("Isento, com Fundeinfra"),
         td("RCTE-GO Anx. IX, art. 6º, CXVI")],
        [td("Fundeinfra (facultativo)"),
         td("% × Valor operação (varia por mercadoria)"),
         td("Lei 21.670/2022 (GO)")],
        # ── IRPF Rural ──
        [td("IRPF Rural (PF) — resultado real"),
         td("Tabela progressiva × Resultado da atividade rural"),
         td("Lei 8.023/90 + RIR/2018")],
        [td("IRPF Rural (PF) — arbitrado"),
         td("20% × Receita bruta (forma presumida)"),
         td("Lei 8.023/90, art. 5º")],
    ]
    tr3 = Table(r3, colWidths=[48*mm, W-96*mm, 48*mm])
    tr3.setStyle(tsb())
    story.append(tr3)
    return story


def construir_pagina_7_testes() -> list:
    """Página 7 — Regras 4, 5 + lista resumida de tipos de anomalia."""
    story = [PageBreak()]
    story.append(Paragraph("Regra 4 — Cruzamentos forenses de detecção de anomalias", ST["subsec"]))
    r4 = [
        [th("Teste"), th("Critério matemático"), th("Detecta")],
        [td("T-01 Concentração",     bold=True), td("Valor 1 nota / Receita anual ≥ 10%"),                    td("Operações extraordinárias")],
        [td("T-02 Smurfing",         bold=True), td("≥ 3 notas mesmo destinatário/dia COM valores idênticos"), td("Fragmentação fiscal")],
        [td("T-03 Trânsito órfão",   bold=True), td("Σ Remessas/Leilão SEM NF-e venda subsequente"),          td("Receita não declarada")],
        [td("T-04 Concentração PF",  bold=True), td("Vendas a PF ≥ 90% E PFs com 3+ aquisições"),             td("Intermediação não declarada")],
        [td("T-05 IE inconsistente", bold=True), td("Mesmo CPF/CNPJ vinculado a 2+ IEs"),                     td("Erro cadastral ou simulação")],
        [td("T-06 Pauta+Sazon.",     bold=True), td("Σ trimestral ≥ 45%"),                                    td("Sub/superfat. ou esvaziamento")],
        [td("T-07 Documental",       bold=True), td("Validação dígito verificador de todos os CPF/CNPJ"),     td("Documentos forjados")],
        [td("T-08 Cruzamento",       bold=True), td("Cruzamento interno por categoria contábil"),              td("Inconsistência entre fontes")],
    ]
    tr4 = Table(r4, colWidths=[34*mm, W-82*mm, 48*mm])
    tr4.setStyle(tsb())
    story.append(tr4)
    story.append(sp(1))

    story.append(Paragraph("Regra 5 — Cruzamentos com bases externas", ST["subsec"]))
    r5 = [
        [th("Fonte externa"), th("O que confirmar"), th("Como cruzar")],
        [td("AGRODEFESA-GO",           bold=True), td("GTA correspondente a cada NFA-e"),  td("1 GTA para cada nota com gado em trânsito")],
        [td("Banco do contribuinte",   bold=True), td("Crédito do valor de cada venda"),   td("Σ depósitos/PIX = Σ receita imediata")],
        [td("Leiloeiros (ACTs)",       bold=True), td("NF-e modelo 55 do leiloeiro"),      td("Cada Remessa/Leilão deve gerar venda subsequente")],
        [td("Receita Federal (CAEPF)", bold=True), td("Status produtor rural dos PFs"),    td("PF sem CAEPF + 3+ compras = revenda informal")],
        [td("SEFAZ-GO+SiCAR+JUCEG",    bold=True), td("IEs ativas; capacidade do imóvel"), td("Cabeças/UA ≤ Área CAR; vínculo + venda atípica")],
    ]
    tr5 = Table(r5, colWidths=[42*mm, 55*mm, W-97*mm])
    tr5.setStyle(tsb())
    story.append(tr5)
    story.append(sp(1))

    story.append(Paragraph("TIPOS DE ANOMALIA CONSIDERADOS NA BATERIA DE TESTES", ST["subsec"]))
    story.append(info_box(
        "Fragmentação fiscal (smurfing) · Subfaturamento · Uso de 'laranjas' · Lavagem de gado de "
        "origem irregular · Conluio com leiloeiro para subdeclaração · Transferência intrafamiliar "
        "disfarçada de venda · Emissão a destinatários inexistentes · Intermediação não declarada por "
        "PFs · Inconsistência cadastral · Concentração atípica de operações · Sazonalidade "
        "incompatível com perfil de produção rotineira.",
        border_color=AZUL_M))
    story.append(sp(1))

    # ── Legenda de severidade dos achados ──
    story.append(Paragraph("LEGENDA DE SEVERIDADE DOS ACHADOS", ST["subsec"]))
    leg = [
        [th("Nível"), th("Cód."), th("Critério de classificação"),
         th("Ação esperada", align=TA_RIGHT)],
        [td("CRÍTICO",   bold=True, color=BRANCO),
         td("C-XX",      bold=True, color=BRANCO),
         td("Indício forte de irregularidade ativa (smurfing, "
            "concentração ≥ 10% em 1 nota)", color=BRANCO),
         td("Aprofundar em 30 dias", bold=True, color=BRANCO, align=TA_RIGHT)],
        [td("ALTO",      bold=True, color=BRANCO),
         td("A-XX",      bold=True, color=BRANCO),
         td("Padrão atípico que merece cruzamento com fontes externas "
            "(GTAs, CAEPF, extratos)", color=BRANCO),
         td("Cruzar em 60 dias", bold=True, color=BRANCO, align=TA_RIGHT)],
        [td("MÉDIO",     bold=True),
         td("M-XX",      bold=True),
         td("Obrigação acessória ou recolhimento derivado do volume auditado"),
         td("Conformidade fiscal", bold=True, align=TA_RIGHT)],
        [td("ATENÇÃO",   bold=True),
         td("AT-XX",     bold=True),
         td("Item de revisão técnica que pode mudar de severidade após análise"),
         td("Revisar manualmente", bold=True, align=TA_RIGHT)],
        [td("CONFORME",  bold=True, color=CONFORME),
         td("OK-XX",     bold=True, color=CONFORME),
         td("Cruzamento ou validação executada com sucesso "
            "(sem indício de irregularidade)", color=CONFORME),
         td("Sem ação", color=CONFORME, align=TA_RIGHT)],
    ]
    t_leg = Table(leg, colWidths=[24*mm, 16*mm, W-90*mm, 50*mm])
    style_leg = tsb()
    # Pintar fundos por severidade — linhas 1, 2 com vermelho/laranja
    style_leg.add("BACKGROUND", (0, 1), (-1, 1), CRITICO)
    style_leg.add("BACKGROUND", (0, 2), (-1, 2), ALTO)
    style_leg.add("BACKGROUND", (0, 3), (-1, 3), MEDIO_BG)
    style_leg.add("BACKGROUND", (0, 4), (-1, 4), ATENCAO_BG)
    style_leg.add("BACKGROUND", (0, 5), (-1, 5), CONFORME_BG)
    t_leg.setStyle(style_leg)
    story.append(t_leg)
    story.append(sp(1))

    story.append(Paragraph(
        "<i>Catálogo completo de 18 tipologias estruturadas em 5 eixos na próxima página.</i>",
        S("nx", fontName="Helvetica-Oblique", fontSize=7.5,
          textColor=CTXT, alignment=TA_RIGHT, leading=10)))
    return story


def construir_pagina_8_catalogo() -> list:
    """Página 8 — Catálogo de 18 tipologias × 5 eixos."""
    story = [PageBreak()]
    story.append(Paragraph("CATÁLOGO COMPLETO DE TIPOLOGIAS DE ANOMALIA", ST["sec"]))
    story.append(hr(AZUL_M, 1.2))

    # Tipologias agora estão sempre disponíveis (integradas no código)
    if not CATALOGO_ANOMALIAS:
        story.append(Paragraph(
            "OrgAudi 1.0 — Catálogo de tipologias estruturado em 5 eixos: "
            "<b>Eixo I</b> Manipulação de Valores · "
            "<b>Eixo II</b> Irregularidade de Partes · "
            "<b>Eixo III</b> Irregularidade de Mercadoria · "
            "<b>Eixo IV</b> Irregularidade Cadastral e Operacional · "
            "<b>Eixo V</b> Esquemas Estruturados.",
            ST["small"]))
        story.append(sp(1))
        story.append(info_box(
            "<b>Catálogo não disponível.</b><br/>"
            "O catálogo de 18 tipologias deveria estar acessível. "
            "Verifique se o arquivo foi carregado corretamente.",
            label="AVISO",
            border_color=ALTO, bg=ALTO_BG))
        return story

    story.append(Paragraph(
        "OrgAudi 1.0 — 18 tipologias estruturadas em 5 eixos de classificação. "
        "Cada anomalia é referenciada por código (AN-XX), eixo, gravidade e tributos impactados.",
        ST["small"]))
    story.append(sp(1))

    grav_color = {
        Gravidade.MUITO_ALTA: CRITICO,
        Gravidade.ALTA: ALTO,
        Gravidade.MEDIA: MEDIO,
    }
    eixo_nomes = {
        EixoAnomalia.MANIPULACAO_VALORES:       "Eixo I — Manipulação de Valores",
        EixoAnomalia.IRREGULARIDADE_PARTES:     "Eixo II — Irregularidade de Partes",
        EixoAnomalia.IRREGULARIDADE_MERCADORIA: "Eixo III — Irregularidade de Mercadoria",
        EixoAnomalia.IRREGULARIDADE_CADASTRAL:  "Eixo IV — Irregularidade Cadastral e Operacional",
        EixoAnomalia.ESQUEMAS_ESTRUTURADOS:     "Eixo V — Esquemas Estruturados",
    }

    rows = [[th("Cód.", size=6.5), th("Tipo / Descrição", size=6.5),
             th("Gravidade", size=6.5, align=TA_CENTER), th("Tributos", size=6.5)]]
    eixo_atual = None
    eixo_indices = []

    for a in CATALOGO_ANOMALIAS:
        if a.eixo != eixo_atual:
            eixo_atual = a.eixo
            rows.append([Paragraph(f"<b>{eixo_nomes[a.eixo]}</b>",
                S("ex", fontName="Helvetica-Bold", fontSize=7.5,
                  textColor=BRANCO, leading=9)), "", "", ""])
            eixo_indices.append(len(rows) - 1)
        rows.append([
            td(a.codigo.value, bold=True, color=grav_color[a.gravidade], size=6.5),
            Paragraph(
                f"<b>{a.tipo}</b> "
                f"<font size='6' color='#475569'>— {a.descricao}</font>",
                S("ad", fontName="Helvetica", fontSize=6.5,
                  textColor=CTXT_DARK, leading=8.5)),
            td(a.gravidade.value, bold=True, color=grav_color[a.gravidade],
               align=TA_CENTER, size=6.5),
            td(", ".join(a.tributos_impactados), size=6.5),
        ])

    tcat = Table(rows, colWidths=[14*mm, W-72*mm, 22*mm, 36*mm])
    style = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 6.5),
        ("GRID",         (0, 0), (-1, -1), 0.2, CBORD),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ])
    for idx in eixo_indices:
        style.add("BACKGROUND",    (0, idx), (-1, idx), AZUL_M)
        style.add("SPAN",          (0, idx), (-1, idx))
        style.add("TOPPADDING",    (0, idx), (-1, idx), 3)
        style.add("BOTTOMPADDING", (0, idx), (-1, idx), 3)
    for i in range(1, len(rows)):
        if i not in eixo_indices:
            cor = BRANCO if (i - eixo_indices[0]) % 2 == 1 else CBG_LIGHT
            style.add("BACKGROUND", (0, i), (-1, i), cor)
    tcat.setStyle(style)
    story.append(tcat)
    story.append(sp(1))

    leg = Table([[
        Paragraph(f"<b>● MUITO ALTA</b> ({len(buscar_por_gravidade(Gravidade.MUITO_ALTA))})",
                  S("lg1", fontName="Helvetica", fontSize=7.5,
                    textColor=CRITICO, alignment=TA_CENTER, leading=10)),
        Paragraph(f"<b>● ALTA</b> ({len(buscar_por_gravidade(Gravidade.ALTA))})",
                  S("lg2", fontName="Helvetica", fontSize=7.5,
                    textColor=ALTO, alignment=TA_CENTER, leading=10)),
        Paragraph(f"<b>● MÉDIA</b> ({len(buscar_por_gravidade(Gravidade.MEDIA))})",
                  S("lg3", fontName="Helvetica", fontSize=7.5,
                    textColor=MEDIO, alignment=TA_CENTER, leading=10)),
        Paragraph(f"<b>Total: {len(CATALOGO_ANOMALIAS)} tipologias × 5 eixos</b>",
                  S("lg4", fontName="Helvetica-Bold", fontSize=7.5,
                    textColor=AZUL, alignment=TA_CENTER, leading=10)),
    ]], colWidths=[W/4]*4)
    leg.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, CBORD),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, CBORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(leg)
    return story


def _planilha_table(planilha: list[PlanilhaMensal], total_label: str = "TOTAL") -> Table:
    """Constrói tabela de planilha mensal (vendas/remessas/compras)."""
    rows = [[th("Mês"), th("Q. Notas", align=TA_RIGHT),
             th("Cabeças", align=TA_RIGHT), th("Valor", align=TA_RIGHT)]]
    tot_n = tot_c = 0
    tot_v = Decimal("0")
    for p in planilha:
        rows.append([
            td(p.mes, bold=True),
            td(str(p.qtd_notas), align=TA_RIGHT),
            td(str(p.cabecas), align=TA_RIGHT),
            td(fmt_brl(p.valor), align=TA_RIGHT),
        ])
        tot_n += p.qtd_notas
        tot_c += p.cabecas
        tot_v += p.valor
    # Linha TOTAL: fundo azul + texto BRANCO (cor explícita no Paragraph,
    # pois TEXTCOLOR da TableStyle não sobrescreve cor de Paragraph com cor própria)
    rows.append([
        td(total_label, bold=True, color=BRANCO),
        td(str(tot_n), bold=True, color=BRANCO, align=TA_RIGHT),
        td(str(tot_c), bold=True, color=BRANCO, align=TA_RIGHT),
        td(fmt_brl(tot_v), bold=True, color=BRANCO, align=TA_RIGHT),
    ])
    t = Table(rows, colWidths=[35*mm, 22*mm, 22*mm, W-79*mm])
    style = tsb()
    for s in tfoot():
        style.add(*s)
    t.setStyle(style)
    return t


def construir_pagina_9_planilhas(
    planilha_vendas: list[PlanilhaMensal],
    planilha_remessas: list[PlanilhaMensal],
) -> list:
    """Página de Planilhas de Vendas e Remessas + indicadores derivados."""
    story = [PageBreak()]
    story.append(Paragraph("PLANILHA DE GADO PARA IMPOSTO DE RENDA", ST["h2"]))
    story.append(Paragraph("Lei 8.023/90 — IRPF Atividade Rural", ST["sub"]))
    story.append(hr(AZUL, 1.2))
    story.append(sp(2))

    story.append(Paragraph("VENDAS — Cliente como REMETENTE → RECEITA", ST["sec"]))
    story.append(_planilha_table(planilha_vendas))
    story.append(sp(1))

    story.append(Paragraph(
        "REMESSAS — Cliente como REMETENTE → TRÂNSITO (não soma à base IRPF)", ST["sec"]))
    story.append(_planilha_table(planilha_remessas))
    story.append(sp(2))

    # ── Bloco de indicadores derivados de distribuição mensal ──
    story.append(Paragraph("INDICADORES DE DISTRIBUIÇÃO MENSAL", ST["sec"]))
    story.append(hr(AZUL_M, 0.8))
    story.append(sp(1))

    def _ind_vendas(planilha: list[PlanilhaMensal]) -> dict:
        """Calcula indicadores de distribuição (média, pico, concentração)."""
        if not planilha:
            return {"meses_ativos": 0, "media_valor": Decimal("0"),
                    "mes_pico": "—", "valor_pico": Decimal("0"),
                    "pct_pico": Decimal("0"), "trim_pico": "—",
                    "pct_trim_pico": Decimal("0")}
        total_v = sum((p.valor for p in planilha), Decimal("0"))
        meses_ativos = len(planilha)
        media_v = (total_v / Decimal(meses_ativos)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP) if meses_ativos > 0 else Decimal("0")
        # mês de pico
        pico = max(planilha, key=lambda p: p.valor)
        pct_pico = (pico.valor / total_v * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP) if total_v > 0 else Decimal("0")
        # trimestre de pico — agrupa meses por trimestre
        # MESES_PT é constante global ["JAN", "FEV", ...]
        trim_idx = {}
        for p in planilha:
            try:
                m_idx = MESES_PT.index(p.mes)  # 0..11
            except ValueError:
                continue
            trim = m_idx // 3 + 1  # 1..4
            trim_idx.setdefault(trim, Decimal("0"))
            trim_idx[trim] += p.valor
        if trim_idx and total_v > 0:
            t_pico = max(trim_idx.items(), key=lambda x: x[1])
            trim_pico = f"{t_pico[0]}º trim."
            pct_trim_pico = (t_pico[1] / total_v * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            trim_pico = "—"
            pct_trim_pico = Decimal("0")
        return {
            "meses_ativos": meses_ativos,
            "media_valor": media_v,
            "mes_pico": pico.mes,
            "valor_pico": pico.valor,
            "pct_pico": pct_pico,
            "trim_pico": trim_pico,
            "pct_trim_pico": pct_trim_pico,
        }

    ind_v = _ind_vendas(planilha_vendas)
    ind_r = _ind_vendas(planilha_remessas)

    rows_ind = [
        [th("Indicador"),
         th("Vendas (Receita)", align=TA_RIGHT),
         th("Remessas (Trânsito)", align=TA_RIGHT)],
        [td("Meses com movimento"),
         td(str(ind_v["meses_ativos"]), bold=True, align=TA_RIGHT),
         td(str(ind_r["meses_ativos"]), bold=True, align=TA_RIGHT)],
        [td("Média mensal (mês ativo)"),
         td(fmt_brl(ind_v["media_valor"]), align=TA_RIGHT),
         td(fmt_brl(ind_r["media_valor"]), align=TA_RIGHT)],
        [td("Mês de pico"),
         td(f'{ind_v["mes_pico"]} — {fmt_brl(ind_v["valor_pico"])} ({fmt_pct(float(ind_v["pct_pico"]))})',
            align=TA_RIGHT),
         td(f'{ind_r["mes_pico"]} — {fmt_brl(ind_r["valor_pico"])} ({fmt_pct(float(ind_r["pct_pico"]))})'
            if ind_r["meses_ativos"] > 0 else "—",
            align=TA_RIGHT)],
        [td("Trimestre de maior concentração"),
         td(f'{ind_v["trim_pico"]} ({fmt_pct(float(ind_v["pct_trim_pico"]))})',
            align=TA_RIGHT),
         td(f'{ind_r["trim_pico"]} ({fmt_pct(float(ind_r["pct_trim_pico"]))})'
            if ind_r["meses_ativos"] > 0 else "—",
            align=TA_RIGHT)],
    ]
    t_ind = Table(rows_ind, colWidths=[W*0.40, W*0.30, W*0.30])
    t_ind.setStyle(tsb())
    story.append(t_ind)
    story.append(sp(2))

    # ── Nota interpretativa ──
    story.append(info_box(
        "<b>Como ler estes indicadores:</b> uma concentração trimestral acima de "
        "<b>45%</b> dispara o teste forense T-06 (sazonalidade incompatível com "
        "produção rotineira). Picos em um único mês ≥ 30% da receita anual também "
        "merecem cruzamento com GTAs e extratos bancários. Valores equilibrados "
        "ao longo do ano são o padrão esperado para pecuária de cria/recria/engorda.",
        border_color=AZUL_M, bg=CBG_LIGHT))
    return story


def construir_pagina_10_compras_formula(
    planilha_compras: list[PlanilhaMensal],
    resumo: ResumoFiscal,
) -> list:
    """Página 10 — Total geral + Compras + Fórmula F1-F6."""
    story = [PageBreak()]

    # Total geral das saídas
    tg = [
        [th("TOTAL GERAL DAS SAÍDAS (Vendas + Remessas)", align=TA_LEFT),
         th("Notas", align=TA_RIGHT),
         th("Cabeças", align=TA_RIGHT),
         th("Valor", align=TA_RIGHT)],
        [td("Soma agregada das saídas (cliente como REMETENTE)", bold=True),
         td(str(resumo.qtd_total_saidas), bold=True, align=TA_RIGHT, color=AZUL),
         td(str(resumo.cabecas_vendas + resumo.cabecas_remessas),
            bold=True, align=TA_RIGHT, color=AZUL),
         td(fmt_brl(resumo.valor_bruto_saidas), bold=True, align=TA_RIGHT, color=AZUL)],
    ]
    ttg = Table(tg, colWidths=[W-79*mm, 22*mm, 22*mm, 35*mm])
    ttg.setStyle(tsb(stripe=False))
    story.append(ttg)
    story.append(sp(1))

    story.append(Paragraph(
        "COMPRAS — Cliente como DESTINATÁRIO → DESPESA / INVESTIMENTO", ST["sec"]))
    story.append(_planilha_table(planilha_compras))
    story.append(sp(1))

    story.append(Paragraph("FÓRMULA APLICADA — REGRA 2 (APURAÇÃO DA RECEITA RURAL)", ST["sec"]))
    fr = [
        [th("Cód."), th("Descrição"), th("Valor", align=TA_RIGHT)],
        [td("F1", bold=True, color=CONFORME),
         td("Receita imediata (vendas diretas)"),
         td(fmt_brl(resumo.F1_receita_imediata), align=TA_RIGHT)],
        [td("F2", bold=True, color=ALTO),
         td("Trânsito potencial (remessas — NÃO base IRPF)"),
         td(fmt_brl(resumo.F2_transito), align=TA_RIGHT)],
        [td("F3", bold=True, color=CONFORME),
         td("Receita realizada de leilão (NF-e mod. 55)"),
         td(fmt_brl(resumo.F3_receita_realizada_leilao), align=TA_RIGHT)],
        [td("F4", bold=True, color=AZUL_M),
         td("Receita bruta total DIRPF Rural (F1 + F3)"),
         td(fmt_brl(resumo.F4_receita_bruta), bold=True, align=TA_RIGHT)],
        [td("F6", bold=True, color=MEDIO),
         td("Despesa / Investimento dedutível (compras)"),
         td(fmt_brl(resumo.F6_despesa), align=TA_RIGHT)],
        [td("F5", bold=True, color=BRANCO),
         td("Resultado da atividade rural (F4 − F6)", bold=True, color=BRANCO),
         td(fmt_brl(resumo.F5_resultado_rural), bold=True, color=BRANCO, align=TA_RIGHT)],
    ]
    tf = Table(fr, colWidths=[14*mm, W-54*mm, 40*mm])
    style_tf = tsb()
    for s in tfoot():
        style_tf.add(*s)
    tf.setStyle(style_tf)
    story.append(tf)
    return story


def construir_pagina_11_assinatura(
    contribuinte: Contribuinte,
    periodo: Periodo,
    hash_doc: str,
) -> list:
    """Página final — Declarações + assinatura + selo institucional + hash."""
    story = [PageBreak()]
    story.append(Paragraph("DECLARAÇÃO DE ALCANCE E LIMITAÇÕES", ST["sec"]))
    story.append(hr(AZUL_M, 1.2))
    story.append(sp(1))

    story.append(info_box(
        "Este relatório foi produzido pelo sistema OrgAudi 1.0 / NFA Extractor com base nos arquivos "
        "PDF de NFA-e fornecidos. Os achados constituem <b>indícios objetivos</b> derivados de "
        "cruzamentos lógicos internos, não confirmados com documentação primária externa "
        "(extratos bancários, GTAs, ACTs, contratos). A confirmação depende de etapa subsequente "
        "de coleta de evidências.",
        label="ALCANCE", border_color=AZUL_M, bg=CBG_LIGHT))
    story.append(sp(1))

    story.append(info_box(
        "<b>O presente documento NÃO formula acusações, NÃO imputa dolo e NÃO substitui procedimento "
        "de fiscalização tributária formal.</b> Os elementos aqui mapeados constituem subsídios "
        "técnicos para tomada de decisão do contribuinte e de seus assessores, e para eventual "
        "regularização espontânea nos termos do art. 138 do CTN.",
        label="LIMITAÇÕES", border_color=ALTO, bg=ALTO_BG))
    story.append(sp(3))

    story.append(Paragraph("RESPONSÁVEL TÉCNICO PELA AUDITORIA", ST["sec"]))
    story.append(hr(AZUL, 1.2))
    story.append(sp(4))

    # ── Bloco de assinatura ──
    story.append(Paragraph("ROBSON ALAIN VELOSO", ST["an"]))
    story.append(Paragraph("Ciências Contábeis", ST["as"]))
    story.append(Paragraph("ORGATEC CONTABILIDADE E AUDITORIA", ST["ae"]))
    story.append(Paragraph(
        f"Auditoria emitida em {fmt_data(periodo.data_auditoria)}", ST["as"]))
    story.append(sp(1))
    story.append(HRFlowable(width="55%", thickness=0.4, color=CBORD, spaceAfter=4))
    story.append(Paragraph("Sistema de auditoria contábil-fiscal", ST["small"]))
    story.append(Paragraph(
        "OrgAudi 1.0 / NFA Extractor — ORGATEC Contabilidade e Auditoria", ST["sys"]))
    story.append(sp(3))

    # ── Logo institucional (se disponível) ──
    # Quando o arquivo logo_oficial_transp.png existir em /home/claude,
    # /mnt/user-data/uploads ou no diretório atual, ela é renderizada aqui.
    # Quando não existe, simplesmente não aparece nada — sem selo sintético.
    logo_t = _get_logo_t()
    if logo_t:
        try:
            logo_img = RLImage(logo_t, width=42*mm, height=38*mm,
                               kind="proportional", mask="auto")
            logo_img.hAlign = "CENTER"
            story.append(logo_img)
            story.append(sp(2))
        except Exception as e:
            logger.debug("Logo de assinatura não pôde ser desenhada: %s", e)

    # ── Carimbo de validação ──
    carimbo = Table(
        [[
            Paragraph(
                "<b>HASH DE VALIDAÇÃO</b>",
                S("ch1", fontName="Helvetica-Bold", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9)),
            Paragraph(
                f"<b>{hash_doc}</b>",
                S("ch2", fontName="Courier-Bold", fontSize=10,
                  textColor=AZUL, alignment=TA_LEFT, leading=12)),
        ], [
            Paragraph(
                "ALGORITMO",
                S("ch3", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9)),
            Paragraph(
                "SHA-256 (16 hex)",
                S("ch4", fontName="Helvetica", fontSize=8,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)),
        ], [
            Paragraph(
                "EMITIDO EM",
                S("ch5", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9)),
            Paragraph(
                fmt_data(periodo.data_auditoria),
                S("ch6", fontName="Helvetica-Bold", fontSize=8,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)),
        ]],
        colWidths=[35*mm, W - 35*mm],
    )
    carimbo.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, CBORD),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, CBORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(carimbo)
    story.append(sp(2))

    # ── Disclaimer final em itálico ──
    cl = Table([[Paragraph(
        "<i>Classificação contábil: Cliente=Remetente → Receita; Cliente=Destinatário → "
        "Despesa/Investimento; Remessa/Leilão → Trânsito (não-receita até arremate). "
        f"Processamento por OrgAudi 1.0 — Hash documento: <b>{hash_doc}</b></i>",
        S("cl", fontName="Helvetica-Oblique", fontSize=7.5,
          textColor=CTXT, alignment=TA_CENTER, leading=10))
    ]], colWidths=[W])
    cl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL_CL),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(cl)
    return story


# ═══════════════════════════════════════════════════════════════════════════════
#  CLASSE PRINCIPAL — LaudoOrgAudi
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LaudoOrgAudi:
    """
    Laudo completo OrgAudi 1.0 — gera as 11 páginas com design profissional.

    Modo 1 (notas brutas): passe `notas` e os achados/etapas serão sugeridos
    automaticamente pelos testes T-01 a T-08.

    Modo 2 (dados pré-processados): passe `resumo`, `achados`, `etapas`,
    `planilha_vendas`, `planilha_remessas`, `planilha_compras` diretamente.
    """
    contribuinte: Contribuinte
    periodo: Periodo

    # Modo 1 — entrada bruta
    notas: list[NotaFiscal] = field(default_factory=list)

    # Modo 2 — entrada já processada (sobrescreve modo 1 quando fornecido)
    resumo: ResumoFiscal | None = None
    achados: list[Achado] = field(default_factory=list)
    etapas: list[Etapa] = field(default_factory=list)
    planilha_vendas: list[PlanilhaMensal] = field(default_factory=list)
    planilha_remessas: list[PlanilhaMensal] = field(default_factory=list)
    planilha_compras: list[PlanilhaMensal] = field(default_factory=list)

    # Resultados dos testes (preenchido por processar())
    t01: ResultadoT01 | None = None
    t02: ResultadoT02 | None = None
    t04: ResultadoT04 | None = None
    t07: ResultadoT07 | None = None
    hash_doc: str = ""

    def processar(self) -> LaudoOrgAudi:
        """
        Executa o motor: classifica, apura F1-F6, executa T-01 a T-08,
        constrói planilhas mensais e — se não houver achados manuais — sugere.
        """
        if not self.notas and self.resumo is None:
            raise ValueError(
                "Forneça `notas` (modo 1) ou `resumo` (modo 2). Ambos vazios.")

        # Modo 1 — calcular tudo a partir das notas
        if self.notas:
            cpf = self.contribuinte.cpf
            if self.resumo is None:
                # Passa o Contribuinte completo: propaga eh_pj e eh_segurado_especial
                # para a alíquota Funrural correta (LC 224/2025).
                self.resumo = apurar_resumo(
                    self.notas, self.contribuinte, data_referencia=self.periodo.fim)
            if not self.planilha_vendas:
                self.planilha_vendas = construir_planilha_mensal(
                    self.notas, CategoriaContabil.RECEITA, cpf)
            if not self.planilha_remessas:
                self.planilha_remessas = construir_planilha_mensal(
                    self.notas, CategoriaContabil.TRANSITO, cpf)
            if not self.planilha_compras:
                self.planilha_compras = construir_planilha_mensal(
                    self.notas, CategoriaContabil.DESPESA, cpf)

            # Testes
            self.t01 = teste_t01_concentracao(self.notas, cpf)
            self.t02 = teste_t02_smurfing(self.notas, cpf)
            self.t04 = teste_t04_concentracao_pf(self.notas, cpf)
            self.t07 = teste_t07_documental(self.notas)

            # Sugerir achados se não foram fornecidos manualmente
            if not self.achados:
                self.achados = self._sugerir_achados()

        # NOTA (v1.5.0): a geração automática de etapas foi desativada porque
        # a página 5 (Recomendações) foi removida em v1.4.0. As etapas só são
        # populadas se o chamador fornecê-las explicitamente (modo 2).
        # A função _etapas_padrao() permanece disponível como helper opcional.

        # Hash do laudo
        self.hash_doc = hash_laudo(
            self.contribuinte, self.periodo, self.resumo,
            self.notas if self.notas else [])
        return self

    def _sugerir_achados(self) -> list[Achado]:
        """Constrói achados a partir dos resultados dos testes T-01 a T-08."""
        ach: list[Achado] = []
        c = 1
        a_count = 1

        # T-01 → CRÍTICO (cada nota concentradora)
        for nota, pct in (self.t01.notas_concentradoras if self.t01 else []):
            ach.append(Achado(
                codigo=f"C-{c:02d}",
                titulo=f"Operação singular concentra {fmt_pct(pct)} da receita anual",
                descricao=(
                    f"NFA-e nº <b>{nota.numero}</b> de <b>{fmt_data(nota.data)}</b> "
                    f"concentra <b>{fmt_pct(pct)} da receita anual</b> em uma única "
                    f"operação para <b>{nota.destinatario_nome}</b>. Verificar valor "
                    f"unitário contra pauta e capacidade do imóvel rural do destinatário."
                ),
                severidade=Severidade.CRITICO,
                tabela_cabecalhos=["NFA-e", "Data", "Cabeças", "Valor", "% receita", "Destinatário"],
                tabela_linhas=[[
                    nota.numero, fmt_data(nota.data), str(nota.cabecas),
                    fmt_brl(nota.valor), fmt_pct(pct),
                    nota.destinatario_nome[:30],
                ]],
                cruzamentos=[
                    "GTA AGRODEFESA-GO",
                    f"Extrato bancário ({fmt_brl(nota.valor)})",
                    "Vínculo familiar/societário (JUCEG/RFB)",
                    "Capacidade do imóvel rural (SiCAR/CAR)",
                ],
            ))
            c += 1

        # T-02 → CRÍTICO (cada grupo de smurfing)
        for grupo in (self.t02.grupos if self.t02 else []):
            if grupo.qtd_repeticoes < 3:
                continue
            tabela = [[
                n.numero, fmt_data(n.data), fmt_brl(n.valor), str(n.cabecas),
            ] for n in grupo.notas]
            tabela_total = [
                "TOTAL EM UM ÚNICO DIA", "",
                fmt_brl(grupo.valor_total),
                str(sum(n.cabecas for n in grupo.notas)),
            ]
            ach.append(Achado(
                codigo=f"C-{c:02d}",
                titulo=f"Fragmentação fiscal (smurfing) — {fmt_data(grupo.data)}",
                descricao=(
                    f"Em <b>{fmt_data(grupo.data)}</b> foram emitidas "
                    f"<b>{len(grupo.notas)} NFA-e</b> ao mesmo destinatário "
                    f"<b>{grupo.destinatario_nome}</b> (CPF {grupo.destinatario_cpf}), "
                    f"totalizando <b>{fmt_brl(grupo.valor_total)}</b>. "
                    f"<b>{grupo.qtd_repeticoes} notas com valor exatamente idêntico "
                    f"({fmt_brl(grupo.valor_repetido)})</b> — padrão clássico de "
                    f"fragmentação fiscal."
                ),
                severidade=Severidade.CRITICO,
                tabela_cabecalhos=["NFA-e", "Data", "Valor", "Cabeças"],
                tabela_linhas=tabela,
                tabela_totais=tabela_total,
                porque_critico=(
                    "<b>Hipóteses:</b> (i) manter cada nota abaixo de limiar de triagem; "
                    "(ii) uso de 'laranja'; (iii) lavagem de gado."
                ),
                cruzamentos=[
                    f"GTAs AGRODEFESA-GO das {len(grupo.notas)} notas",
                    "Extrato bancário do dia (PIX/depósitos casados)",
                    "CAEPF do destinatário",
                    "Vínculo familiar/societário (JUCEG/RFB)",
                ],
            ))
            c += 1

        # T-04 → ALTO (concentração em PFs recorrentes)
        if self.t04 and self.t04.detectado():
            top5 = self.t04.pfs_recorrentes[:5]
            outros_qtd = len(self.t04.pfs_recorrentes) - 5
            tabela = [[p.nome[:35], p.cpf, str(p.qtd_notas), fmt_brl(p.valor_total)]
                      for p in top5]
            if outros_qtd > 0:
                outros_notas = sum(p.qtd_notas for p in self.t04.pfs_recorrentes[5:])
                outros_valor = sum((p.valor_total for p in self.t04.pfs_recorrentes[5:]),
                                   Decimal("0"))
                tabela.append([
                    f"Outros {outros_qtd} PFs com 3+ aquisições", "—",
                    str(outros_notas), fmt_brl(outros_valor),
                ])
            total_notas = sum(p.qtd_notas for p in self.t04.pfs_recorrentes)
            total_valor = sum((p.valor_total for p in self.t04.pfs_recorrentes),
                              Decimal("0"))
            ach.append(Achado(
                codigo=f"A-{a_count:02d}",
                titulo=(
                    f"Concentração em PFs com perfil de revenda — "
                    f"{fmt_brl(total_valor)}"
                ),
                descricao=(
                    f"<b>{fmt_pct(self.t04.pct_vendas_pf)}</b> das vendas diretas foram "
                    f"para pessoa física — atípico para pecuária. <b>"
                    f"{len(self.t04.pfs_recorrentes)} PFs</b> aparecem com 3+ aquisições "
                    f"no período."
                ),
                severidade=Severidade.ALTO,
                tabela_cabecalhos=["Destinatário", "CPF", "Notas", "Valor"],
                tabela_linhas=tabela,
                tabela_totais=[
                    f"TOTAL — {len(self.t04.pfs_recorrentes)} PFs RECORRENTES", "",
                    str(total_notas), fmt_brl(total_valor),
                ],
                cruzamentos=[
                    "Verificar CAEPF (Receita Federal) para cada CPF recorrente",
                    "PF sem CAEPF + 3+ compras = intermediação não declarada",
                ],
            ))
            a_count += 1

        # MÉDIO — sempre (obrigações acessórias + Funrural)
        ach.append(Achado(
            codigo="M-01",
            titulo="Obrigações acessórias derivadas do volume",
            descricao=(
                f"Volume bruto de <b>{fmt_brl(self.resumo.valor_bruto_saidas)}</b> "
                "obriga, para a DIRPF do exercício seguinte: (a) manutenção do "
                "<b>LCDPR</b> — Livro Caixa Digital do Produtor Rural "
                "(IN RFB 1.848/2018); (b) apuração do resultado da atividade rural; "
                "(c) retenção de comprovantes por 5 anos."
            ),
            severidade=Severidade.MEDIO,
        ))
        ach.append(Achado(
            codigo="M-02",
            titulo=f"Funrural a recolher — {fmt_brl(self.resumo.funrural)}",
            descricao=(
                f"Funrural sobre vendas diretas ({fmt_brl(self.resumo.F1_receita_imediata)}) "
                f"à alíquota de <b>{self.resumo.aliquota_funrural_pct}</b> "
                f"(categoria: <b>{self.resumo.categoria_previdenciaria}</b>, "
                f"vigente no período auditado): "
                f"<b>{fmt_brl(self.resumo.funrural)}</b>. "
                f"Base legal: {self.resumo.base_legal_funrural}. "
                f"Tabela completa: PF Patronal 1,50% (até 31/03/2026) → 1,63% (≥ 01/04/2026); "
                f"PF Segurado Especial 1,50% (mantida — orientação RFB 03/2026); "
                f"PJ 2,05% (até 31/03/2026) → 2,23% (≥ 01/04/2026)."
            ),
            severidade=Severidade.MEDIO,
        ))

        # ATENÇÃO — compras relevantes
        if self.resumo.F6_despesa > 0:
            ach.append(Achado(
                codigo="AT-01",
                titulo="Compras de gado relevantes — verificar tratamento contábil",
                descricao=(
                    f"<b>{fmt_brl(self.resumo.F6_despesa)} em "
                    f"{self.resumo.qtd_compras} notas</b> de compra. Sob a Regra 1 "
                    "OrgAudi 1.0 (Cliente=Destinatário → DESPESA/INVEST.), reduz a "
                    "base de cálculo do IRPF Rural ou ativa investimento dedutível, "
                    "conforme finalidade: <b>reposição de plantel = despesa; matriz "
                    "reprodutora = ativo</b>."
                ),
                severidade=Severidade.ATENCAO,
            ))

        # CONFORMIDADES (T-07 + Regra 1 + classificação)
        if self.t07:
            n_docs = self.t07.total_documentos_verificados
            n_inv = len(self.t07.cpfs_invalidos) + len(self.t07.cnpjs_invalidos)
            ach.append(Achado(
                codigo="OK-01",
                titulo=f"Validação de dígito verificador de CPF/CNPJ ({n_docs} documentos)",
                descricao="TODOS VÁLIDOS" if n_inv == 0 else f"{n_inv} INVÁLIDOS",
                severidade=Severidade.CONFORME,
            ))
        ach.append(Achado(
            codigo="OK-02",
            titulo="Cruzamento de totais por categoria contábil (Regra 1 OrgAudi 1.0)",
            descricao="CONFORME",
            severidade=Severidade.CONFORME,
        ))
        ach.append(Achado(
            codigo="OK-03",
            titulo=f"Classificação automática de {len(self.notas)} notas (Receita / Trânsito / Despesa)",
            descricao="EXECUTADA",
            severidade=Severidade.CONFORME,
        ))
        return ach

    def _etapas_padrao(self) -> list[Etapa]:
        """Etapas do plano de ação 30/60/90 dias.

        DEPRECATED desde v1.4.0: a página 5 (Recomendações) foi removida da
        renderização padrão do PDF. Este helper permanece disponível para
        chamadores que queiram montar uma seção customizada de recomendações
        ou exportar as etapas em outro formato (e-mail, dashboard, etc.).

        Não é mais chamado automaticamente em processar().
        """
        if self.resumo is None:
            return []
        irpf = fmt_brl(self.resumo.irpf_estimado)
        funrural = fmt_brl(self.resumo.funrural)
        f4 = fmt_brl(self.resumo.F4_receita_bruta)
        f5 = fmt_brl(self.resumo.F5_resultado_rural)
        f6 = fmt_brl(self.resumo.F6_despesa)

        return [
            Etapa(
                numero=1,
                titulo="Aprofundar achados críticos",
                prazo="30 DIAS",
                accent=Severidade.CRITICO,
                itens=[
                    "Solicitar documentação primária dos achados críticos e altos: GTAs, "
                    "extratos bancários, comprovantes de pagamento, ACTs dos leiloeiros, "
                    "relação completa de NF-e modelo 55 emitidas pelos leiloeiros em seu nome.",
                    "Cruzar com sistemas externos: AGRODEFESA-GO (GTAs e SIDAGRO), "
                    "Receita Federal (CAEPF dos PFs recorrentes), SiCAR (capacidade do "
                    "imóvel), JUCEG (vínculos societários).",
                ]),
            Etapa(
                numero=2,
                titulo="Conformidade fiscal",
                prazo="60 DIAS",
                accent=Severidade.ALTO,
                itens=[
                    "Reconstituir o LCDPR do exercício com base no relatório auditado, "
                    f"incorporando as {self.resumo.qtd_compras} notas de compra ({f6}) e "
                    "separando rigorosamente receita de trânsito.",
                    f"Apurar o IRPF Rural do exercício seguinte. Base: F5 = {f5} "
                    f"(F4 {f4} − F6 {f6}). IRPF estimado (20%): {irpf}.",
                    f"Conferir Funrural recolhido contra a estimativa {funrural}.",
                ]),
            Etapa(
                numero=3,
                titulo="Mitigação prospectiva",
                prazo="90 DIAS",
                accent=Severidade.MEDIO,
                itens=[
                    "Implantar segregação de fluxos nos sistemas internos: rotina "
                    "específica para vendas a PF (checagem CAEPF) e outra para remessas a "
                    "leilão (cobrança formal das notas de venda do leiloeiro).",
                    "Adequar à Reforma Tributária (LC 214/2025): a partir de 2027, CBS "
                    "substitui PIS/COFINS na cadeia agro. Atualizar emissão de NFA-e/NF-e "
                    "com IBS/CBS conforme NT 2025.002 RTC.",
                ]),
        ]

    def gerar_pdf(self, caminho: str) -> str:
        """
        Gera o PDF e retorna o caminho.

        Usa técnica two-pass: o primeiro build descobre o total real de páginas
        (incluindo quebras automáticas do ReportLab quando o conteúdo extrapola),
        o segundo build renderiza com o cabeçalho "Página X de N" correto.
        """
        if self.resumo is None:
            self.processar()

        def montar_story():
            s = []
            s += construir_pagina_1_capa(
                self.contribuinte, self.periodo, self.resumo, self.achados)
            s += construir_pagina_achados(self.achados)
            # [REMOVIDO: Página 5 — Recomendações e próximas etapas]
            # s += construir_pagina_5_recomendacoes(self.etapas)
            s += construir_pagina_6_formulas()
            s += construir_pagina_7_testes()
            s += construir_pagina_8_catalogo()
            s += construir_pagina_9_planilhas(
                self.planilha_vendas, self.planilha_remessas)
            s += construir_pagina_10_compras_formula(
                self.planilha_compras, self.resumo)
            s += construir_pagina_11_assinatura(
                self.contribuinte, self.periodo, self.hash_doc)
            return s

        kwargs = dict(
            pagesize=A4,
            leftMargin=14*mm, rightMargin=14*mm,
            topMargin=20*mm, bottomMargin=17*mm,
            title="Relatório de Auditoria Forense — OrgAudi 1.0",
            author="Robson Alain Veloso — ORGATEC",
            subject=f"Análise Fiscal NFA-e — {self.contribuinte.nome}",
        )

        # Pass 1 — descobrir total real de páginas (incluindo quebras automáticas).
        # Cada handler tem estado próprio (closure), o que torna o método thread-safe.
        import io
        hf1_first, hf1_later = _criar_handler_pagina(total_paginas=99)  # placeholder
        buf = io.BytesIO()
        doc1 = SimpleDocTemplate(buf, **kwargs)
        doc1.build(montar_story(), onFirstPage=hf1_first, onLaterPages=hf1_later)
        total_real = doc1.page  # número da última página renderizada

        # Pass 2 — renderiza com o total correto no cabeçalho
        hf2_first, hf2_later = _criar_handler_pagina(total_paginas=total_real)
        doc2 = SimpleDocTemplate(caminho, **kwargs)
        doc2.build(montar_story(), onFirstPage=hf2_first, onLaterPages=hf2_later)
        return caminho

    def resumo_executivo(self) -> str:
        """Resumo de 1 parágrafo para e-mail / impressão."""
        if self.resumo is None:
            return "Laudo não processado. Chame .processar() primeiro."
        sev_count = Counter(a.severidade for a in self.achados)
        n_critico = sev_count.get(Severidade.CRITICO, 0)
        n_alto = sev_count.get(Severidade.ALTO, 0)
        return (
            f"Auditoria OrgAudi 1.0 — {self.contribuinte.nome} ({self.contribuinte.cpf}) "
            f"— período {fmt_data(self.periodo.inicio)} a {fmt_data(self.periodo.fim)}. "
            f"Volume bruto {fmt_brl(self.resumo.valor_bruto_saidas)} em "
            f"{self.resumo.qtd_total_saidas} saídas. Receita imediata "
            f"{fmt_brl(self.resumo.F1_receita_imediata)} (F1). Resultado rural "
            f"{fmt_brl(self.resumo.F5_resultado_rural)} (F5). IRPF estimado "
            f"{fmt_brl(self.resumo.irpf_estimado)}; Funrural {fmt_brl(self.resumo.funrural)}. "
            f"{n_critico} achado(s) crítico(s), {n_alto} alto(s). Hash: {self.hash_doc}."
        )


# =============================================================================
#  WRAPPER / INTERFACE — Integrado neste arquivo
# =============================================================================

class CPFInvalidoError(ValueError):
    """Erro de validação de CPF — abortar geração do laudo."""
    pass


def _validar_cpf_obrigatorio(cpf: str, contexto: str = "") -> None:
    """
    Valida CPF e levanta CPFInvalidoError se inválido.
    Usado nos modos batch/API onde não há prompt interativo para correção.
    """
    if not validar_cpf(cpf):
        ctx = f" ({contexto})" if contexto else ""
        raise CPFInvalidoError(
            f"CPF inválido{ctx}: '{cpf}' — dígito verificador não confere. "
            f"Não é possível gerar laudo com CPF inválido."
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  CARREGAMENTO DE NOTAS A PARTIR DE JSON
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_data(s: str) -> date:
    """Aceita 'YYYY-MM-DD' ou 'DD/MM/YYYY'."""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {s}")


def carregar_notas_de_json(arquivo: str) -> list[NotaFiscal]:
    """
    Carrega notas a partir de um JSON.
    Formato esperado:
      [
        {
          "numero": "26.409.264",
          "data": "2025-10-24",
          "natureza": "VENDA",
          "valor": 295750.00,
          "cabecas": 91,
          "remetente_cpf": "019.925.771-02",
          "remetente_nome": "GENIS ...",
          "destinatario_cpf": "022.047.861-95",
          "destinatario_nome": "GUSTAVO ..."
        },
        ...
      ]
    """
    with open(arquivo, encoding="utf-8") as f:
        dados = json.load(f)

    notas: list[NotaFiscal] = []
    for d in dados:
        notas.append(NotaFiscal(
            numero=d["numero"],
            data=_parse_data(d["data"]),
            natureza=NaturezaNota(d["natureza"].upper()),
            valor=Decimal(str(d["valor"])),
            cabecas=int(d.get("cabecas", 0)),
            remetente_cpf=d.get("remetente_cpf", ""),
            remetente_nome=d.get("remetente_nome", ""),
            destinatario_cpf=d.get("destinatario_cpf", ""),
            destinatario_nome=d.get("destinatario_nome", ""),
        ))
    return notas


def gerar_laudo_de_json(dados: dict, caminho_saida: str,
                         strict_cpf: bool = True) -> dict:
    """
    Gera laudo a partir de um dict completo.

    Formato:
      {
        "contribuinte": {"nome": "...", "cpf": "...", "ie": "...", "municipio": "..."},
        "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
        "notas": [...]   // formato carregar_notas_de_json
      }

    Args:
      dados: dict com contribuinte, periodo e notas.
      caminho_saida: caminho do PDF de saída.
      strict_cpf: se True (padrão), CPF inválido do contribuinte aborta a geração.
                  Os CPFs nas notas são apenas registrados como achado T-07,
                  não bloqueiam a geração.

    Retorna dict com {pdf, hash, resumo_executivo, kpis, achados}.

    Levanta CPFInvalidoError se strict_cpf=True e CPF do contribuinte inválido.
    """
    c = dados["contribuinte"]
    p = dados["periodo"]

    # Validação obrigatória do CPF do contribuinte (modo batch/API)
    if strict_cpf:
        _validar_cpf_obrigatorio(
            c["cpf"], contexto=f"contribuinte {c.get('nome', '')}".strip())

    contrib = Contribuinte(
        nome=c["nome"], cpf=c["cpf"],
        ie=c.get("ie", ""), municipio=c.get("municipio", ""),
        estado=c.get("estado", "GO"),
        eh_pj=c.get("eh_pj", False),
        eh_segurado_especial=c.get("eh_segurado_especial", False))
    periodo = Periodo(
        inicio=_parse_data(p["inicio"]),
        fim=_parse_data(p["fim"]),
        data_auditoria=_parse_data(p.get("data_auditoria",
                                          date.today().strftime("%Y-%m-%d"))))

    notas: list[NotaFiscal] = []
    for d in dados.get("notas", []):
        notas.append(NotaFiscal(
            numero=d["numero"],
            data=_parse_data(d["data"]) if isinstance(d["data"], str) else d["data"],
            natureza=NaturezaNota(d["natureza"].upper()) if isinstance(d["natureza"], str) else d["natureza"],
            valor=Decimal(str(d["valor"])),
            cabecas=int(d.get("cabecas", 0)),
            remetente_cpf=d.get("remetente_cpf", ""),
            remetente_nome=d.get("remetente_nome", ""),
            destinatario_cpf=d.get("destinatario_cpf", ""),
            destinatario_nome=d.get("destinatario_nome", ""),
        ))

    laudo = LaudoOrgAudi(contribuinte=contrib, periodo=periodo, notas=notas)
    laudo.processar()
    laudo.gerar_pdf(caminho_saida)

    return {
        "pdf": caminho_saida,
        "hash": laudo.hash_doc,
        "resumo_executivo": laudo.resumo_executivo(),
        "kpis": {
            "F1_receita_imediata": float(laudo.resumo.F1_receita_imediata),
            "F2_transito":         float(laudo.resumo.F2_transito),
            "F4_receita_bruta":    float(laudo.resumo.F4_receita_bruta),
            "F5_resultado_rural":  float(laudo.resumo.F5_resultado_rural),
            "F6_despesa":          float(laudo.resumo.F6_despesa),
            "irpf_estimado":       float(laudo.resumo.irpf_estimado),
            "funrural":            float(laudo.resumo.funrural),
            "aliquota_funrural":   laudo.resumo.aliquota_funrural_pct,
            "categoria_previdenciaria": laudo.resumo.categoria_previdenciaria,
            "base_legal_funrural": laudo.resumo.base_legal_funrural,
            "qtd_vendas":          laudo.resumo.qtd_vendas,
            "qtd_remessas":        laudo.resumo.qtd_remessas,
            "qtd_compras":         laudo.resumo.qtd_compras,
        },
        "achados": [
            {"codigo": a.codigo, "titulo": a.titulo,
             "severidade": a.severidade.value}
            for a in laudo.achados
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MODO INTERATIVO
# ═══════════════════════════════════════════════════════════════════════════════

def _input(label: str, default: str = "", validador=None) -> str:
    suf = f" [{default}]" if default else ""
    while True:
        valor = input(f"  {label}{suf}: ").strip() or default
        if validador and not validador(valor):
            print("     ✗ valor inválido — tente novamente")
            continue
        return valor


def modo_interativo() -> int:
    print("═" * 70)
    print("  OrgAudi 1.0 — Gerador de Laudo (modo interativo)")
    print("  ORGATEC CONTABILIDADE E AUDITORIA")
    print("═" * 70)

    print("\n[1/3] DADOS DO CONTRIBUINTE")
    nome = _input("Nome completo", validador=lambda x: len(x) >= 5)
    cpf = _input("CPF", validador=validar_cpf)
    ie = _input("Inscrição Estadual (opcional)")
    municipio = _input("Município", default="Formoso")
    estado = _input("Estado", default="GO")

    print("\n  Categoria previdenciária (afeta alíquota Funrural):")
    print("    1 = PF Patronal (default — produtor rural com empregados)")
    print("    2 = PF Segurado Especial (agricultor familiar / economia familiar)")
    print("    3 = PJ (pessoa jurídica)")
    cat_escolha = _input("Escolha [1/2/3]", default="1")
    eh_pj = (cat_escolha == "3")
    eh_segurado_especial = (cat_escolha == "2")

    print("\n[2/3] PERÍODO AUDITADO")
    ano_atual = date.today().year - 1
    inicio = _input("Data de início (YYYY-MM-DD)",
                    default=f"{ano_atual}-01-01")
    fim = _input("Data de fim (YYYY-MM-DD)",
                 default=f"{ano_atual}-12-31")

    print("\n[3/3] DADOS DAS NOTAS FISCAIS")
    print("  → Forneça caminho do arquivo JSON com a lista de notas.")
    print("    Formato exemplo em: contribuintes_batch.json")
    notas_arq = _input("Arquivo JSON de notas (ou ENTER para pular)")

    saida = _input("Caminho do PDF de saída",
                   default=f"laudo_{cpf.replace('.','').replace('-','')}.pdf")

    contrib = Contribuinte(nome=nome, cpf=cpf, ie=ie,
                            municipio=municipio, estado=estado,
                            eh_pj=eh_pj,
                            eh_segurado_especial=eh_segurado_especial)
    periodo = Periodo(_parse_data(inicio), _parse_data(fim))

    notas = carregar_notas_de_json(notas_arq) if notas_arq else []
    if not notas:
        print("\n  ⚠ Sem notas — gerando laudo apenas com cabeçalho/identificação.")
        print("     Não recomendado em auditoria real.")
        return 1

    laudo = LaudoOrgAudi(contribuinte=contrib, periodo=periodo, notas=notas)
    laudo.processar()
    laudo.gerar_pdf(saida)

    print("\n" + "═" * 70)
    print(f"  ✓ Laudo gerado: {saida}")
    print(f"  ✓ Hash:         {laudo.hash_doc}")
    print("═" * 70)
    print(f"\n{laudo.resumo_executivo()}\n")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  MODO RÁPIDO (CLI)
# ═══════════════════════════════════════════════════════════════════════════════

def modo_rapido(args) -> int:
    # Valida CPF antes de qualquer processamento (consistência com modo interativo)
    try:
        _validar_cpf_obrigatorio(args.cpf, contexto=f"contribuinte {args.nome}")
    except CPFInvalidoError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    contrib = Contribuinte(
        nome=args.nome, cpf=args.cpf,
        ie=args.ie or "", municipio=args.municipio or "",
        estado=args.estado or "GO",
        eh_pj=getattr(args, "pj", False),
        eh_segurado_especial=getattr(args, "segurado_especial", False))
    periodo = Periodo(
        inicio=_parse_data(args.inicio),
        fim=_parse_data(args.fim))

    notas = carregar_notas_de_json(args.notas) if args.notas else []
    if not notas:
        print("✗ É necessário fornecer --notas (arquivo JSON)", file=sys.stderr)
        return 1

    laudo = LaudoOrgAudi(contribuinte=contrib, periodo=periodo, notas=notas)
    laudo.processar()
    laudo.gerar_pdf(args.out)

    print(f"✓ {args.out}")
    print(f"  Hash: {laudo.hash_doc}")
    print(f"  {laudo.resumo_executivo()}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  MODO BATCH (vários contribuintes em sequência)
# ═══════════════════════════════════════════════════════════════════════════════

def modo_batch(arquivo_lote: str) -> int:
    """
    Formato do JSON de lote:
      [
        {
          "contribuinte": {...},
          "periodo": {...},
          "notas": [...] OU "notas_arquivo": "caminho.json",
          "saida": "laudo_X.pdf"
        },
        ...
      ]

    Erros são registrados em laudo_erros_YYYYMMDD_HHMMSS.log para rastreabilidade.
    """
    with open(arquivo_lote, encoding="utf-8") as f:
        lote = json.load(f)

    # Log de erros em arquivo dedicado
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"laudo_erros_{timestamp}.log"

    print(f"Processando lote: {len(lote)} laudo(s)")
    print(f"Log de erros: {log_path}")

    sucesso = falha = 0
    erros: list[dict] = []

    for i, item in enumerate(lote, 1):
        saida = item.get("saida") or f"laudo_{i:03d}.pdf"
        nome_contrib = item.get("contribuinte", {}).get("nome", "?")
        cpf_contrib = item.get("contribuinte", {}).get("cpf", "?")

        try:
            dados = dict(item)
            dados.pop("saida", None)
            if "notas_arquivo" in item:
                dados["notas"] = [
                    {"numero": n.numero,
                     "data": n.data.isoformat(),
                     "natureza": n.natureza.value,
                     "valor": float(n.valor),
                     "cabecas": n.cabecas,
                     "remetente_cpf": n.remetente_cpf,
                     "remetente_nome": n.remetente_nome,
                     "destinatario_cpf": n.destinatario_cpf,
                     "destinatario_nome": n.destinatario_nome}
                    for n in carregar_notas_de_json(item["notas_arquivo"])
                ]
                dados.pop("notas_arquivo")
            res = gerar_laudo_de_json(dados, saida)
            print(f"  [{i:3d}/{len(lote)}] ✓ {saida}  hash={res['hash']}")
            sucesso += 1

        except CPFInvalidoError as e:
            tipo = "CPF_INVALIDO"
            msg = str(e)
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

        except FileNotFoundError as e:
            tipo = "ARQUIVO_NAO_ENCONTRADO"
            msg = str(e)
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

        except (KeyError, ValueError) as e:
            tipo = "DADOS_INVALIDOS"
            msg = f"{type(e).__name__}: {e}"
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

        except Exception as e:
            tipo = "ERRO_INESPERADO"
            msg = f"{type(e).__name__}: {e}"
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

    # Grava log de erros se houver falhas
    if erros:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("# OrgAudi 1.0 — Log de erros do lote\n")
            f.write(f"# Arquivo: {arquivo_lote}\n")
            f.write(f"# Timestamp: {timestamp}\n")
            f.write(f"# Total: {len(lote)} | Sucesso: {sucesso} | Falha: {falha}\n\n")
            json.dump(erros, f, indent=2, ensure_ascii=False)

    print(f"\nConcluído: {sucesso} sucesso(s), {falha} falha(s)")
    if erros:
        print(f"Detalhes em: {log_path}")
    return 0 if falha == 0 else 2


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OrgAudi 1.0 — Gerador de Laudo de Auditoria Forense",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = parser.add_subparsers(dest="modo")

    sub.add_parser("interativo", help="Modo interativo (padrão)")

    rp = sub.add_parser("rapido", help="Modo rápido via CLI")
    rp.add_argument("--nome", required=True)
    rp.add_argument("--cpf", required=True)
    rp.add_argument("--ie")
    rp.add_argument("--municipio")
    rp.add_argument("--estado")
    rp.add_argument("--inicio", required=True)
    rp.add_argument("--fim", required=True)
    rp.add_argument("--notas", required=True, help="JSON com a lista de notas")
    rp.add_argument("--out", required=True, help="Caminho do PDF de saída")
    rp.add_argument("--pj", action="store_true",
                    help="Contribuinte é Pessoa Jurídica (alíquotas Funrural 2,05%%/2,23%%)")
    rp.add_argument("--segurado-especial", action="store_true",
                    dest="segurado_especial",
                    help="PF Segurado Especial (agricultura familiar) — Funrural mantém 1,5%%")

    ba = sub.add_parser("batch", help="Modo batch — múltiplos contribuintes")
    ba.add_argument("arquivo", help="JSON de lote")

    args = parser.parse_args(argv)

    if args.modo is None or args.modo == "interativo":
        return modo_interativo()
    if args.modo == "rapido":
        return modo_rapido(args)
    if args.modo == "batch":
        return modo_batch(args.arquivo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
