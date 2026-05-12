"""Testes E2E das rotas /auth/* — login, refresh, me, seed."""
import os

os.environ["JWT_SECRET_KEY"] = "a" * 64

import pytest
from fastapi.testclient import TestClient

from api.auth.security import create_refresh_token, hash_password
from api.main import app
from nfa_extractor.infrastructure.database_v2 import SessionLocal, User

client = TestClient(app)


@pytest.fixture
def _user_ativo():
    """Cria usuário ativo, deleta no teardown."""
    db = SessionLocal()
    db.query(User).filter(User.email == "ativo@x.com").delete()
    u = User(
        nome="Ativo", email="ativo@x.com",
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


@pytest.fixture
def _user_inativo():
    db = SessionLocal()
    db.query(User).filter(User.email == "inativo@x.com").delete()
    u = User(
        nome="Inativo", email="inativo@x.com",
        hashed_password=hash_password("SenhaSegura123"),
        role="user", is_active=False,
    )
    db.add(u); db.commit(); db.refresh(u)
    user_id = u.id
    db.close()
    yield user_id
    db = SessionLocal()
    db.query(User).filter(User.id == user_id).delete()
    db.commit(); db.close()


# ── /auth/login ──────────────────────────────────────────────────────────────

class TestLogin:
    def test_credenciais_invalidas_retorna_401(self):
        res = client.post(
            "/auth/login",
            data={"username": "naoexiste@x.com", "password": "x"},
        )
        assert res.status_code == 401

    def test_login_sucesso_retorna_par_tokens(self, _user_ativo):
        res = client.post(
            "/auth/login",
            data={"username": "ativo@x.com", "password": "SenhaSegura123"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body and "refresh_token" in body
        assert body["user"]["email"] == "ativo@x.com"

    def test_login_user_inativo_retorna_403(self, _user_inativo):
        res = client.post(
            "/auth/login",
            data={"username": "inativo@x.com", "password": "SenhaSegura123"},
        )
        assert res.status_code == 403


# ── /auth/refresh ────────────────────────────────────────────────────────────

class TestRefresh:
    def test_refresh_user_inexistente_401(self):
        token = create_refresh_token({"sub": "999999", "email": "x@y.com"})
        res = client.post("/auth/refresh", json={"refresh_token": token})
        assert res.status_code == 401

    def test_refresh_user_inativo_403(self, _user_inativo):
        token = create_refresh_token({"sub": str(_user_inativo)})
        res = client.post("/auth/refresh", json={"refresh_token": token})
        assert res.status_code == 403

    def test_refresh_sucesso(self, _user_ativo):
        token = create_refresh_token({"sub": str(_user_ativo)})
        res = client.post("/auth/refresh", json={"refresh_token": token})
        assert res.status_code == 200
        assert "access_token" in res.json()


# ── /auth/me ─────────────────────────────────────────────────────────────────

class TestMe:
    def test_me_user_inexistente_404(self):
        from api.auth.security import create_access_token
        token = create_access_token({"sub": "999999", "email": "x@y.com"})
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 404

    def test_me_sucesso(self, _user_ativo):
        from api.auth.security import create_access_token
        token = create_access_token({"sub": str(_user_ativo), "email": "ativo@x.com"})
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "ativo@x.com"


# ── /auth/seed ───────────────────────────────────────────────────────────────

class TestSeed:
    def test_seed_sem_token_404(self, monkeypatch):
        monkeypatch.delenv("SEED_BOOTSTRAP_TOKEN", raising=False)
        res = client.post("/auth/seed")
        assert res.status_code == 404

    def test_seed_token_invalido_404(self, monkeypatch):
        monkeypatch.setenv("SEED_BOOTSTRAP_TOKEN", "secret-correto")
        res = client.post("/auth/seed", headers={"X-Seed-Token": "errado"})
        assert res.status_code == 404

    def test_seed_password_curta_400(self, monkeypatch):
        monkeypatch.setenv("SEED_BOOTSTRAP_TOKEN", "tk-12345")
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "curta")
        res = client.post("/auth/seed", headers={"X-Seed-Token": "tk-12345"})
        assert res.status_code == 400

    def test_seed_admin_existente_409(self, monkeypatch):
        # Garante que existe admin no banco
        db = SessionLocal()
        existente = db.query(User).filter(User.role == "admin").first()
        if not existente:
            adm = User(
                nome="x", email=f"adm-existente-{os.getpid()}@x.com",
                hashed_password=hash_password("SenhaForte123"),
                role="admin", is_active=True,
            )
            db.add(adm); db.commit()
        db.close()

        monkeypatch.setenv("SEED_BOOTSTRAP_TOKEN", "tk-ok")
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "SenhaForteOK1234567")
        res = client.post("/auth/seed", headers={"X-Seed-Token": "tk-ok"})
        assert res.status_code == 409

    def test_seed_sucesso_cria_admin(self, monkeypatch):
        # Remove qualquer admin
        db = SessionLocal()
        db.query(User).filter(User.role == "admin").delete()
        db.commit(); db.close()

        monkeypatch.setenv("SEED_BOOTSTRAP_TOKEN", "tk-seed")
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "SenhaInicialForte123")
        monkeypatch.setenv("ADMIN_EMAIL", "admin-seed-test@orgatec.com.br")
        res = client.post("/auth/seed", headers={"X-Seed-Token": "tk-seed"})
        assert res.status_code == 201
        assert res.json()["email"] == "admin-seed-test@orgatec.com.br"
        # Cleanup
        db = SessionLocal()
        db.query(User).filter(User.email == "admin-seed-test@orgatec.com.br").delete()
        db.commit(); db.close()
