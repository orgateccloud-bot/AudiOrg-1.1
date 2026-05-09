"""
Ledger — registro append-only de eventos do squad Horizon-Blue.

Esta versão é um stub leve: registra em arquivo JSONL local
(`out/ledger.jsonl`) e em logger estruturado. Sem dependência de DB.

Para produção, substituir `async_log_event` por persistência real
(Postgres / event store). A interface deve ser preservada para que os
agentes (ex.: A-01 @Junior) continuem chamando do mesmo jeito.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_ROOT = Path(__file__).resolve().parent.parent.parent
_LEDGER_PATH = _ROOT / "out" / "ledger.jsonl"
_LOCK = asyncio.Lock()


async def async_log_event(
    *,
    requisicao_id: str,
    agent_id: str,
    acao: str,
    tier: str = "",
    status: str = "APROVADO",
    audit_hash: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """Registra um evento no ledger append-only.

    Mantém a assinatura usada por agentes (a01_junior.py).
    Não bloqueia: escreve linha JSONL e loga via structlog.
    """
    evento = {
        "ts":             datetime.now(timezone.utc).isoformat(),
        "ts_unix":        time.time(),
        "requisicao_id":  requisicao_id,
        "agent_id":       agent_id,
        "acao":           acao,
        "tier":           tier,
        "status":         status,
        "audit_hash":     audit_hash,
        "payload":        payload or {},
    }
    logger.info(
        "ledger.evento",
        agent_id=agent_id,
        acao=acao,
        status=status,
        requisicao_id=requisicao_id,
    )
    try:
        async with _LOCK:
            _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _LEDGER_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        # Não falha o agente em caso de I/O lento — só registra
        logger.warning("ledger.write_error", erro=str(exc))


def log_event_sync(**kwargs: Any) -> None:
    """Versão síncrona — útil em scripts e testes que não rodam em event loop."""
    asyncio.run(async_log_event(**kwargs))
