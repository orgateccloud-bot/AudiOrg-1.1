"""Token Router — Roteamento inteligente de modelos por custo e complexidade.

Hierarquia de custo (Anthropic 2026):
  Haiku  $0.80/$4.00 por MTok (input/output)
  Sonnet $3.00/$15.00 por MTok
  Opus   $15.00/$75.00 por MTok

Política de roteamento:
  HAIKU   → tarefas simples: classificação, extração, roteamento, LGPD
  SONNET  → auditoria padrão: fiscal rural, ICMS, ITR, planejamento, jurídico
  OPUS    → análise rigorosa: score >= 85, >=3 tipologias criticas, prob. autuação >= 0.75
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


_MODELO_BASE: dict[TipoTarefa, ModelType] = {
    TipoTarefa.ROTEAMENTO:      ModelType.HAIKU,
    TipoTarefa.CLASSIFICACAO:   ModelType.HAIKU,
    TipoTarefa.EXTRACAO:        ModelType.HAIKU,
    TipoTarefa.LGPD:            ModelType.HAIKU,
    TipoTarefa.CONFORMIDADE:    ModelType.HAIKU,
    TipoTarefa.AUDITORIA:       ModelType.SONNET,
    TipoTarefa.ICMS:            ModelType.SONNET,
    TipoTarefa.ITR:             ModelType.SONNET,
    TipoTarefa.LCDPR:           ModelType.SONNET,
    TipoTarefa.PLANEJAMENTO:    ModelType.SONNET,
    TipoTarefa.JURIDICO:        ModelType.SONNET,
    TipoTarefa.ESOCIAL:         ModelType.SONNET,
    TipoTarefa.FORENSE:         ModelType.SONNET,
    TipoTarefa.PATRIMONIO:      ModelType.SONNET,
    TipoTarefa.FORENSE_CRITICO: ModelType.OPUS,
    TipoTarefa.DECISAO_FINAL:   ModelType.OPUS,
}

# Agente → TipoTarefa (para roteamento automático por agent_id)
_AGENTE_TAREFA: dict[str, TipoTarefa] = {
    "A-01": TipoTarefa.ROTEAMENTO,
    "A-06": TipoTarefa.EXTRACAO,
    "A-13": TipoTarefa.CONFORMIDADE,
    "A-16": TipoTarefa.LGPD,
    "A-24": TipoTarefa.CLASSIFICACAO,
    "A-07": TipoTarefa.FORENSE,
    "A-08": TipoTarefa.AUDITORIA,
    "A-09": TipoTarefa.CONFORMIDADE,
    "A-10": TipoTarefa.PATRIMONIO,
    "A-11": TipoTarefa.PLANEJAMENTO,
    "A-12": TipoTarefa.PLANEJAMENTO,
    "A-14": TipoTarefa.FORENSE,
    "A-15": TipoTarefa.JURIDICO,
    "A-17": TipoTarefa.PLANEJAMENTO,
    "A-18": TipoTarefa.PLANEJAMENTO,
    "A-19": TipoTarefa.PATRIMONIO,
    "A-20": TipoTarefa.ESOCIAL,
    "A-21": TipoTarefa.ICMS,
    "A-22": TipoTarefa.ITR,
    "A-23": TipoTarefa.FORENSE,
    "A-25": TipoTarefa.LCDPR,
    "A-26": TipoTarefa.PATRIMONIO,
    "A-27": TipoTarefa.FORENSE_CRITICO,
    "A-00": TipoTarefa.DECISAO_FINAL,
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

    # ── Escalada para Opus ────────────────────────────────────────────────────
    if modelo_base != ModelType.OPUS:
        if score_risco >= 85:
            return RotingDecision(
                modelo=ModelType.OPUS, tipo_tarefa=tipo_tarefa,
                motivo=f"Score critico {score_risco:.0f} >= 85 -> Opus",
                score_risco=score_risco, tipologias_criticas=tipologias_criticas,
                upgrade_aplicado=True,
            )
        if tipologias_criticas >= 3:
            return RotingDecision(
                modelo=ModelType.OPUS, tipo_tarefa=tipo_tarefa,
                motivo=f"{tipologias_criticas} tipologias criticas >= 3 -> Opus",
                score_risco=score_risco, tipologias_criticas=tipologias_criticas,
                upgrade_aplicado=True,
            )
        if probabilidade_autuacao >= 0.75:
            return RotingDecision(
                modelo=ModelType.OPUS, tipo_tarefa=tipo_tarefa,
                motivo=f"Prob. autuacao {probabilidade_autuacao:.0%} >= 75% -> Opus",
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


def estimar_tokens(texto: str) -> int:
    """Estimativa rápida: ~4 chars por token (sem chamar a API)."""
    return max(1, len(texto) // 4)
