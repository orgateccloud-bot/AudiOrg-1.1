"""Testes do audit_result_repo — P0-2 persistência de resultados NFA-e."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-bytes-long-suficient-for-tests")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_result_repo.db")

from nfa_extractor.infrastructure.audit_result_repo import (  # noqa: E402
    deletar_resultado,
    get_resultado,
    listar_por_usuario,
    resultado_existe,
    upsert_resultado,
)
from nfa_extractor.infrastructure.database_v2 import init_db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()


def test_upsert_e_get(tmp_path):
    rid = "test-rid-001"
    upsert_resultado(rid, {"foo": "bar", "valor": 100.5}, user_id="42")
    assert resultado_existe(rid)
    data = get_resultado(rid)
    assert data == {"foo": "bar", "valor": 100.5}


def test_upsert_atualiza_existente():
    rid = "test-rid-002"
    upsert_resultado(rid, {"v": 1}, user_id="42")
    upsert_resultado(rid, {"v": 2}, user_id="42")
    assert get_resultado(rid) == {"v": 2}


def test_get_inexistente_retorna_none():
    assert get_resultado("nao-existe") is None
    assert resultado_existe("nao-existe") is False


def test_deletar():
    rid = "test-rid-003"
    upsert_resultado(rid, {"x": 1}, user_id="42")
    assert deletar_resultado(rid) is True
    assert get_resultado(rid) is None
    assert deletar_resultado(rid) is False  # idempotente


def test_listar_por_usuario():
    upsert_resultado("rid-u99-1", {"a": 1}, user_id="99")
    upsert_resultado("rid-u99-2", {"a": 2}, user_id="99")
    upsert_resultado("rid-u88-1", {"a": 3}, user_id="88")
    meus = listar_por_usuario("99")
    rids = {r["result_id"] for r in meus}
    assert "rid-u99-1" in rids
    assert "rid-u99-2" in rids
    assert "rid-u88-1" not in rids


def test_persist_hash_pdf():
    """P0-6: pdf_sha256 sobrevive ao upsert."""
    rid = "test-rid-pdf-hash"
    hash_fake = "a" * 64
    upsert_resultado(rid, {"pdf_sha256": hash_fake, "result_id": rid}, pdf_sha256=hash_fake)
    data = get_resultado(rid)
    assert data["pdf_sha256"] == hash_fake
