"""
ORGATEC – Repositório de tasks de auditoria.

Substitui o dict in-memory por persistência em PostgreSQL/SQLite.
Sobrevive a reinicializações do backend e suporta múltiplos workers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from nfa_extractor.infrastructure.database_v2 import AuditTask, SessionLocal

logger = logging.getLogger(__name__)


def upsert_task(task_id: str, payload: dict[str, Any]) -> None:
    """Cria ou atualiza task. Estado completo armazenado em payload_json."""
    status = str(payload.get("status", "iniciado"))[:32]
    progress = int(payload.get("progress", 0))
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)

    with SessionLocal() as db:
        task = db.get(AuditTask, task_id)
        if task is None:
            task = AuditTask(
                task_id=task_id,
                status=status,
                progress=progress,
                payload_json=payload_json,
            )
            db.add(task)
        else:
            task.status = status
            task.progress = progress
            task.payload_json = payload_json
        db.commit()


def get_task(task_id: str) -> dict[str, Any] | None:
    """Retorna o payload completo da task, ou None se não existir."""
    with SessionLocal() as db:
        task = db.get(AuditTask, task_id)
        if task is None:
            return None
        if not task.payload_json:
            return {"status": task.status, "progress": task.progress}
        try:
            return json.loads(task.payload_json) or {}
        except json.JSONDecodeError:
            logger.warning("payload_json inválido para task %s", task_id)
            return {"status": task.status, "progress": task.progress}


def task_exists(task_id: str) -> bool:
    with SessionLocal() as db:
        return db.get(AuditTask, task_id) is not None


def cleanup_old_tasks(ttl_seconds: int = 3600) -> int:
    """Remove tasks com `updated_at` mais antigas que TTL. Retorna total deletado.

    Usa UTC consistente com AuditTask.updated_at (que é definido por _utcnow()
    em database_v2.py). Naive datetime.now() causaria offset por timezone local.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    with SessionLocal() as db:
        # SQLite armazena datetime como string sem awareness; comparamos com naive
        # depois de drop tzinfo para ficar compatível em ambos backends.
        cutoff_compat = cutoff.replace(tzinfo=None)
        deletados = (
            db.query(AuditTask)
            .filter(AuditTask.updated_at < cutoff_compat)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deletados
