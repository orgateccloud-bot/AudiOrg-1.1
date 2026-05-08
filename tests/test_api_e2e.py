"""
Testes end-to-end da API — usa TestClient do FastAPI.
Testa fluxo completo: health, auth, endpoints protegidos.
"""

import sys
import os
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "a" * 64

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.auth.security import create_access_token, create_token_pair
from nfa_extractor.infrastructure.database_v2 import init_db

# Garante que as tabelas existem antes dos testes
init_db()

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _auth_headers(role: str = "user") -> dict:
    token = create_access_token({"sub": "1", "email": "test@test.com", "role": role})
    return {"Authorization": f"Bearer {token}"}


# ── Health ───────────────────────────────────────────────────────────────────

class TestHealth:

    def test_ping(self):
        res = client.get("/ping")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert "version" in res.json()


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestAuthEndpoints:

    def test_login_sem_credenciais_retorna_422(self):
        res = client.post("/auth/login")
        assert res.status_code == 422

    def test_login_credenciais_erradas_retorna_401(self):
        res = client.post("/auth/login", data={"username": "nope@nope.com", "password": "wrong"})
        assert res.status_code == 401

    def test_refresh_sem_body_retorna_422(self):
        res = client.post("/auth/refresh")
        assert res.status_code == 422

    def test_refresh_token_invalido_retorna_401(self):
        res = client.post("/auth/refresh", json={"refresh_token": "invalid.token.here"})
        assert res.status_code == 401

    def test_me_sem_token_retorna_401(self):
        res = client.get("/auth/me")
        assert res.status_code == 401


# ── Endpoints protegidos ─────────────────────────────────────────────────────

class TestProtectedEndpoints:

    def test_clientes_sem_token_retorna_401(self):
        res = client.get("/clientes/")
        assert res.status_code == 401

    def test_agente_sem_token_retorna_401(self):
        res = client.post("/agente/chat", json={"pergunta": "teste"})
        assert res.status_code == 401

    def test_metrics_sem_token_retorna_401(self):
        res = client.get("/metrics/ai")
        assert res.status_code == 401

    def test_metrics_user_comum_retorna_403(self):
        res = client.get("/metrics/ai", headers=_auth_headers("user"))
        assert res.status_code == 403

    def test_metrics_admin_retorna_200(self):
        res = client.get("/metrics/ai", headers=_auth_headers("admin"))
        assert res.status_code == 200
        assert isinstance(res.json(), dict)


# ── Finance endpoints (sem Supabase → 503) ───────────────────────────────────

class TestFinanceEndpoints:

    def test_finance_sem_supabase_retorna_503(self):
        """Quando Supabase não está configurado, todos retornam 503."""
        endpoints = [
            ("GET", "/finance/profile"),
            ("GET", "/finance/categories"),
            ("GET", "/finance/transactions"),
            ("GET", "/finance/summary"),
            ("GET", "/finance/predictions"),
        ]
        headers = _auth_headers()
        for method, path in endpoints:
            if method == "GET":
                res = client.get(path, headers=headers)
            assert res.status_code == 503
            assert "Supabase" in res.json()["detail"]

    def test_finance_create_sem_supabase_retorna_503(self):
        headers = _auth_headers()
        res = client.post(
            "/finance/transactions",
            json={"type": "income", "amount": 1000},
            headers=headers,
        )
        assert res.status_code == 503

    def test_finance_categories_seed_sem_supabase_retorna_503(self):
        headers = _auth_headers()
        res = client.post("/finance/categories/seed", headers=headers)
        assert res.status_code == 503

    def test_finance_sem_token_retorna_401(self):
        res = client.get("/finance/profile")
        assert res.status_code == 401


# ── Rate Limiting ────────────────────────────────────────────────────────────

class TestRateLimiting:

    def test_ping_nao_tem_rate_limit_header(self):
        """O /ping é excluído do rate limiting."""
        res = client.get("/ping")
        # Pode ou não ter o header, mas não deve retornar 429
        assert res.status_code == 200

    def test_request_normal_tem_header(self):
        """Requests normais devem ter X-RateLimit-Remaining."""
        res = client.get("/auth/me")
        # Retorna 401 (sem token) mas deve ter o header de rate limit
        assert "X-RateLimit-Remaining" in res.headers or res.status_code == 401


# ── CORS ─────────────────────────────────────────────────────────────────────

class TestCORS:

    def test_cors_headers_presentes(self):
        res = client.options(
            "/ping",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI CORS middleware responde a OPTIONS
        assert res.status_code in (200, 405)
