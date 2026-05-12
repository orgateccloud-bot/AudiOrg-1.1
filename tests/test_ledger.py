"""Testes para ledger persistente em Postgres/SQLite (#26).

Cobertura:
- log_event_sync escreve em ledger_entries com colunas corretas
- async_log_event roda em executor (não bloqueia loop)
- payload é serializado em JSON
- concorrência: 50 inserts paralelos não duplicam id (autoincrement)
- falha de banco -> fallback JSONL (zero perda)
- requisicao_id e agent_id são indexados (busca por chave volta < N linhas)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Setup: banco SQLite isolado por sessão ───────────────────────────────────


@pytest.fixture(scope="module")
def _isolated_db(tmp_path_factory, monkeypatch_module=None):
    """Banco SQLite efêmero com schema aplicado via alembic upgrade."""
    db_path = tmp_path_factory.mktemp("ledger") / "ledger.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["ENV"] = "development"

    # Reload database_v2 contra o novo DATABASE_URL
    import importlib
    from nfa_extractor.infrastructure import database_v2
    importlib.reload(database_v2)

    # Aplica migrations
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    yield database_v2

    os.environ.pop("DATABASE_URL", None)


# ── log_event_sync ───────────────────────────────────────────────────────────


class TestLogEventSync:

    def test_insere_linha_com_colunas_corretas(self, _isolated_db):
        from horizon_blue_one.core import ledger
        from nfa_extractor.infrastructure.database_v2 import LedgerEntry, SessionLocal

        ledger.log_event_sync(
            requisicao_id="req-test-1",
            agent_id="A-01",
            acao="Roteou nfa para A-08",
            tier="Haiku",
            status="APROVADO",
            audit_hash="abc123",
            payload={"tipo": "nfa", "destino": "A-08"},
        )

        with SessionLocal() as session:
            row = session.query(LedgerEntry).filter_by(requisicao_id="req-test-1").one()
            assert row.agent_id == "A-01"
            assert row.acao == "Roteou nfa para A-08"
            assert row.tier == "Haiku"
            assert row.audit_hash == "abc123"
            assert json.loads(row.payload_json) == {"tipo": "nfa", "destino": "A-08"}
            assert row.ts is not None

    def test_payload_none_grava_null(self, _isolated_db):
        from horizon_blue_one.core import ledger
        from nfa_extractor.infrastructure.database_v2 import LedgerEntry, SessionLocal

        ledger.log_event_sync(
            requisicao_id="req-test-2",
            agent_id="A-08",
            acao="Auditoria iniciada",
        )

        with SessionLocal() as session:
            row = session.query(LedgerEntry).filter_by(requisicao_id="req-test-2").one()
            assert row.payload_json is None
            assert row.status == "APROVADO"  # default


# ── async_log_event ──────────────────────────────────────────────────────────


class TestAsyncLogEvent:

    def test_async_grava_evento(self, _isolated_db):
        from horizon_blue_one.core import ledger
        from nfa_extractor.infrastructure.database_v2 import LedgerEntry, SessionLocal

        async def _go():
            await ledger.async_log_event(
                requisicao_id="req-async-1",
                agent_id="A-01",
                acao="Async test",
                payload={"k": "v"},
            )

        asyncio.run(_go())

        with SessionLocal() as session:
            row = session.query(LedgerEntry).filter_by(requisicao_id="req-async-1").one()
            assert row.acao == "Async test"

    def test_async_nao_bloqueia_loop(self, _isolated_db):
        """Se async_log_event bloqueasse o loop, este teste demoraria > 2s."""
        from horizon_blue_one.core import ledger

        async def _go():
            tarefas = [
                ledger.async_log_event(
                    requisicao_id=f"req-loop-{i}",
                    agent_id="A-01",
                    acao=f"loop {i}",
                )
                for i in range(5)
            ]
            await asyncio.gather(*tarefas)

        import time
        t0 = time.time()
        asyncio.run(_go())
        elapsed = time.time() - t0
        assert elapsed < 2.0, f"Async loop demorou {elapsed:.2f}s — provavelmente está bloqueando"


# ── Concorrência ─────────────────────────────────────────────────────────────


class TestConcorrencia:

    def test_100_inserts_paralelos_geram_100_linhas_unicas(self, _isolated_db):
        from horizon_blue_one.core import ledger
        from nfa_extractor.infrastructure.database_v2 import LedgerEntry, SessionLocal

        def _emit(i: int):
            ledger.log_event_sync(
                requisicao_id=f"req-concorrente-{i}",
                agent_id="A-01",
                acao=f"concorrente {i}",
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(_emit, range(100)))

        with SessionLocal() as session:
            ids = [
                row.id for row in
                session.query(LedgerEntry).filter(
                    LedgerEntry.requisicao_id.like("req-concorrente-%")
                ).all()
            ]
            assert len(ids) == 100
            assert len(set(ids)) == 100, "IDs duplicados após inserts paralelos"


# ── Fallback JSONL ───────────────────────────────────────────────────────────


class TestFallbackJsonl:

    def test_falha_no_insert_escreve_jsonl(self, _isolated_db, tmp_path, monkeypatch):
        from horizon_blue_one.core import ledger

        fallback = tmp_path / "fallback.jsonl"
        monkeypatch.setattr(ledger, "_FALLBACK_PATH", fallback)

        def _explode(*_a, **_kw):
            raise RuntimeError("simulando banco indisponível")

        monkeypatch.setattr(ledger, "_insert_sync", _explode)

        ledger.log_event_sync(
            requisicao_id="req-fallback",
            agent_id="A-01",
            acao="testando fallback",
            payload={"x": 1},
        )

        assert fallback.exists()
        linha = json.loads(fallback.read_text(encoding="utf-8").splitlines()[0])
        assert linha["requisicao_id"] == "req-fallback"
        assert linha["_motivo_fallback"] == "simulando banco indisponível"

    def test_async_falha_escreve_fallback(self, _isolated_db, tmp_path, monkeypatch):
        from horizon_blue_one.core import ledger

        fallback = tmp_path / "fallback_async.jsonl"
        monkeypatch.setattr(ledger, "_FALLBACK_PATH", fallback)

        def _explode(*_a, **_kw):
            raise RuntimeError("db down")

        monkeypatch.setattr(ledger, "_insert_sync", _explode)

        async def _go():
            await ledger.async_log_event(
                requisicao_id="req-async-fb",
                agent_id="A-99",
                acao="async fallback",
            )

        asyncio.run(_go())
        assert fallback.exists()
        linha = json.loads(fallback.read_text(encoding="utf-8").splitlines()[0])
        assert linha["requisicao_id"] == "req-async-fb"


# ── Schema ───────────────────────────────────────────────────────────────────


class TestSchema:

    def test_tabela_ledger_existe_com_indices(self, _isolated_db):
        from sqlalchemy import inspect
        from nfa_extractor.infrastructure.database_v2 import engine

        insp = inspect(engine)
        assert "ledger_entries" in insp.get_table_names()

        cols = {c["name"] for c in insp.get_columns("ledger_entries")}
        esperadas = {
            "id", "ts", "requisicao_id", "agent_id", "acao",
            "tier", "status", "audit_hash", "payload_json",
        }
        assert esperadas.issubset(cols), f"faltando: {esperadas - cols}"

        indices = {ix["name"] for ix in insp.get_indexes("ledger_entries")}
        # Pelo menos os índices definidos na migration
        assert any("requisicao_id" in n for n in indices)
        assert any("agent_id" in n for n in indices)
