"""
ORGATEC – Rate Limiting Middleware.

Usa um contador in-memory por IP. Simples, sem dependência de Redis.
Para produção multi-instance, substituir por slowapi ou redis-based.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Configuração padrão: 60 requests por minuto por IP
DEFAULT_RATE_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60


class _TokenBucket:
    """Token bucket simples para rate limiting por IP."""

    def __init__(self, rate: int, window: float):
        self._rate = rate
        self._window = window
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Retorna (permitido, requests_restantes)."""
        now = time.monotonic()
        bucket = self._buckets[key]
        # Remove timestamps fora da janela
        self._buckets[key] = [t for t in bucket if now - t < self._window]
        bucket = self._buckets[key]

        if len(bucket) >= self._rate:
            return False, 0

        bucket.append(now)
        return True, self._rate - len(bucket)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware de rate limiting por IP."""

    def __init__(self, app, rate: int = DEFAULT_RATE_LIMIT, window: float = DEFAULT_WINDOW_SECONDS):
        super().__init__(app)
        self._bucket = _TokenBucket(rate, window)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting para health check
        if request.url.path == "/ping":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        allowed, remaining = self._bucket.is_allowed(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Limite de requisições excedido. Tente novamente em breve."},
                headers={"Retry-After": str(int(DEFAULT_WINDOW_SECONDS))},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
