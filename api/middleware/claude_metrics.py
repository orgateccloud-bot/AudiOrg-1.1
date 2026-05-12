"""Métricas Prometheus de uso e custo do Claude.

Subscreve em `horizon_blue_one.core.token_router.adicionar_listener` e publica:

- claude_calls_total{modelo}                  — Counter de chamadas por modelo
- claude_tokens_total{modelo,direcao}         — Counter input/output tokens
- claude_cost_usd_total{modelo}               — Counter custo acumulado USD
- claude_routing_total{decisao}               — Counter upgrade/downgrade/base
- claude_output_saturation_ratio{modelo}      — Histogram output/max_tokens
- claude_economia_vs_sonnet_usd_total         — Counter economia vs tudo-Sonnet

O módulo é importado por `api/main.py` no boot para registrar o listener.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

from horizon_blue_one.core.model_adapter import ModelType
from horizon_blue_one.core.token_router import (
    RotingDecision,
    adicionar_listener,
)

# ── Tabelas de preço (espelho de token_router para cálculo isolado) ──────────
_CUSTO_INPUT_USD_PER_MTOK: dict[ModelType, float] = {
    ModelType.HAIKU:  0.80,
    ModelType.SONNET: 3.00,
    ModelType.OPUS:   15.00,
}
_CUSTO_OUTPUT_USD_PER_MTOK: dict[ModelType, float] = {
    ModelType.HAIKU:  4.00,
    ModelType.SONNET: 15.00,
    ModelType.OPUS:   75.00,
}

# ── Métricas ─────────────────────────────────────────────────────────────────

CLAUDE_CALLS_TOTAL = Counter(
    "claude_calls_total",
    "Total de chamadas ao Claude por modelo.",
    ["modelo"],
)

CLAUDE_TOKENS_TOTAL = Counter(
    "claude_tokens_total",
    "Tokens consumidos pelo Claude por modelo e direção.",
    ["modelo", "direcao"],  # direcao = input | output
)

CLAUDE_COST_USD_TOTAL = Counter(
    "claude_cost_usd_total",
    "Custo acumulado em USD por modelo.",
    ["modelo"],
)

CLAUDE_ROUTING_TOTAL = Counter(
    "claude_routing_total",
    "Decisões de roteamento (upgrade/downgrade/base).",
    ["decisao"],
)

CLAUDE_OUTPUT_SATURATION = Histogram(
    "claude_output_saturation_ratio",
    "Razão output_tokens / max_tokens — próximo a 1.0 indica truncamento.",
    ["modelo"],
    buckets=(0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0),
)

CLAUDE_ECONOMIA_VS_SONNET = Counter(
    "claude_economia_vs_sonnet_usd_total",
    "Economia acumulada em USD comparando ao custo de tudo em Sonnet.",
)


def _publicar(
    modelo: ModelType,
    tokens_in: int,
    tokens_out: int,
    decision: RotingDecision,
    max_tokens: int | None,
    agent_id: str | None,
) -> None:
    # `agent_id` é parte do contrato do listener; reservado para futura métrica
    # por agente. Não é usado neste corpo, mas a assinatura deve ser preservada.
    del agent_id
    """Listener registrado em `token_router.adicionar_listener`."""
    modelo_label = modelo.value
    CLAUDE_CALLS_TOTAL.labels(modelo=modelo_label).inc()
    CLAUDE_TOKENS_TOTAL.labels(modelo=modelo_label, direcao="input").inc(tokens_in)
    CLAUDE_TOKENS_TOTAL.labels(modelo=modelo_label, direcao="output").inc(tokens_out)

    custo = (
        tokens_in  * _CUSTO_INPUT_USD_PER_MTOK.get(modelo,  0.0) +
        tokens_out * _CUSTO_OUTPUT_USD_PER_MTOK.get(modelo, 0.0)
    ) / 1_000_000
    if custo > 0:
        CLAUDE_COST_USD_TOTAL.labels(modelo=modelo_label).inc(custo)

    custo_se_sonnet = (
        tokens_in  * _CUSTO_INPUT_USD_PER_MTOK[ModelType.SONNET] +
        tokens_out * _CUSTO_OUTPUT_USD_PER_MTOK[ModelType.SONNET]
    ) / 1_000_000
    economia = custo_se_sonnet - custo
    if economia > 0:
        CLAUDE_ECONOMIA_VS_SONNET.inc(economia)

    if decision.upgrade_aplicado:
        CLAUDE_ROUTING_TOTAL.labels(decisao="upgrade_opus").inc()
    elif decision.downgrade_aplicado:
        CLAUDE_ROUTING_TOTAL.labels(decisao="downgrade_haiku").inc()
    else:
        CLAUDE_ROUTING_TOTAL.labels(decisao="base").inc()

    if max_tokens and max_tokens > 0:
        CLAUDE_OUTPUT_SATURATION.labels(modelo=modelo_label).observe(
            min(tokens_out / max_tokens, 1.0)
        )


# Registro automático no import — `api/main.py` deve importar este módulo.
adicionar_listener(_publicar)
