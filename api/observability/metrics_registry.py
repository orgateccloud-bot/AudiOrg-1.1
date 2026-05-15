"""Registro central de métricas Prometheus do OrgAudi.

Define o ``CollectorRegistry`` e as 4 métricas-base previstas na Issue #25:

* ``orgaudi_laudos_total``           — Counter de laudos gerados (label: status)
* ``orgaudi_laudo_duration_seconds`` — Histogram de duração de laudo (p95 derivado)
* ``orgaudi_errors_5xx_total``       — Counter de erros 5xx (label: route)
* ``orgaudi_token_cost_total``       — Counter de custo cumulativo de tokens (label: provider)

Esta etapa (1/N) APENAS REGISTRA as métricas. Instrumentação ativa virá em
PRs subsequentes (services, middleware, ai_client).
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

# Registry dedicado — não usa o default global, para evitar colisões em testes
# e permitir múltiplas instâncias em servidores que usam threading.
REGISTRY: CollectorRegistry = CollectorRegistry()

LAUDOS_TOTAL = Counter(
    "orgaudi_laudos_total",
    "Total de laudos NFA-e gerados pelo OrgAudi.",
    labelnames=("status",),
    registry=REGISTRY,
)

LAUDO_DURATION_SECONDS = Histogram(
    "orgaudi_laudo_duration_seconds",
    "Duração (em segundos) do processamento de um laudo NFA-e.",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

ERRORS_5XX_TOTAL = Counter(
    "orgaudi_errors_5xx_total",
    "Total de respostas HTTP 5xx servidas pela API.",
    labelnames=("route",),
    registry=REGISTRY,
)

TOKEN_COST_TOTAL = Counter(
    "orgaudi_token_cost_total",
    "Custo cumulativo (em USD) de tokens consumidos por provedor de IA.",
    labelnames=("provider",),
    registry=REGISTRY,
)

__all__ = [
    "REGISTRY",
    "LAUDOS_TOTAL",
    "LAUDO_DURATION_SECONDS",
    "ERRORS_5XX_TOTAL",
    "TOKEN_COST_TOTAL",
]
