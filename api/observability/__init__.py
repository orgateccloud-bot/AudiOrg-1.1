"""Camada de observabilidade da API: Sentry + métricas OrgAudi-específicas.

Complementa `api/middleware/prometheus.py` (HTTP genérico) e
`api/middleware/claude_metrics.py` (uso/custo Claude) com:

- `init_sentry`: bootstrap do Sentry SDK no startup do FastAPI (#25)
- `ORGAUDI_LAUDOS_TOTAL`: counter de laudos emitidos por status
- `ORGAUDI_ERRORS_S5_TOTAL`: counter de erros 5xx por componente
- `ORGAUDI_CLAUDE_COST_USD_TOTAL`: alias de `claude_cost_usd_total` para
  alinhar com a nomenclatura `orgaudi_*` do plano de observabilidade
"""
from api.observability.orgaudi_metrics import (
    ORGAUDI_CLAUDE_COST_USD_TOTAL,
    ORGAUDI_ERRORS_S5_TOTAL,
    ORGAUDI_LAUDOS_TOTAL,
    registrar_erro_s5,
    registrar_laudo,
)
from api.observability.sentry_init import init_sentry

__all__ = [
    "ORGAUDI_CLAUDE_COST_USD_TOTAL",
    "ORGAUDI_ERRORS_S5_TOTAL",
    "ORGAUDI_LAUDOS_TOTAL",
    "init_sentry",
    "registrar_erro_s5",
    "registrar_laudo",
]
