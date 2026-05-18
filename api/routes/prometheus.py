"""Endpoint de exposição Prometheus (``GET /metrics/prom``).

Escopo (PR 1/N do fatiamento da Issue #72):

* Retorna o snapshot acumulado das métricas registradas em
  ``api.observability.metrics_registry.REGISTRY``.
* Nesta etapa as métricas estão registradas mas NÃO instrumentadas,
  então o corpo retornado contém apenas cabeçalhos (com valor 0).
* Instrumentação ativa virá em PRs subsequentes (2/N a 5/N).

Endpoint:

* ``GET /metrics/prom`` → 200 ``text/plain; version=0.0.4; charset=utf-8``
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.observability.metrics_registry import REGISTRY

router = APIRouter(prefix="/metrics", tags=["Observabilidade"])


@router.get(
    "/prom",
    response_class=Response,
    summary="Snapshot das métricas Prometheus do OrgAudi",
    responses={
        200: {
            "description": "Formato Prometheus exposition (text/plain)",
            "content": {"text/plain": {}},
        }
    },
)
def prometheus_metrics() -> Response:
    """Retorna as métricas registradas no ``REGISTRY`` dedicado."""
    payload = generate_latest(REGISTRY)
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
