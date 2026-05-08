"""
═══════════════════════════════════════════════════════════════════════════════
  OrgAudi 1.0 — Catálogo de Tipologias de Anomalia
  ORGATEC CONTABILIDADE E AUDITORIA
═══════════════════════════════════════════════════════════════════════════════

18 tipologias estruturadas em 5 eixos forenses, cada uma classificada por
gravidade (MUITO_ALTA, ALTA, MEDIA) e tributos impactados.

Eixos:
  I   — Manipulação de Valores
  II  — Irregularidade de Partes
  III — Irregularidade de Mercadoria
  IV  — Irregularidade Cadastral e Operacional
  V   — Esquemas Estruturados
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EixoAnomalia(str, Enum):
    """Eixo forense de classificação da anomalia."""
    MANIPULACAO_VALORES       = "MANIPULACAO_VALORES"
    IRREGULARIDADE_PARTES     = "IRREGULARIDADE_PARTES"
    IRREGULARIDADE_MERCADORIA = "IRREGULARIDADE_MERCADORIA"
    IRREGULARIDADE_CADASTRAL  = "IRREGULARIDADE_CADASTRAL"
    ESQUEMAS_ESTRUTURADOS     = "ESQUEMAS_ESTRUTURADOS"


class Gravidade(str, Enum):
    """Nível de gravidade da anomalia."""
    MUITO_ALTA = "MUITO ALTA"
    ALTA       = "ALTA"
    MEDIA      = "MÉDIA"


class CodigoAnomalia(str, Enum):
    """Código único da anomalia (AN-XX)."""
    AN_01 = "AN-01"
    AN_02 = "AN-02"
    AN_03 = "AN-03"
    AN_04 = "AN-04"
    AN_05 = "AN-05"
    AN_06 = "AN-06"
    AN_07 = "AN-07"
    AN_08 = "AN-08"
    AN_09 = "AN-09"
    AN_10 = "AN-10"
    AN_11 = "AN-11"
    AN_12 = "AN-12"
    AN_13 = "AN-13"
    AN_14 = "AN-14"
    AN_15 = "AN-15"
    AN_16 = "AN-16"
    AN_17 = "AN-17"
    AN_18 = "AN-18"


@dataclass
class Anomalia:
    """Tipologia de anomalia catalogada."""
    codigo: CodigoAnomalia
    eixo: EixoAnomalia
    tipo: str
    descricao: str
    gravidade: Gravidade
    tributos_impactados: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
#  CATÁLOGO COMPLETO — 18 tipologias × 5 eixos
# ═══════════════════════════════════════════════════════════════════════════════

CATALOGO_ANOMALIAS: list[Anomalia] = [
    # ── Eixo I: Manipulação de Valores ────────────────────────────────────────
    Anomalia(
        codigo=CodigoAnomalia.AN_01,
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        tipo="Subfaturamento",
        descricao="Valor unitário abaixo da pauta fiscal estadual ou de mercado",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF", "Funrural"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_02,
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        tipo="Superfaturamento",
        descricao="Valor unitário acima do máximo razoável de mercado",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_03,
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        tipo="Concentração singular",
        descricao="Uma única operação concentra ≥ 10% da receita anual",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF", "Funrural"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_04,
        eixo=EixoAnomalia.MANIPULACAO_VALORES,
        tipo="Smurfing (fragmentação fiscal)",
        descricao="Múltiplas notas de valor idêntico no mesmo dia/destinatário",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF", "Funrural"],
    ),

    # ── Eixo II: Irregularidade de Partes ─────────────────────────────────────
    Anomalia(
        codigo=CodigoAnomalia.AN_05,
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        tipo="PF recorrente sem CAEPF",
        descricao="Pessoa física aparece como destinatária 3+ vezes (perfil de revenda)",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_06,
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        tipo="Concentração em PF (atípico para pecuária)",
        descricao="≥ 90% das vendas a pessoa física, padrão atípico",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_07,
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        tipo="Vínculo familiar/societário não declarado",
        descricao="Operação entre partes relacionadas sem destaque (RFB/JUCEG)",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_08,
        eixo=EixoAnomalia.IRREGULARIDADE_PARTES,
        tipo="CPF/CNPJ com dígito verificador inválido",
        descricao="Documento de parte com dígito DV incorreto (T-07)",
        gravidade=Gravidade.MEDIA,
        tributos_impactados=["ICMS", "Cadastro"],
    ),

    # ── Eixo III: Irregularidade de Mercadoria ────────────────────────────────
    Anomalia(
        codigo=CodigoAnomalia.AN_09,
        eixo=EixoAnomalia.IRREGULARIDADE_MERCADORIA,
        tipo="Capacidade do imóvel rural incompatível",
        descricao="Quantidade de cabeças supera lotação SiCAR/CAR do destinatário",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "ITR", "Funrural"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_10,
        eixo=EixoAnomalia.IRREGULARIDADE_MERCADORIA,
        tipo="Ausência de GTA correlata",
        descricao="NFA-e sem GTA AGRODEFESA-GO correspondente",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "Sanitário"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_11,
        eixo=EixoAnomalia.IRREGULARIDADE_MERCADORIA,
        tipo="Trânsito não-arrematado em leilão",
        descricao="Remessa para leiloeiro sem NF-e de retorno ou venda",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),

    # ── Eixo IV: Irregularidade Cadastral e Operacional ───────────────────────
    Anomalia(
        codigo=CodigoAnomalia.AN_12,
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        tipo="LCDPR não escriturado",
        descricao="Volume bruto exige Livro Caixa Digital do Produtor Rural",
        gravidade=Gravidade.MEDIA,
        tributos_impactados=["IRPF", "Cadastro"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_13,
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        tipo="DIRPF Rural omissa ou divergente",
        descricao="Resultado rural F5 não bate com o declarado em DIRPF",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["IRPF"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_14,
        eixo=EixoAnomalia.IRREGULARIDADE_CADASTRAL,
        tipo="Funrural não recolhido ou subdeclarado",
        descricao="Diferença entre Funrural calculado (1,5% × F1) e o efetivamente pago",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["Funrural", "Previdenciário"],
    ),

    # ── Eixo V: Esquemas Estruturados ─────────────────────────────────────────
    Anomalia(
        codigo=CodigoAnomalia.AN_15,
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        tipo="Lavagem de gado (gado fantasma)",
        descricao="Padrão de notas que não casam com fluxo bancário ou GTAs",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF", "Lavagem"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_16,
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        tipo="Uso de 'laranjas' (interpostas pessoas)",
        descricao="PFs sem capacidade econômica como destinatários recorrentes",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF", "Lavagem"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_17,
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        tipo="Triangulação fictícia",
        descricao="Operações em cadeia com mesmo gado, sem trânsito físico real",
        gravidade=Gravidade.MUITO_ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),
    Anomalia(
        codigo=CodigoAnomalia.AN_18,
        eixo=EixoAnomalia.ESQUEMAS_ESTRUTURADOS,
        tipo="Reciclagem de notas (cancelamento abusivo)",
        descricao="Notas canceladas e reemitidas com valores divergentes",
        gravidade=Gravidade.ALTA,
        tributos_impactados=["ICMS", "IRPF"],
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE BUSCA
# ═══════════════════════════════════════════════════════════════════════════════

def buscar_por_eixo(eixo: EixoAnomalia) -> list[Anomalia]:
    """Filtra o catálogo pelo eixo informado."""
    return [a for a in CATALOGO_ANOMALIAS if a.eixo == eixo]


def buscar_por_gravidade(gravidade: Gravidade) -> list[Anomalia]:
    """Filtra o catálogo pela gravidade informada."""
    return [a for a in CATALOGO_ANOMALIAS if a.gravidade == gravidade]


def buscar_por_codigo(codigo: str | CodigoAnomalia) -> Anomalia | None:
    """Retorna a anomalia pelo código (AN-01..AN-18)."""
    cod = codigo.value if isinstance(codigo, CodigoAnomalia) else codigo
    for a in CATALOGO_ANOMALIAS:
        if a.codigo.value == cod:
            return a
    return None
