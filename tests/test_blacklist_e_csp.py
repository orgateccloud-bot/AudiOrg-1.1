"""Testes para JWT blacklist + CSP nonce dinâmico + xgboost lazy load."""
import os
import time

os.environ["JWT_SECRET_KEY"] = "a" * 64

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.auth import blacklist
from api.auth.security import create_access_token, hash_password
from api.main import app
from nfa_extractor.infrastructure.database_v2 import SessionLocal, User

client = TestClient(app)


@pytest.fixture(autouse=True)
def _limpar_blacklist():
    blacklist._limpar_tudo()
    yield
    blacklist._limpar_tudo()


# ── api/auth/blacklist ───────────────────────────────────────────────────────

class TestBlacklist:
    def test_token_nao_adicionado_nao_esta_revogado(self):
        assert blacklist.esta_revogado("tok-aleatorio") is False

    def test_adicionar_e_verificar(self):
        tok = "tok-1"
        blacklist.adicionar(tok, time.time() + 3600)
        assert blacklist.esta_revogado(tok) is True

    def test_token_expirado_remove_automaticamente(self):
        tok = "tok-velho"
        blacklist.adicionar(tok, time.time() - 1)  # já expirou
        assert blacklist.esta_revogado(tok) is False

    def test_hash_token_isola(self):
        # Tokens diferentes geram hashes diferentes
        from api.auth.blacklist import _hash_token
        assert _hash_token("a") != _hash_token("b")
        assert _hash_token("a") == _hash_token("a")

    def test_limpar_tudo_reseta(self):
        blacklist.adicionar("x", time.time() + 60)
        blacklist._limpar_tudo()
        assert blacklist.esta_revogado("x") is False


# ── /auth/logout ─────────────────────────────────────────────────────────────

@pytest.fixture
def _user_logout():
    db = SessionLocal()
    db.query(User).filter(User.email == "logout@x.com").delete()
    u = User(
        nome="Logout", email="logout@x.com",
        hashed_password=hash_password("SenhaSegura123"),
        role="user", is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    user_id = u.id
    db.close()
    yield user_id
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit(); db.close()


class TestLogout:
    def test_logout_revoga_token_e_subsequente_falha(self, _user_logout):
        token = create_access_token({"sub": str(_user_logout), "email": "logout@x.com"})
        # /me funciona inicialmente
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        # Logout revoga
        res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 204
        # /me agora falha
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_logout_token_invalido_retorna_401(self):
        res = client.post("/auth/logout", headers={"Authorization": "Bearer token.lixo.aqui"})
        assert res.status_code == 401


# ── CSP nonce dinâmico ──────────────────────────────────────────────────────

class TestCspNonce:
    def test_resposta_inclui_nonce_no_csp(self):
        res = client.get("/ping")
        csp = res.headers.get("Content-Security-Policy", "")
        assert "nonce-" in csp
        assert "'unsafe-inline'" not in csp

    def test_nonces_diferentes_entre_requests(self):
        r1 = client.get("/ping").headers.get("Content-Security-Policy", "")
        r2 = client.get("/ping").headers.get("Content-Security-Policy", "")
        # Os dois CSPs devem diferir pelo nonce
        assert r1 != r2

    @pytest.mark.asyncio
    async def test_csp_estatico_se_passado_explicitamente(self):
        from api.middleware.security_headers import SecurityHeadersMiddleware

        mw = SecurityHeadersMiddleware(app=None, csp="default-src 'self'")
        req = MagicMock()
        req.url.scheme = "http"
        req.url.path = "/"
        req.state = type("S", (), {})()

        async def _next(_r):
            r = MagicMock()
            r.headers = {}
            return r

        resp = await mw.dispatch(req, _next)
        assert resp.headers["Content-Security-Policy"] == "default-src 'self'"

    @pytest.mark.asyncio
    async def test_nonce_disponivel_em_request_state(self):
        """O middleware popula request.state.csp_nonce para uso em templates."""
        from api.middleware.security_headers import SecurityHeadersMiddleware
        mw = SecurityHeadersMiddleware(app=None)
        capturado = {}

        class _S:
            pass

        req = MagicMock()
        req.url.scheme = "http"
        req.url.path = "/"
        req.state = _S()

        async def _next(r):
            capturado["nonce"] = r.state.csp_nonce
            resp = MagicMock()
            resp.headers = {}
            return resp

        await mw.dispatch(req, _next)
        assert "nonce" in capturado
        assert len(capturado["nonce"]) > 0


# ── xgboost lazy load ───────────────────────────────────────────────────────

class TestXgboostLazy:
    def test_modelo_atual_carrega_sob_demanda(self, monkeypatch):
        from horizon_blue_one.ml import xgboost_scorer as xgb_mod
        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", False)
        monkeypatch.setattr(xgb_mod, "_xgb_model", None)
        # Sem XGBOOST_MODEL_PATH → não tenta carregar nada
        monkeypatch.delenv("XGBOOST_MODEL_PATH", raising=False)
        assert xgb_mod._modelo_atual() is None
        assert xgb_mod._xgb_load_attempted is True

    def test_modelo_atual_so_carrega_uma_vez(self, monkeypatch):
        from horizon_blue_one.ml import xgboost_scorer as xgb_mod
        chamadas = []
        original = xgb_mod._try_load_model

        def _spy():
            chamadas.append(1)
            original()

        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", False)
        monkeypatch.setattr(xgb_mod, "_try_load_model", _spy)
        xgb_mod._modelo_atual()
        xgb_mod._modelo_atual()
        xgb_mod._modelo_atual()
        # Só carregou na primeira vez
        assert len(chamadas) == 1
