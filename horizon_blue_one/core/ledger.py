"""Ledger de eventos de agentes — escreve em Postgres (#26).

Substitui o append-only JSONL anterior. Cada evento de agente vira uma
linha na tabela `ledger_entries` (queryable, indexada por requisicao_id,
agent_id e audit_hash).

API:
    await async_log_event(
        requisicao_id="req-abc",
        agent_id="A-01",
        acao="Roteou nfa para A-08",
        tier="Haiku",
        status="APROVADO",
        audit_hash="...",
        payload={"chave": "valor"},
    )

Comportamento:
- Em produção: insere síncronamente via SQLAlchemy session no thread executor
  (não bloqueia o event loop). Falha em insert -> log de erro + JSONL fallback
  (mantém integridade: nenhum evento é perdido por flakiness do banco).
- Em dev/teste sem DATABASE_URL Postgres: ainda escreve no banco padrão
  (SQLite WAL); o desenho continua queryable em qualquer ambiente.
- JSONL fallback fica em LEDGER_FALLBACK_PATH (default: ledger_fallback.jsonl).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FALLBACK_PATH = Path(os.getenv("LEDGER_FALLBACK_PATH", "ledger_fallback.jsonl"))


def _write_fallback_jsonl(entry: dict[str, Any]) -> None:
    """Último recurso quando o banco está indisponível — garante zero perda."""
    try:
        with _FALLBACK_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except OSError as exc:
        logger.error("ledger_fallback_falhou motivo=%s entry_keys=%s", exc, list(entry.keys()))


def _insert_sync(
    requisicao_id: str,
    agent_id: str,
    acao: str,
    tier: Optional[str],
    status: str,
    audit_hash: Optional[str],
    payload: Optional[dict[str, Any]],
) -> None:
    """Insert síncrono — rodado dentro de asyncio.to_thread para não bloquear o loop."""
    # Import preguiçoso: testes que monkeypatcham SessionLocal precisam do binding atual
    from nfa_extractor.infrastructure.database_v2 import LedgerEntry, SessionLocal

    payload_str = json.dumps(payload, default=str) if payload else None
    entry = LedgerEntry(
        ts=datetime.now(timezone.utc),
        requisicao_id=requisicao_id,
        agent_id=agent_id,
        acao=acao,
        tier=tier,
        status=status,
        audit_hash=audit_hash,
        payload_json=payload_str,
    )
    with SessionLocal() as session:
        session.add(entry)
        session.commit()


async def async_log_event(
    *,
    requisicao_id: str,
    agent_id: str,
    acao: str,
    tier: Optional[str] = None,
    status: str = "APROVADO",
    audit_hash: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Grava evento no ledger sem bloquear o event loop.

    Se o insert falhar (banco fora, schema desatualizado, etc.) o evento é
    serializado para o JSONL fallback — preserva auditabilidade mesmo em
    incidente de banco.
    """
    try:
        await asyncio.to_thread(
            _insert_sync,
            requisicao_id,
            agent_id,
            acao,
            tier,
            status,
            audit_hash,
            payload,
        )
    except Exception as exc:
        logger.error(
            "ledger_insert_falhou agent=%s requisicao=%s error=%s",
            agent_id, requisicao_id, exc,
        )
        _write_fallback_jsonl(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "requisicao_id": requisicao_id,
                "agent_id": agent_id,
                "acao": acao,
                "tier": tier,
                "status": status,
                "audit_hash": audit_hash,
                "payload": payload,
                "_motivo_fallback": str(exc),
            }
        )


def log_event_sync(
    *,
    requisicao_id: str,
    agent_id: str,
    acao: str,
    tier: Optional[str] = None,
    status: str = "APROVADO",
    audit_hash: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Versão síncrona — para callers fora de contexto async (scripts, testes)."""
    try:
        _insert_sync(requisicao_id, agent_id, acao, tier, status, audit_hash, payload)
    except Exception as exc:
        logger.error(
            "ledger_insert_sync_falhou agent=%s requisicao=%s error=%s",
            agent_id, requisicao_id, exc,
        )
        _write_fallback_jsonl(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "requisicao_id": requisicao_id,
                "agent_id": agent_id,
                "acao": acao,
                "tier": tier,
                "status": status,
                "audit_hash": audit_hash,
                "payload": payload,
                "_motivo_fallback": str(exc),
            }
        )
