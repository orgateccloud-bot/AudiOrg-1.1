"""Testes do endpoint /chat/{result_id} — Fase 1 da integração Claude.

Cobertura:
- 401 sem token JWT
- 404 quando result_id não existe
- 404 quando usuário tenta acessar laudo de outro (não-admin)
- 200 quando admin acessa laudo de qualquer dono
- 200 quando dono acessa próprio laudo, Claude mockado
- DELETE limpa histórico
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Garante secret key antes de importar a app (que carrega security.py)
os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-bytes-long-suficient-for-tests")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_chat.db")

from api.main import app  # noqa: E402
from api.auth.security import create_token_pair  # noqa: E402
from api.services.auditoria import resultados_store  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def token_alice() -> str:
    pair = create_token_pair({"sub": "10", "email": "alice@orgatec.com.br", "role": "user"})
    return pair.access_token


@pytest.fixture
def token_bob() -> str:
    pair = create_token_pair({"sub": "20", "email": "bob@orgatec.com.br", "role": "user"})
    return pair.access_token


@pytest.fixture
def token_admin() -> str:
    pair = create_token_pair({"sub": "1", "email": "admin@orgatec.com.br", "role": "admin"})
    return pair.access_token


@pytest.fixture(autouse=True)
def _laudo_de_alice():
    from api.routes.chat import _chat_sessions
    rid = "rid-alice-001"
    resultados_store[rid] = {
        "result_id": rid,
        "_user_id": "10",
        "veredito_ia": "APROVADO",
        "qtd_notas": 12,
        "valor_total": 50000.0,
        "anomalias_detectadas": [],
    }
    _chat_sessions.clear()  # isolamento entre testes
    yield rid
    resultados_store.pop(rid, None)
    _chat_sessions.clear()


@pytest.fixture(autouse=True)
def _claude_mock(monkeypatch):
    """Mocka call_model para não bater na API Anthropic durante teste."""
    async def _fake(model_type, prompt, system="", max_tokens=4096):
        return '{"ok": "mock"}'
    monkeypatch.setattr(
        "horizon_blue_one.agents.base_agent.call_model",
        _fake,
    )


def test_chat_exige_autenticacao(client: TestClient):
    resp = client.post("/chat/rid-alice-001", json={"pergunta": "oi?"})
    assert resp.status_code == 401


def test_chat_404_quando_laudo_nao_existe(client: TestClient, token_alice: str):
    resp = client.post(
        "/chat/rid-inexistente",
        json={"pergunta": "oi?"},
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    assert resp.status_code == 404


def test_chat_404_quando_nao_e_dono_nem_admin(client: TestClient, token_bob: str):
    resp = client.post(
        "/chat/rid-alice-001",
        json={"pergunta": "oi?"},
        headers={"Authorization": f"Bearer {token_bob}"},
    )
    # Bob não é dono nem admin → 404 (evita revelar que laudo existe)
    assert resp.status_code == 404


def test_chat_200_quando_dono(client: TestClient, token_alice: str):
    resp = client.post(
        "/chat/rid-alice-001",
        json={"pergunta": "qual o veredito?"},
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_id"] == "rid-alice-001"
    assert body["qtd_perguntas"] == 1
    assert body["pergunta"] == "qual o veredito?"
    assert "resposta" in body


def test_chat_200_quando_admin(client: TestClient, token_admin: str):
    resp = client.post(
        "/chat/rid-alice-001",
        json={"pergunta": "ping"},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp.status_code == 200


def test_chat_historico_e_limpar(client: TestClient, token_alice: str):
    headers = {"Authorization": f"Bearer {token_alice}"}
    client.post("/chat/rid-alice-001", json={"pergunta": "q1"}, headers=headers)
    client.post("/chat/rid-alice-001", json={"pergunta": "q2"}, headers=headers)

    hist = client.get("/chat/rid-alice-001/historico", headers=headers)
    assert hist.status_code == 200
    assert len(hist.json()["historico"]) == 2

    delete = client.delete("/chat/rid-alice-001/historico", headers=headers)
    assert delete.status_code == 204

    hist2 = client.get("/chat/rid-alice-001/historico", headers=headers)
    assert hist2.json()["historico"] == []


def test_chat_pergunta_vazia_rejeitada(client: TestClient, token_alice: str):
    resp = client.post(
        "/chat/rid-alice-001",
        json={"pergunta": ""},
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    # Pydantic rejeita antes do agente (min_length=1)
    assert resp.status_code == 422
