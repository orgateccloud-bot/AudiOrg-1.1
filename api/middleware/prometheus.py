"""Middleware Prometheus — expõe métricas HTTP padrão.

Coleta:
- http_requests_total{method, path, status}    — Counter
- http_request_duration_seconds{method, path}  — Histogram
- http_requests_in_progress{method, path}      — Gauge
- app_info{version}                            — Info

Endpoint /metrics/prometheus servido em api/routes/metrics.py.
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

# ── Métricas Prometheus (singletons no módulo) ────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total de requisições HTTP por método/rota/status.",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Latência das requisições HTTP em segundos.",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Requisições HTTP em andamento.",
    ["method", "path"],
)

APP_INFO = Info("orgaudi_app", "Informações estáticas da aplicação OrgAudi.")
APP_INFO.info({"version": "8.0.0", "service": "orgaudi-sovereign"})


def _normalizar_path(raw: str) -> str:
    """Reduz cardinalidade — paths com UUIDs/IDs viram rótulos genéricos."""
    if raw == "/":
        return "/"
    partes = raw.split("/")
    out = []
    for p in partes:
        if not p:
            continue
        # Heurística: número puro ou hex >=12 chars → :id
        if p.isdigit() or (len(p) >= 12 and all(c in "0123456789abcdef-" for c in p.lower())):
            out.append(":id")
        else:
            out.append(p)
    return "/" + "/".join(out)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Coleta métricas HTTP para Prometheus."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        path = _normalizar_path(request.url.path)

        # Não conta o próprio endpoint /metrics/prometheus (evita ruído)
        if path == "/metrics/prometheus":
            return await call_next(request)

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).inc()
        inicio = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duracao = time.monotonic() - inicio
            HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(duracao)
            HTTP_REQUESTS_TOTAL.labels(
                method=method, path=path, status=str(status_code),
            ).inc()
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, path=path).dec()
            # Issue #25: errors_s5 separado para alertas no dashboard
            if status_code >= 500:
                try:
                    from api.observability.orgaudi_metrics import registrar_erro_s5
                    registrar_erro_s5(path)
                except Exception:  # noqa: BLE001 — métrica não pode quebrar request
                    pass


def render_metrics() -> StarletteResponse:
    """Renderiza o snapshot atual em formato Prometheus text/plain."""
    return StarletteResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
