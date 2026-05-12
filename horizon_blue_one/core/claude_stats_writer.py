"""Writer batched de stats Claude → tabela `claude_stats` em Postgres (#27).

Modelo de uso:

    from horizon_blue_one.core.claude_stats_writer import registrar_call, flush

    registrar_call("claude-sonnet-4-6", tokens_in=1200, tokens_out=480)
    # ... várias chamadas ...
    flush()  # persiste agregados acumulados (1 linha por periodo+modelo)

Por que batched: cada agente do pipeline S1-S7 faz dezenas de chamadas;
um INSERT por call duplicaria a latência e a contenção no pool. Acumulamos
em memória por (periodo_iso, modelo) e fazemos UPSERT (sum incremental)
em flush periódico — disparado a cada `_BATCH_MAX_CALLS` ou via
`iniciar_flush_periodico()` em background.

Independência do listener: pode ser chamado diretamente por `token_router`
quando #29 mergear (registrando `registrar_call` como listener), ou
invocado manualmente em qualquer ponto que conheça os tokens da chamada.

Tabela `claude_stats` é criada pela migration alembic 003.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from nfa_extractor.infrastructure.database_v2 import ClaudeStats, SessionLocal

logger = logging.getLogger(__name__)

# ── Tabela de preços (USD por 1M tokens) — espelho do token_router ──────────
#
# Quando o token_router de #29 expuser as tabelas, esta cópia pode ser
# removida. Por ora, mantemos a mesma referência para isolar o writer
# de dependências em vôo.
_PRECO_INPUT_USD_PER_MTOK: dict[str, float] = {
    "claude-haiku-4-5-20251001": 0.80,
    "claude-haiku-4-5":          0.80,
    "claude-sonnet-4-6":         3.00,
    "claude-sonnet-4-5":         3.00,
    "claude-opus-4-7":           15.00,
    "claude-opus-4-6":           15.00,
}
_PRECO_OUTPUT_USD_PER_MTOK: dict[str, float] = {
    "claude-haiku-4-5-20251001": 4.00,
    "claude-haiku-4-5":          4.00,
    "claude-sonnet-4-6":         15.00,
    "claude-sonnet-4-5":         15.00,
    "claude-opus-4-7":           75.00,
    "claude-opus-4-6":           75.00,
}

_BATCH_MAX_CALLS = 100  # flush automático a cada N calls acumuladas


def _calcular_custo(modelo: str, tokens_in: int, tokens_out: int) -> float:
    custo_in  = _PRECO_INPUT_USD_PER_MTOK.get(modelo,  0.0)
    custo_out = _PRECO_OUTPUT_USD_PER_MTOK.get(modelo, 0.0)
    return (tokens_in * custo_in + tokens_out * custo_out) / 1_000_000


def _periodo_atual() -> str:
    """ISO-8601 do início da hora UTC corrente (YYYY-MM-DDTHH:00:00Z)."""
    agora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return agora.strftime("%Y-%m-%dT%H:00:00Z")


# ── Buffer in-memory ─────────────────────────────────────────────────────────
# Key: (periodo, modelo). Value: dict de agregados acumulados desde o último flush.
_BUFFER: dict[tuple[str, str], dict[str, float]] = {}
_LOCK = threading.Lock()
_TOTAL_CALLS_DESDE_FLUSH = 0


def registrar_call(
    modelo: str,
    tokens_in: int,
    tokens_out: int,
    *,
    custo_usd: float | None = None,
    flush_auto: bool = True,
) -> None:
    """Acumula uma chamada Claude no buffer. Custo é derivado da tabela
    interna se não fornecido. Flush automático ao atingir _BATCH_MAX_CALLS."""
    global _TOTAL_CALLS_DESDE_FLUSH

    custo = float(custo_usd) if custo_usd is not None else _calcular_custo(
        modelo, tokens_in, tokens_out,
    )
    chave = (_periodo_atual(), modelo)
    with _LOCK:
        bucket = _BUFFER.setdefault(chave, {
            "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        })
        bucket["calls"]      += 1
        bucket["tokens_in"]  += int(tokens_in)
        bucket["tokens_out"] += int(tokens_out)
        bucket["cost_usd"]   += custo
        _TOTAL_CALLS_DESDE_FLUSH += 1
        deve_fazer_flush = flush_auto and _TOTAL_CALLS_DESDE_FLUSH >= _BATCH_MAX_CALLS

    if deve_fazer_flush:
        flush()


def flush(session_factory=None) -> int:
    """Persiste o buffer no Postgres. UPSERT incremental: linha existente
    para (periodo, modelo) tem seus contadores somados; nova linha é criada
    quando ausente. Retorna o número de chaves processadas.

    `session_factory` resolve para o `SessionLocal` deste módulo no momento
    da chamada (não no module-load), permitindo monkeypatch em testes.
    """
    global _TOTAL_CALLS_DESDE_FLUSH

    factory = session_factory if session_factory is not None else SessionLocal

    with _LOCK:
        snapshot = dict(_BUFFER)
        _BUFFER.clear()
        _TOTAL_CALLS_DESDE_FLUSH = 0

    if not snapshot:
        return 0

    chaves_processadas = 0
    try:
        with factory() as db:  # type: Session
            for (periodo, modelo), agg in snapshot.items():
                _upsert_um(db, periodo, modelo, agg)
                chaves_processadas += 1
            db.commit()
    except Exception as exc:  # noqa: BLE001 — não derruba pipeline por métrica
        logger.error(
            "claude_stats.flush_falhou chaves=%d erro=%s",
            len(snapshot), exc,
        )
        # Reinjeta no buffer para retry na próxima chamada
        with _LOCK:
            for chave, agg in snapshot.items():
                existente = _BUFFER.setdefault(chave, {
                    "calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                })
                existente["calls"]      += agg["calls"]
                existente["tokens_in"]  += agg["tokens_in"]
                existente["tokens_out"] += agg["tokens_out"]
                existente["cost_usd"]   += agg["cost_usd"]
        return 0

    logger.info("claude_stats.flush chaves=%d", chaves_processadas)
    return chaves_processadas


def _upsert_um(db: Session, periodo: str, modelo: str, agg: dict[str, float]) -> None:
    """Soma incremental: localiza linha por (periodo, modelo) e atualiza,
    ou insere nova se não existe. Funciona idêntico em SQLite e Postgres."""
    existente = db.execute(
        select(ClaudeStats).where(
            ClaudeStats.periodo == periodo,
            ClaudeStats.modelo == modelo,
        )
    ).scalar_one_or_none()

    if existente is None:
        db.add(ClaudeStats(
            periodo=periodo,
            modelo=modelo,
            calls=int(agg["calls"]),
            tokens_in=int(agg["tokens_in"]),
            tokens_out=int(agg["tokens_out"]),
            cost_usd_acumulado=float(agg["cost_usd"]),
        ))
    else:
        existente.calls              += int(agg["calls"])
        existente.tokens_in          += int(agg["tokens_in"])
        existente.tokens_out         += int(agg["tokens_out"])
        existente.cost_usd_acumulado += float(agg["cost_usd"])


# ── Background flush periódico ──────────────────────────────────────────────

_FLUSH_TASK: asyncio.Task | None = None


async def _loop_flush_periodico(intervalo_s: float) -> None:
    while True:
        try:
            await asyncio.sleep(intervalo_s)
        except asyncio.CancelledError:
            break
        try:
            await asyncio.to_thread(flush)
        except Exception as exc:  # noqa: BLE001
            logger.warning("claude_stats.flush_periodico_erro erro=%s", exc)


def iniciar_flush_periodico(intervalo_s: float = 30.0) -> bool:
    """Inicia a task de flush periódico. Retorna False se já estava ativa."""
    global _FLUSH_TASK
    if _FLUSH_TASK is not None and not _FLUSH_TASK.done():
        return False
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return False
    _FLUSH_TASK = loop.create_task(_loop_flush_periodico(intervalo_s))
    return True


def parar_flush_periodico() -> None:
    """Cancela a task de flush periódico. Faz um flush final síncrono."""
    global _FLUSH_TASK
    if _FLUSH_TASK is not None and not _FLUSH_TASK.done():
        _FLUSH_TASK.cancel()
    _FLUSH_TASK = None
    flush()


# ── Helpers de teste ────────────────────────────────────────────────────────

def reset_buffer_para_testes() -> None:
    """Limpa o buffer in-memory. Uso restrito a fixtures."""
    global _TOTAL_CALLS_DESDE_FLUSH
    with _LOCK:
        _BUFFER.clear()
        _TOTAL_CALLS_DESDE_FLUSH = 0
