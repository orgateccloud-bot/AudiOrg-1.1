"""
orgaudi.catalog
═══════════════
Catálogo de 18 tipologias forenses × 5 eixos de classificação.

Cada anomalia tem código (AN-XX), descrição, gravidade e os tributos típicos
que ela afeta. Os helpers de busca (`buscar_por_codigo`, `buscar_por_eixo`,
`buscar_por_gravidade`, `buscar_por_tributo`) permitem consulta direta sem
varrer o catálogo manualmente.

Sem dependências internas — só Enum/dataclass da stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


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
