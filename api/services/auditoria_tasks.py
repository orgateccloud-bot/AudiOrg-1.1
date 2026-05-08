"""
ORGATEC – Proxy persistente para status de tasks de auditoria.

Substitui o antigo dict in-memory por backend de banco de dados via
audit_task_repo. Mantém interface dict-like (proxy pattern) para zero
impacto nos chamadores que faziam tasks_status[task_id] = {...}.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from nfa_extractor.infrastructure.audit_task_repo import (
    cleanup_old_tasks,
    get_task,
    task_exists,
    upsert_task,
)

logger = logging.getLogger(__name__)


class _DbTasksProxy:
    """Backend persistente para status de tasks (PostgreSQL/SQLite via SQLAlchemy).

    Mantém a mesma interface (__setitem__, __getitem__, __contains__, get) do
    antigo proxy in-memory para zero impacto em callers. Cleanup oportunístico
    no write (limita execução a 1×/min).
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl = ttl_seconds
        self._last_cleanup = 0.0
        self._cleanup_interval = 60.0

    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup >= self._cleanup_interval:
            try:
                cleanup_old_tasks(self.ttl)
            except Exception as exc:
                logger.warning("cleanup tasks falhou: %s", exc)
            self._last_cleanup = now

    def __setitem__(self, key: str, value: Any) -> None:
        self._maybe_cleanup()
        upsert_task(key, value)

    def __getitem__(self, key: str) -> Any:
        data = get_task(key)
        if data is None:
            raise KeyError(key)
        return data

    def __contains__(self, key: str) -> bool:
        return task_exists(key)

    def get(self, key: str, default: Any = None) -> Any:
        data = get_task(key)
        return default if data is None else data


tasks_status: _DbTasksProxy = _DbTasksProxy()
