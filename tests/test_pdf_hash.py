"""Teste P0-6: hash SHA-256 do PDF emitido é calculado e persistido."""
from __future__ import annotations

import hashlib
import os

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-bytes-long-suficient-for-tests")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_pdf_hash.db")

from api.services.auditoria_nfae import gerar_pdf_nfae, resultados_store  # noqa: E402
from nfa_extractor.infrastructure.audit_result_repo import (  # noqa: E402
    get_resultado,
    upsert_resultado,
)
from nfa_extractor.infrastructure.database_v2 import init_db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()


def _resultado_minimo() -> dict:
    return {
        "result_id":     "test-pdf-hash-001",
        "_user_id":      "1",
        "audit_hash":    "h" * 64,
        "status":        "APROVADO",
        "score_risco":   {"score": 30, "nivel": "BAIXO", "modo": "heuristico"},
        "resumo_fiscal": {
            "f1_receita_imediata": 1000.0,
            "f2_transito": 0,
            "f4_receita_bruta": 1000.0,
            "f6_despesa": 200.0,
            "f5_resultado_rural": 800.0,
            "funrural": 25.0,
            "aliquota_funrural": 0.025,
            "irpf_estimado": 0,
            "total_notas": 1,
        },
        "notas_re1_aplicada": 0,
        "analise_assurance": {},
        "contribuinte": {"nome": "Teste", "cpf": "000.000.000-00", "regime": "PF"},
        "timestamp": "2026-05-12T00:00:00Z",
    }


def test_gerar_pdf_devolve_bytes_e_persiste_hash():
    resultado = _resultado_minimo()
    # Pré-persiste o resultado para que gerar_pdf_nfae possa salvar o hash
    upsert_resultado(resultado["result_id"], resultado, user_id="1", audit_hash="h" * 64)

    pdf_bytes = gerar_pdf_nfae(resultado)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000

    # P0-6: hash do PDF deve estar persistido
    persistido = get_resultado(resultado["result_id"])
    assert persistido is not None
    hash_esperado = hashlib.sha256(pdf_bytes).hexdigest()
    assert persistido["pdf_sha256"] == hash_esperado


def test_resultados_store_proxy_persiste():
    """resultados_store agora é proxy: __setitem__ vai pro DB."""
    rid = "test-proxy-001"
    resultados_store[rid] = {"foo": "bar", "result_id": rid, "_user_id": "1"}
    assert rid in resultados_store
    assert resultados_store[rid]["foo"] == "bar"
    # Sobrevive a "restart" (recarrega do DB)
    from nfa_extractor.infrastructure.audit_result_repo import get_resultado
    assert get_resultado(rid)["foo"] == "bar"
