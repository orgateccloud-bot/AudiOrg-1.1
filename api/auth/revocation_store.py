"""
ORGATEC – Store de revogação de refresh tokens (jti blacklist).

Backend Redis para produção (chave `revoked:refresh:{jti}` com TTL = exp restante),
com fallback in-memory para dev/teste quando REDIS_URL não está configurado.

Em produção (ENV=production), a ausência de REDIS_URL é fatal: o constructor
levanta RuntimeError no startup. Em dev, log warning e cai para in-memory.

API pública:
- get_store()              -> instância singleton, lazy
- store.revoke(jti, ttl)   -> marca como revogado
- store.is_revoked(jti)    -> True/False
- reset_store_for_tests()  -> força nova instância (usado por fixtures pytest)
"""
from __future__ import annotations

import os
import time
from typing import Optional, Protocol

import structlog

logger = structlog.get_logger(__name__)


class _Backend(Protocol):
    def revoke(self, jti: str, ttl_seconds: int) -> None: ...
    def is_revoked(self, jti: str) -> bool: ...


class _InMemoryBackend:
    """Fallback simples: dict {jti: expira_em_epoch}. Single-process, sem persistência."""

    def __init__(self) -> None:
        self._entries: dict[str, float] = {}

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        self._entries[jti] = time.time() + max(ttl_seconds, 0)

    def is_revoked(self, jti: str) -> bool:
        exp = self._entries.get(jti)
        if exp is None:
            return False
        if time.time() >= exp:
            # Expirou — limpa para liberar memória
            self._entries.pop(jti, None)
            return False
        return True


class _RedisBackend:
    """Backend Redis. Chave `revoked:refresh:{jti}` com TTL aproximadamente igual à exp do token."""

    _PREFIX = "revoked:refresh:"

    def __init__(self, client) -> None:
        self._client = client

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return  # Token já expirou; não há o que revogar
        self._client.set(f"{self._PREFIX}{jti}", "1", ex=ttl_seconds)

    def is_revoked(self, jti: str) -> bool:
        return bool(self._client.exists(f"{self._PREFIX}{jti}"))


class RevocationStore:
    """Facade que delega ao backend ativo."""

    def __init__(self, backend: _Backend) -> None:
        self._backend = backend

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        self._backend.revoke(jti, ttl_seconds)

    def is_revoked(self, jti: str) -> bool:
        return self._backend.is_revoked(jti)


def _build_backend() -> _Backend:
    """Decide Redis vs in-memory pelo env REDIS_URL; fail-loud em produção sem Redis."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    env = os.getenv("ENV", "development").lower()

    if not redis_url:
        if env == "production":
            raise RuntimeError(
                "REDIS_URL é obrigatório em produção para revogação de refresh tokens. "
                "Configure REDIS_URL ou rode com ENV != production."
            )
        logger.warning(
            "revocation_store_in_memory",
            motivo="REDIS_URL ausente",
            env=env,
            efeito="Revogação não persiste entre reinícios nem entre instâncias.",
        )
        return _InMemoryBackend()

    try:
        import redis  # type: ignore[import-untyped]
    except ImportError as exc:
        if env == "production":
            raise RuntimeError("Pacote `redis` não instalado em produção.") from exc
        logger.warning("revocation_store_redis_unavailable", motivo="pacote redis ausente")
        return _InMemoryBackend()

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    return _RedisBackend(client)


_store: Optional[RevocationStore] = None


def get_store() -> RevocationStore:
    """Retorna instância singleton (lazy)."""
    global _store
    if _store is None:
        _store = RevocationStore(_build_backend())
    return _store


def reset_store_for_tests() -> None:
    """Força reconstrução da store — usado por fixtures pytest entre testes."""
    global _store
    _store = None
