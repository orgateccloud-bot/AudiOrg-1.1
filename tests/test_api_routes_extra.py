"""Testes de integração das rotas API — clientes, auth, agente, auditoria."""
import os
from unittest.mock import patch

os.environ["JWT_SECRET_KEY"] = "a" * 64

import pytest
from fastapi.testclient import TestClient

from api.auth.security import create_access_token, hash_password
from api.main import app
from nfa_extractor.infrastructure.database_v2 import Cliente, SessionLocal, User, init_db

init_db()
client = TestClient(app)


def _auth_headers(role: str = "admin", user_id: str = "1") -> dict:
    token = create_access_token({"sub": user_id, "email": "t@t.com", "role": role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _limpa_clientes():
    """Garante DB limpo de clientes entre testes."""
    with SessionLocal() as db:
        db.query(Cliente).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(Cliente).delete()
        db.commit()


# ── /clientes/ ───────────────────────────────────────────────────────────────

class TestClientesCRUD:
    def test_listar_clientes_autenticado_retorna_lista(self):
        # Cria um usuário válido para o get_current_user
        res = client.get("/clientes/", headers=_auth_headers())
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_criar_cliente_sucesso(self):
        res = client.post(
            "/clientes/",
            json={"nome": "Produtor Rural", "cpf_cnpj": "52998224725"},
            headers=_auth_headers(),
        )
        assert res.status_code == 201
        body = res.json()
        assert body["nome"] == "Produtor Rural"
        assert body["cpf_cnpj"] == "52998224725"

    def test_criar_cliente_duplicado_retorna_409(self):
        # Cria um cliente
        client.post(
            "/clientes/",
            json={"nome": "Primeiro", "cpf_cnpj": "52998224725"},
            headers=_auth_headers(),
        )
        # Tenta duplicar
        res = client.post(
            "/clientes/",
            json={"nome": "Segundo", "cpf_cnpj": "52998224725"},
            headers=_auth_headers(),
        )
        assert res.status_code == 409
        assert "já cadastrado" in res.json()["detail"]

    def test_criar_cliente_cpf_invalido_422(self):
        res = client.post(
            "/clientes/",
            json={"nome": "NomeOk", "cpf_cnpj": "00000000000"},
            headers=_auth_headers(),
        )
        assert res.status_code == 422

    def test_remover_cliente_existente(self):
        criado = client.post(
            "/clientes/",
            json={"nome": "ParaApagar", "cpf_cnpj": "52998224725"},
            headers=_auth_headers(),
        )
        client_id = criado.json()["id"]
        res = client.delete(f"/clientes/{client_id}", headers=_auth_headers())
        assert res.status_code == 204

    def test_remover_cliente_inexistente_404(self):
        res = client.delete("/clientes/99999", headers=_auth_headers())
        assert res.status_code == 404


# ── /auth/login (fluxo feliz) ────────────────────────────────────────────────

class TestAuthFluxoFeliz:
    def _criar_user(self, email="login@test.com", senha="SenhaForte123!"):
        with SessionLocal() as db:
            # Remove se existir
            existente = db.query(User).filter_by(email=email).first()
            if existente:
                db.delete(existente)
                db.commit()
            u = User(
                nome="Teste",
                email=email,
                hashed_password=hash_password(senha),
                role="user",
                is_active=True,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            return u.id

    def test_login_credenciais_corretas_retorna_token(self):
        self._criar_user(email="ok@test.com", senha="SenhaForte123!")
        res = client.post(
            "/auth/login",
            data={"username": "ok@test.com", "password": "SenhaForte123!"},
        )
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["user"]["email"] == "ok@test.com"

    def test_login_user_inativo_retorna_403(self):
        with SessionLocal() as db:
            existente = db.query(User).filter_by(email="inativo@test.com").first()
            if existente:
                db.delete(existente)
                db.commit()
            u = User(
                nome="Inativo", email="inativo@test.com",
                hashed_password=hash_password("SenhaForte123!"),
                role="user", is_active=False,
            )
            db.add(u)
            db.commit()
        res = client.post(
            "/auth/login",
            data={"username": "inativo@test.com", "password": "SenhaForte123!"},
        )
        assert res.status_code == 403

    def test_refresh_com_token_valido_renova(self):
        self._criar_user(email="refresh@test.com")
        # 1) Login para obter refresh token
        login = client.post(
            "/auth/login",
            data={"username": "refresh@test.com", "password": "SenhaForte123!"},
        )
        refresh_token = login.json()["refresh_token"]
        # 2) Usa o refresh
        res = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_refresh_user_apagado_retorna_401(self):
        uid = self._criar_user(email="apagado@test.com")
        login = client.post(
            "/auth/login",
            data={"username": "apagado@test.com", "password": "SenhaForte123!"},
        )
        refresh = login.json()["refresh_token"]
        # Apaga o user
        with SessionLocal() as db:
            u = db.query(User).filter_by(id=uid).first()
            db.delete(u)
            db.commit()
        res = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert res.status_code == 401

    def test_me_com_token_valido_retorna_dados(self):
        uid = self._criar_user(email="me@test.com")
        token = create_access_token({"sub": str(uid), "email": "me@test.com", "role": "user"})
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "me@test.com"

    def test_me_user_inexistente_404(self):
        # token aponta para id que não existe
        token = create_access_token({"sub": "99999", "email": "x@y.com", "role": "user"})
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 404


# ── /auth/seed ───────────────────────────────────────────────────────────────

class TestAuthSeed:
    def test_sem_seed_token_retorna_404(self):
        res = client.post("/auth/seed", headers={"X-Seed-Token": "errado"})
        assert res.status_code == 404

    def test_seed_token_correto_mas_password_curta_400(self, monkeypatch):
        monkeypatch.setenv("SEED_BOOTSTRAP_TOKEN", "supersecret")
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "curta")
        res = client.post("/auth/seed", headers={"X-Seed-Token": "supersecret"})
        assert res.status_code == 400

    def test_seed_com_admin_existente_409(self, monkeypatch):
        # Garante que existe admin
        with SessionLocal() as db:
            existente = db.query(User).filter_by(role="admin").first()
            if not existente:
                db.add(User(
                    nome="Adm", email="adm@orgatec.com.br",
                    hashed_password=hash_password("SenhaForteSuficiente1!"),
                    role="admin", is_active=True,
                ))
                db.commit()
        monkeypatch.setenv("SEED_BOOTSTRAP_TOKEN", "supersecret")
        monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "SenhaForteSuficiente1!")
        res = client.post("/auth/seed", headers={"X-Seed-Token": "supersecret"})
        assert res.status_code == 409


# ── /agente/chat ─────────────────────────────────────────────────────────────

class TestAgenteChat:
    def test_chat_com_perguntar_mockado_retorna_200(self):
        with patch(
            "nfa_extractor.infrastructure.ai_client.perguntar",
            return_value="resposta-da-ia",
        ):
            res = client.post(
                "/agente/chat",
                json={"pergunta": "oi", "contexto": "ctx"},
                headers=_auth_headers(),
            )
        assert res.status_code == 200
        assert res.json()["response"] == "resposta-da-ia"

    def test_chat_quando_perguntar_quebra_500(self):
        with patch(
            "nfa_extractor.infrastructure.ai_client.perguntar",
            side_effect=RuntimeError("falha-ia"),
        ):
            res = client.post(
                "/agente/chat",
                json={"pergunta": "oi", "contexto": ""},
                headers=_auth_headers(),
            )
        assert res.status_code == 500
        assert "falha-ia" in res.json()["detail"]
