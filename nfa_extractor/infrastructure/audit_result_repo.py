"""Repositório de resultados de auditoria NFA-e.

P0-2: substitui resultados_store dict in-memory por persistência em
PostgreSQL/SQLite. Sobrevive restart e suporta múltiplos workers.

Interface dict-like (proxy pattern) para zero impacto nos callers que faziam
resultados_store[result_id] = {...}.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from nfa_extractor.infrastructure.database_v2 import AuditoriaResultado, SessionLocal

logger = logging.getLogger(__name__)


def upsert_resultado(
    result_id: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
    cliente_id: int | None = None,
    audit_hash: str | None = None,
    pdf_sha256: str | None = None,
) -> None:
    """Cria ou atualiza resultado persistente."""
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)

    with SessionLocal() as db:
        res = db.get(AuditoriaResultado, result_id)
        if res is None:
            res = AuditoriaResultado(
                result_id=result_id,
                user_id=user_id or payload.get("_user_id"),
                cliente_id=cliente_id,
                audit_hash=audit_hash or payload.get("audit_hash"),
                pdf_sha256=pdf_sha256,
                payload_json=payload_json,
            )
            db.add(res)
        else:
            res.payload_json = payload_json
            if user_id is not None:
                res.user_id = user_id
            if cliente_id is not None:
                res.cliente_id = cliente_id
            if audit_hash is not None:
                res.audit_hash = audit_hash
            if pdf_sha256 is not None:
                res.pdf_sha256 = pdf_sha256
        db.commit()


def get_resultado(result_id: str) -> dict[str, Any] | None:
    """Retorna o payload completo, ou None se não existir."""
    with SessionLocal() as db:
        res = db.get(AuditoriaResultado, result_id)
        if res is None:
            return None
        try:
            return json.loads(res.payload_json) or {}
        except json.JSONDecodeError:
            logger.warning("payload_json inválido para resultado %s", result_id)
            return {}


def resultado_existe(result_id: str) -> bool:
    with SessionLocal() as db:
        return db.get(AuditoriaResultado, result_id) is not None


def deletar_resultado(result_id: str) -> bool:
    with SessionLocal() as db:
        res = db.get(AuditoriaResultado, result_id)
        if res is None:
            return False
        db.delete(res)
        db.commit()
        return True


def listar_por_usuario(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Lista metadados dos N resultados mais recentes de um usuário."""
    with SessionLocal() as db:
        rows = (
            db.query(AuditoriaResultado)
            .filter(AuditoriaResultado.user_id == user_id)
            .order_by(AuditoriaResultado.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "result_id":  r.result_id,
                "cliente_id": r.cliente_id,
                "audit_hash": r.audit_hash,
                "pdf_sha256": r.pdf_sha256,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
