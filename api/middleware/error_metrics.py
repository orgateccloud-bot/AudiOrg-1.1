"""Middleware ASGI que conta respostas HTTP 5xx em ERRORS_5XX_TOTAL.

PR 3/N do fatiamento da Issue #72 (Observabilidade Prometheus).

Estrategia:

* Embrulha cada request em try/except + verificacao de status_code.
* Em caso de excecao nao tratada que escapa do call_next, conta como 5xx
  e relanca a excecao (Starlette gera 500 automaticamente).
* A label `route` usa o pattern da APIRoute (ex.: ``/resultados/{rid}``)
  quando disponivel para evitar cardinalidade explosiva por path variavel.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.observability.metrics_registry import ERRORS_5XX_TOTAL

logger = logging.getLogger(__name__)


class ErrorMetricsMiddleware(BaseHTTPMiddleware):
    """Conta respostas HTTP 5xx por rota (label ``route``)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # Excecao nao tratada = 500 conceitualmente.
            route_label = _route_label(request)
            ERRORS_5XX_TOTAL.labels(route=route_label).inc()
            raise

        if 500 <= response.status_code < 600:
            route_label = _route_label(request)
            ERRORS_5XX_TOTAL.labels(route=route_label).inc()

        return response


def _route_label(request: Request) -> str:
    """Retorna o pattern da rota (com placeholders) ou o path bruto.

    Preferir o pattern reduz a cardinalidade da metrica em rotas como
    ``/resultados/{rid}`` (uma serie) vs. ``/resultados/abc``,
    ``/resultados/xyz``, ... (N series).
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return getattr(route, "path", "") or request.url.path
    return request.url.path
