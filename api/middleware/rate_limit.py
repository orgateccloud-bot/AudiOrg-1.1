"""
ORGATEC – Rate Limiting Middleware.

Backend Redis (produção/multi-instância) com fallback in-memory (dev/teste).
A escolha é controlada por REDIS_URL; em ENV=production a ausência levanta erro.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Callable, Protocol

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60


class _Backend(Protocol):
    def check(self, key: str, rate: int, window: int) -> tuple[bool, int]: ...


class _InMemoryBackend:
    """Fallback in-memory: dict de timestamps por IP. Não vale para multi-instância."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, rate: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = [t for t in self._buckets[key] if now - t < window]
        if len(bucket) >= rate:
            self._buckets[key] = bucket
            return False, 0
        bucket.append(now)
        self._buckets[key] = bucket
        return True, rate - len(bucket)


class _RedisBackend:
    """Janela fixa em Redis com INCR + EXPIRE. Atômico via pipeline."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._client.ping()

    def check(self, key: str, rate: int, window: int) -> tuple[bool, int]:
        window_start = int(time.time()) // window
        redis_key = f"ratelimit:{key}:{window_start}"
        pipe = self._client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window)
        count, _ = pipe.execute()
        if count > rate:
            return False, 0
        return True, rate - count


def _build_backend() -> _Backend:
    url = os.getenv("REDIS_URL", "").strip()
    env = os.getenv("ENV", "development").lower()
    if url:
        try:
            backend = _RedisBackend(url)
            logger.info("RateLimit usando backend Redis (%s)", url.split("@")[-1])
            return backend
        except Exception as exc:  # noqa: BLE001 — fail loud em prod, fallback em dev
            if env == "production":
                raise RuntimeError(f"REDIS_URL configurado mas inacessível: {exc}") from exc
            logger.warning("Redis indisponível (%s) — usando fallback in-memory", exc)
            return _InMemoryBackend()
    if env == "production":
        raise RuntimeError("REDIS_URL é obrigatório em ENV=production")
    logger.warning("REDIS_URL ausente — rate limit in-memory (não vale multi-instância)")
    return _InMemoryBackend()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware de rate limiting por IP."""

    def __init__(self, app, rate: int = DEFAULT_RATE_LIMIT, window: int = DEFAULT_WINDOW_SECONDS):
        super().__init__(app)
        self._rate = rate
        self._window = window
        self._backend = _build_backend()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/ping":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        allowed, remaining = self._backend.check(client_ip, self._rate, self._window)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Limite de requisições excedido. Tente novamente em breve."},
                headers={"Retry-After": str(self._window)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
