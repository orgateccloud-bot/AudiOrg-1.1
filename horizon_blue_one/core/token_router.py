"""Token Router — Roteamento inteligente de modelos por custo e complexidade.

Hierarquia de custo (Anthropic 2026):
  Haiku  $0.80/$4.00 por MTok (input/output)
  Sonnet $3.00/$15.00 por MTok
  Opus   $15.00/$75.00 por MTok

Política de mix-alvo (rev 2026-05-09):
  HAIKU   80%  → roteamento, classificação, extração, LGPD, conformidade,
                 ICMS, ITR, LCDPR, planejamento tributário, eSocial,
                 patrimônio, contábil, deduções, fluxo de caixa, CFOP, etc.
  SONNET  15%  → trabalho intermediário com Claude: assurance, anomalias
                 AN-01..AN-18, forense de grafo, jurídico complexo
  OPUS     5%  → exclusivo para AUDITORIA (A-08 @Auditor-NFA) e
                 DECISÃO FINAL (A-00 @CEO). Nenhuma outra tarefa usa Opus.

Escalada para Opus (override do mix):
  - Tarefa AUDITORIA com score >= 85
  - Tarefa AUDITORIA com prob. autuação >= 0.75
  - 3+ tipologias críticas
  - Tipo FORENSE_CRITICO ou DECISAO_FINAL (sempre Opus)

Downgrade Sonnet→Haiku permanece quando o score for muito baixo (<25)
e o volume mínimo (<=5 notas) e tarefa não-forense.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import structlog

from horizon_blue_one.core.model_adapter import ModelType

logger = structlog.get_logger()

# ── Preços Anthropic 2026 (USD por 1M tokens) ─────────────────────────────────
_CUSTO_INPUT: dict[ModelType, float] = {
    ModelType.HAIKU:  0.80,
    ModelType.SONNET: 3.00,
    ModelType.OPUS:   15.00,
}
_CUSTO_OUTPUT: dict[ModelType, float] = {
    ModelType.HAIKU:  4.00,
    ModelType.SONNET: 15.00,
    ModelType.OPUS:   75.00,
}

# ── Tipos de Tarefa → Modelo Base ─────────────────────────────────────────────

class TipoTarefa(str, Enum):
    # Haiku — baixa complexidade
    ROTEAMENTO    = "roteamento"
    CLASSIFICACAO = "classificacao"
    EXTRACAO      = "extracao"
    LGPD          = "lgpd"
    CONFORMIDADE  = "conformidade"
    # Sonnet — complexidade padrão
    AUDITORIA     = "auditoria"
    ICMS          = "icms"
    ITR           = "itr"
    LCDPR         = "lcdpr"
    PLANEJAMENTO  = "planejamento"
    JURIDICO      = "juridico"
    ESOCIAL       = "esocial"
    FORENSE       = "forense"
    PATRIMONIO    = "patrimonio"
    # Opus — análise rigorosa (condicional por score/tipologias)
    FORENSE_CRITICO = "forense_critico"
    DECISAO_FINAL   = "decisao_final"


# ── Mix-alvo 80/15/5 (rev 2026-05-09) ────────────────────────────────────────
# 80% HAIKU — toda operação de baixa/média complexidade fica aqui.
# 15% SONNET — só os agentes que cruzam evidências (assurance, anomalias, grafo).
#  5% OPUS  — exclusivo para AUDITORIA (A-08) e DECISAO_FINAL (A-00).
_MODELO_BASE: dict[TipoTarefa, ModelType] = {
    # ── HAIKU (80%) — tarefas operacionais ────────────────────────────────────
    TipoTarefa.ROTEAMENTO:      ModelType.HAIKU,
    TipoTarefa.CLASSIFICACAO:   ModelType.HAIKU,
    TipoTarefa.EXTRACAO:        ModelType.HAIKU,
    TipoTarefa.LGPD:            ModelType.HAIKU,
    TipoTarefa.CONFORMIDADE:    ModelType.HAIKU,
    TipoTarefa.ICMS:            ModelType.HAIKU,
    TipoTarefa.ITR:             ModelType.HAIKU,
    TipoTarefa.LCDPR:           ModelType.HAIKU,
    TipoTarefa.PLANEJAMENTO:    ModelType.HAIKU,
    TipoTarefa.ESOCIAL:         ModelType.HAIKU,
    TipoTarefa.PATRIMONIO:      ModelType.HAIKU,
    # ── SONNET (15%) — raciocínio cruzado, não-final ─────────────────────────
    TipoTarefa.FORENSE:         ModelType.SONNET,   # A-07 / A-23 / A-27
    TipoTarefa.JURIDICO:        ModelType.SONNET,   # A-15
    # ── OPUS (5%) — auditoria + decisão final ────────────────────────────────
    TipoTarefa.AUDITORIA:       ModelType.OPUS,     # A-08 @Auditor-NFA
    TipoTarefa.FORENSE_CRITICO: ModelType.OPUS,     # escalada por critério
    TipoTarefa.DECISAO_FINAL:   ModelType.OPUS,     # A-00 @CEO
}


# ── max_tokens ótimo por agente (rev 2026-05-09) ─────────────────────────────
# Calibrado pelo tamanho real do JSON de saída de cada agente.
# Default: 512. Justificativa em comentário ao lado.
MAX_TOKENS_OTIMO: dict[str, int] = {
    # ── 10 tokens — só nome de agente destino ────────────────────────────────
    "A-01": 10,
    # ── 256 — output curto, OK/ERRO + motivo ─────────────────────────────────
    "A-02": 256, "A-03": 256, "A-04": 256, "A-09": 256, "A-13": 256,
    "A-14": 256, "A-16": 256,
    # ── 512 — JSON estruturado simples (5-8 chaves) ──────────────────────────
    "A-05": 512, "A-06": 512, "A-10": 512, "A-12": 512, "A-15": 512,
    "A-17": 512, "A-18": 512, "A-19": 512, "A-20": 512, "A-21": 512,
    "A-22": 512, "A-24": 512, "A-25": 512, "A-26": 512,
    # ── 1024 — JSON rico (assurance, anomalias) ──────────────────────────────
    "A-07": 1024, "A-11": 1024, "A-23": 1024, "A-27": 1024,
    # ── 1024 — auditoria completa ou decisão final (rev 2026-05-09 v2) ───────
    "A-08": 1024,                # NFAAuditSchema cabe em 1024 (era 2048)
    "A-00": 768,                 # decisão final compacta (era 1024)
    # ── 7 agentes consolidados S1..S7 (rev 2026-05-09 v3) ────────────────────
    "S1": 512,   # Sentinel: lgpd/zerotrust JSON simples
    "S2": 2048,  # Forense: narrativa + tipologias AN-XX (pode crescer)
    "S3": 2048,  # Fiscal: ICMS+ITR+LCDPR+CFOP agregado
    "S4": 1536,  # Contabil: CPC 29 + previsao caixa
    "S5": 1536,  # NFA: total + divergencias + amostra
    "S6": 1024,  # RH: eSocial S-1000..S-2240
    "S7": 2048,  # CEO: decisao + parecer juridico + MD&A
}


def max_tokens_para(agent_id: str | None, fallback: int = 1024) -> int:
    """Retorna max_tokens calibrado por agente, com fallback seguro."""
    return MAX_TOKENS_OTIMO.get(agent_id or "", fallback)

# Agente → TipoTarefa (rev 2026-05-09)
# Distribuição alvo: 22 Haiku · 4 Sonnet · 2 Opus = 78.6% / 14.3% / 7.1%
_AGENTE_TAREFA: dict[str, TipoTarefa] = {
    # ── HAIKU (22 agentes) ────────────────────────────────────────────────────
    "A-01": TipoTarefa.ROTEAMENTO,        # @Junior
    "A-02": TipoTarefa.CONFORMIDADE,      # @Protetor
    "A-03": TipoTarefa.CONFORMIDADE,      # @ZeroTrust
    "A-04": TipoTarefa.CONFORMIDADE,      # @Vigilante
    "A-05": TipoTarefa.EXTRACAO,          # @Engenheiro-ERP
    "A-06": TipoTarefa.EXTRACAO,          # @Extrator-Faturas
    "A-09": TipoTarefa.CONFORMIDADE,      # @Auditor-TI
    "A-10": TipoTarefa.PATRIMONIO,        # @Auditor-Patrimonio
    "A-11": TipoTarefa.PLANEJAMENTO,      # @Planejador-Tributario
    "A-12": TipoTarefa.PLANEJAMENTO,      # @Descobridor-Deducoes
    "A-13": TipoTarefa.CONFORMIDADE,      # @Monitor-Conformidade
    "A-14": TipoTarefa.CLASSIFICACAO,     # @Avaliador-Risco (downgrade Forense->Haiku)
    "A-16": TipoTarefa.LGPD,              # @LGPD
    "A-17": TipoTarefa.PLANEJAMENTO,      # @Previsor-Caixa
    "A-18": TipoTarefa.CLASSIFICACAO,     # @Analista-CSuite (resumo executivo curto)
    "A-19": TipoTarefa.PATRIMONIO,        # @Contabilista-IA
    "A-20": TipoTarefa.ESOCIAL,           # @Esocial-IA
    "A-21": TipoTarefa.ICMS,              # @Auditor-ICMS
    "A-22": TipoTarefa.ITR,               # @Auditor-ITR
    "A-24": TipoTarefa.CLASSIFICACAO,     # @Classificador-CFOP
    "A-25": TipoTarefa.LCDPR,             # @Auditor-LCDPR
    "A-26": TipoTarefa.PATRIMONIO,        # @Auditor-Biologicos
    # ── SONNET (4 agentes) ────────────────────────────────────────────────────
    "A-07": TipoTarefa.FORENSE,           # @Auditoria-Assurance (entrada do funil)
    "A-15": TipoTarefa.JURIDICO,          # @Juridico-Ext
    "A-23": TipoTarefa.FORENSE,           # @Analista-Anomalias AN-01..AN-18
    "A-27": TipoTarefa.FORENSE,           # @Epsilon (grafo) — Sonnet salvo escalada
    # ── Opus apenas em escalada (rev 2026-05-09 v2: máxima economia) ───────────
    # A-08 e A-00 default Sonnet; rotear() escala para Opus se score>=85,
    # tipologias>=3 ou prob_aut>=75% (controlado pela regra Sonnet→Opus existente).
    "A-08": TipoTarefa.FORENSE,           # @Auditor-NFA  → Sonnet base (escala Opus)
    "A-00": TipoTarefa.JURIDICO,          # @CEO          → Sonnet base (escala Opus)
    # ── 7 agentes consolidados S1..S7 (rev 2026-05-09 v3) ─────────────────────
    "S1": TipoTarefa.LGPD,                # @Sentinel  → Haiku
    "S2": TipoTarefa.FORENSE,             # @Forense   → Sonnet (Opus se score>=85)
    "S3": TipoTarefa.AUDITORIA,           # @Fiscal    → Sonnet
    "S4": TipoTarefa.AUDITORIA,           # @Contabil  → Sonnet
    "S5": TipoTarefa.AUDITORIA,           # @NFA       → Sonnet
    "S6": TipoTarefa.ESOCIAL,             # @RH        → Sonnet (Haiku via mix-alvo)
    "S7": TipoTarefa.JURIDICO,            # @CEO       → Sonnet (Opus se score>=85)
}


# ── Decisão de Roteamento ──────────────────────────────────────────────────────

@dataclass
class RotingDecision:
    modelo: ModelType
    tipo_tarefa: TipoTarefa
    motivo: str
    score_risco: float = 0.0
    tipologias_criticas: int = 0
    downgrade_aplicado: bool = False   # True se baixou de Sonnet para Haiku
    upgrade_aplicado: bool = False     # True se subiu para Opus


def rotear(
    tipo_tarefa: TipoTarefa,
    score_risco: float = 0.0,
    tipologias_criticas: int = 0,
    probabilidade_autuacao: float = 0.0,
    num_notas: int = 0,
    agent_id: Optional[str] = None,
) -> RotingDecision:
    """Decide o modelo ideal para a tarefa.

    Regras de escalada para Opus:
      - score_risco >= 85
      - tipologias_criticas >= 3
      - probabilidade_autuacao >= 0.75

    Regras de downgrade para Haiku:
      - score_risco < 25 E num_notas <= 5 E tarefa não é forense
    """
    # Resolver tipo_tarefa a partir do agent_id se não fornecido explicitamente
    if agent_id and agent_id in _AGENTE_TAREFA:
        tipo_tarefa = _AGENTE_TAREFA[agent_id]

    modelo_base = _MODELO_BASE.get(tipo_tarefa, ModelType.SONNET)

    # ── Escalada para Opus (só Sonnet→Opus; Haiku permanece Haiku) ───────────
    # Política: Opus é caro 5x Sonnet — só escalamos os agentes que JÁ são
    # Sonnet (raciocínio cruzado: A-07 assurance, A-23 anomalias, A-27 grafo,
    # A-15 jurídico). Os 22 Haiku ficam Haiku mesmo em cenário crítico —
    # quem decide o caso crítico no fim é A-08 (Opus) e A-00 (Opus).
    if modelo_base == ModelType.SONNET:
        if score_risco >= 85:
            return RotingDecision(
                modelo=ModelType.OPUS, tipo_tarefa=tipo_tarefa,
                motivo=f"Score critico {score_risco:.0f} >= 85 -> Opus (Sonnet escalado)",
                score_risco=score_risco, tipologias_criticas=tipologias_criticas,
                upgrade_aplicado=True,
            )
        if tipologias_criticas >= 3:
            return RotingDecision(
                modelo=ModelType.OPUS, tipo_tarefa=tipo_tarefa,
                motivo=f"{tipologias_criticas} tipologias criticas >= 3 -> Opus (Sonnet escalado)",
                score_risco=score_risco, tipologias_criticas=tipologias_criticas,
                upgrade_aplicado=True,
            )
        if probabilidade_autuacao >= 0.75:
            return RotingDecision(
                modelo=ModelType.OPUS, tipo_tarefa=tipo_tarefa,
                motivo=f"Prob. autuacao {probabilidade_autuacao:.0%} >= 75% -> Opus (Sonnet escalado)",
                score_risco=score_risco, tipologias_criticas=tipologias_criticas,
                upgrade_aplicado=True,
            )

    # ── Downgrade para Haiku ──────────────────────────────────────────────────
    if (modelo_base == ModelType.SONNET
            and score_risco < 25
            and num_notas <= 5
            and tipologias_criticas == 0
            and tipo_tarefa not in (TipoTarefa.FORENSE, TipoTarefa.FORENSE_CRITICO, TipoTarefa.DECISAO_FINAL)):
        return RotingDecision(
            modelo=ModelType.HAIKU, tipo_tarefa=tipo_tarefa,
            motivo=f"Score baixo {score_risco:.0f} + {num_notas} notas -> Haiku (downgrade)",
            score_risco=score_risco, tipologias_criticas=tipologias_criticas,
            downgrade_aplicado=True,
        )

    return RotingDecision(
        modelo=modelo_base, tipo_tarefa=tipo_tarefa,
        motivo=f"Modelo base para {tipo_tarefa.value}",
        score_risco=score_risco, tipologias_criticas=tipologias_criticas,
    )


# ── Estatísticas de Uso ────────────────────────────────────────────────────────

@dataclass
class _TokenStats:
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    chamadas:       dict[str, int]   = field(default_factory=dict)
    tokens_input:   dict[str, int]   = field(default_factory=dict)
    tokens_output:  dict[str, int]   = field(default_factory=dict)
    custo_usd:      dict[str, float] = field(default_factory=dict)
    economia_usd:   float            = 0.0   # vs tudo no Sonnet
    upgrades:       int              = 0
    downgrades:     int              = 0

    def registrar(
        self,
        modelo: ModelType,
        tokens_in: int,
        tokens_out: int,
        decision: RotingDecision,
    ) -> None:
        key = modelo.value
        custo = (
            tokens_in  * _CUSTO_INPUT.get(modelo,  0) +
            tokens_out * _CUSTO_OUTPUT.get(modelo, 0)
        ) / 1_000_000
        custo_sonnet = (
            tokens_in  * _CUSTO_INPUT[ModelType.SONNET] +
            tokens_out * _CUSTO_OUTPUT[ModelType.SONNET]
        ) / 1_000_000
        with self._lock:
            self.chamadas[key]      = self.chamadas.get(key, 0) + 1
            self.tokens_input[key]  = self.tokens_input.get(key, 0) + tokens_in
            self.tokens_output[key] = self.tokens_output.get(key, 0) + tokens_out
            self.custo_usd[key]     = self.custo_usd.get(key, 0.0) + custo
            self.economia_usd      += custo_sonnet - custo
            if decision.upgrade_aplicado:
                self.upgrades += 1
            if decision.downgrade_aplicado:
                self.downgrades += 1

    def resumo(self) -> dict:
        total_chamadas = sum(self.chamadas.values()) or 1
        total_custo    = sum(self.custo_usd.values())
        return {
            "chamadas_por_modelo": dict(self.chamadas),
            "distribuicao": {
                k: f"{v / total_chamadas * 100:.1f}%"
                for k, v in self.chamadas.items()
            },
            "tokens_totais": {
                "input":  sum(self.tokens_input.values()),
                "output": sum(self.tokens_output.values()),
            },
            "custo_total_usd":          round(total_custo, 6),
            "economia_vs_sonnet_usd":   round(self.economia_usd, 6),
            "economia_percentual":      f"{self.economia_usd / max(0.000001, total_custo + self.economia_usd) * 100:.1f}%",
            "upgrades_para_opus":       self.upgrades,
            "downgrades_para_haiku":    self.downgrades,
        }


# Singleton global de estatísticas
_stats = _TokenStats()


def registrar_uso(
    modelo: ModelType,
    tokens_in: int,
    tokens_out: int,
    decision: RotingDecision,
) -> None:
    """Registra uso real após a chamada ao modelo."""
    _stats.registrar(modelo, tokens_in, tokens_out, decision)
    logger.info(
        "token_router.uso",
        modelo=modelo.value,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        motivo=decision.motivo,
        upgrade=decision.upgrade_aplicado,
        downgrade=decision.downgrade_aplicado,
    )


def get_stats() -> dict:
    """Retorna estatísticas acumuladas de uso e custo."""
    return _stats.resumo()


def snapshot_stats() -> dict:
    """Cria deepcopy do estado atual de _TokenStats — útil para isolar
    medições entre PDFs em scripts de simulação. Não modifica o estado."""
    import copy
    with _stats._lock:
        return {
            "chamadas":      copy.deepcopy(_stats.chamadas),
            "tokens_input":  copy.deepcopy(_stats.tokens_input),
            "tokens_output": copy.deepcopy(_stats.tokens_output),
            "custo_usd":     copy.deepcopy(_stats.custo_usd),
            "economia_usd":  _stats.economia_usd,
            "upgrades":      _stats.upgrades,
            "downgrades":    _stats.downgrades,
            "resumo":        _stats.resumo(),
        }


def reset_stats() -> None:
    """Zera _TokenStats — usado entre PDFs/produtores na simulação."""
    with _stats._lock:
        _stats.chamadas.clear()
        _stats.tokens_input.clear()
        _stats.tokens_output.clear()
        _stats.custo_usd.clear()
        _stats.economia_usd = 0.0
        _stats.upgrades = 0
        _stats.downgrades = 0


def estimar_tokens(texto: str) -> int:
    """Estimativa rápida: ~4 chars por token (sem chamar a API)."""
    return max(1, len(texto) // 4)
