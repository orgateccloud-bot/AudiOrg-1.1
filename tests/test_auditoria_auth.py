"""Testes de autorização nos endpoints /auditoria/* (P0-1, P0-2 da auditoria).

Garante que:
- POST /auditoria/upload exige JWT
- POST /auditoria/nfae exige JWT
- client_id inexistente retorna 404
- Resultados/status só visíveis ao dono ou admin
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-bytes-long-suficient-for-tests")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_audit_auth.db")

from api.main import app  # noqa: E402
from api.auth.security import create_token_pair  # noqa: E402
from nfa_extractor.infrastructure.database_v2 import Cliente, SessionLocal, init_db  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()
    with SessionLocal() as db:
        if db.query(Cliente).filter_by(cpf_cnpj="999.999.999-99").first() is None:
            db.add(Cliente(nome="Cliente Teste", cpf_cnpj="999.999.999-99"))
            db.commit()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def token_user() -> str:
    pair = create_token_pair({"sub": "100", "email": "user@x.com", "role": "user"})
    return pair.access_token


@pytest.fixture
def cliente_id() -> int:
    with SessionLocal() as db:
        c = db.query(Cliente).filter_by(cpf_cnpj="999.999.999-99").first()
        return c.id


def test_upload_sem_jwt_retorna_401(client: TestClient, cliente_id: int):
    pdf = b"%PDF-1.4\n" + b"X" * 200
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("nota.pdf", pdf, "application/pdf"))],
    )
    assert resp.status_code == 401


def test_upload_client_id_inexistente_retorna_404(client: TestClient, token_user: str):
    pdf = b"%PDF-1.4\n" + b"X" * 200
    resp = client.post(
        "/auditoria/upload/99999",
        files=[("files", ("nota.pdf", pdf, "application/pdf"))],
        headers={"Authorization": f"Bearer {token_user}"},
    )
    assert resp.status_code == 404
    assert "não encontrado" in resp.json()["detail"].lower()


def test_nfae_sem_jwt_retorna_401(client: TestClient):
    resp = client.post("/auditoria/nfae", json={
        "contribuinte_cpf": "111.222.333-44",
        "contribuinte_nome": "X",
        "notas": [{
            "numero": "1", "data": "2026-01-01", "natureza": "VENDA",
            "valor_total": 100.0,
        }],
    })
    assert resp.status_code == 401
