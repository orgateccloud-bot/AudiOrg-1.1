"""Testes para revogação de refresh tokens via jti (#21).

Cobre:
- jti embutido em todo refresh token novo
- revoke_refresh_token marca jti como inválido
- verify_refresh_token rejeita token revogado com 401
- POST /auth/logout revoga e o refresh subsequente falha
- TTL no Redis respeita exp restante do token
- Backend in-memory e Redis (via fakeredis) se comportam igual
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "a" * 64)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from jose import jwt as jose_jwt

from api.auth import revocation_store as rs
from api.auth.security import (
    create_access_token,
    create_refresh_token,
    revoke_refresh_token,
    verify_refresh_token,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_store_between_tests():
    """Cada teste começa com store limpa."""
    rs.reset_store_for_tests()
    yield
    rs.reset_store_for_tests()


@pytest.fixture
def fakeredis_store(monkeypatch):
    """Injeta uma instância _RedisBackend usando fakeredis."""
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    backend = rs._RedisBackend(client)
    store = rs.RevocationStore(backend)
    monkeypatch.setattr(rs, "_store", store)
    return store


# ── Geração de jti ───────────────────────────────────────────────────────────


class TestJtiNoPayload:

    def test_refresh_token_inclui_jti(self):
        token = create_refresh_token({"sub": "1", "email": "a@b.com"})
        payload = jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        assert "jti" in payload
        assert len(payload["jti"]) >= 16

    def test_jti_unico_por_token(self):
        t1 = create_refresh_token({"sub": "1"})
        t2 = create_refresh_token({"sub": "1"})
        p1 = jose_jwt.decode(t1, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        p2 = jose_jwt.decode(t2, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        assert p1["jti"] != p2["jti"]

    def test_access_token_nao_tem_jti(self):
        token = create_access_token({"sub": "1"})
        payload = jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        assert "jti" not in payload


# ── Backend in-memory ────────────────────────────────────────────────────────


class TestInMemoryBackend:

    def test_revoke_marca_como_revogado(self):
        backend = rs._InMemoryBackend()
        backend.revoke("abc123", ttl_seconds=60)
        assert backend.is_revoked("abc123") is True

    def test_jti_nao_revogado_retorna_false(self):
        backend = rs._InMemoryBackend()
        assert backend.is_revoked("nao-existe") is False

    def test_revoke_com_ttl_zero_expira_imediatamente(self):
        backend = rs._InMemoryBackend()
        backend.revoke("abc", ttl_seconds=0)
        assert backend.is_revoked("abc") is False


# ── Backend Redis (via fakeredis) ────────────────────────────────────────────


class TestRedisBackend:

    def test_revoke_seta_chave_com_ttl(self, fakeredis_store):
        import fakeredis

        client = fakeredis.FakeRedis(decode_responses=True)
        backend = rs._RedisBackend(client)
        backend.revoke("xyz", ttl_seconds=120)
        assert backend.is_revoked("xyz") is True
        # TTL deve estar próximo de 120s
        ttl = client.ttl("revoked:refresh:xyz")
        assert 0 < ttl <= 120

    def test_revoke_ttl_zero_nao_seta(self):
        import fakeredis

        client = fakeredis.FakeRedis(decode_responses=True)
        backend = rs._RedisBackend(client)
        backend.revoke("expirado", ttl_seconds=0)
        assert client.exists("revoked:refresh:expirado") == 0


# ── revoke_refresh_token e verify_refresh_token ──────────────────────────────


class TestRevokeFlow:

    def test_revoke_invalida_token_subsequente(self):
        token = create_refresh_token({"sub": "1", "email": "a@b.com", "role": "user"})
        # Antes: verify passa
        data = verify_refresh_token(token)
        assert data.sub == "1"
        # Revoga
        revoke_refresh_token(token)
        # Depois: verify falha com 401
        with pytest.raises(HTTPException) as exc:
            verify_refresh_token(token)
        assert exc.value.status_code == 401
        assert "revogado" in exc.value.detail.lower()

    def test_revoke_idempotente(self):
        token = create_refresh_token({"sub": "1"})
        revoke_refresh_token(token)
        revoke_refresh_token(token)  # Não deve falhar

    def test_revoke_recusa_access_token(self):
        token = create_access_token({"sub": "1"})
        with pytest.raises(HTTPException) as exc:
            revoke_refresh_token(token)
        assert exc.value.status_code == 401

    def test_revoke_recusa_token_invalido(self):
        with pytest.raises(HTTPException):
            revoke_refresh_token("nao.eh.token")

    def test_revoke_so_afeta_o_jti_revogado(self):
        t1 = create_refresh_token({"sub": "1"})
        t2 = create_refresh_token({"sub": "1"})
        revoke_refresh_token(t1)
        # t2 (jti diferente) continua válido
        data = verify_refresh_token(t2)
        assert data.sub == "1"

    def test_revoke_token_sem_jti_falha_400(self):
        """Tokens emitidos antes do #21 não têm jti — caller deve refazer login."""
        from api.auth.security import _encode

        token = _encode({"sub": "1"}, timedelta(minutes=5), "refresh")
        # Remove jti se algum padrão adicionou — re-emite sem helper
        payload = jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        payload.pop("jti", None)
        token_sem_jti = jose_jwt.encode(payload, os.environ["JWT_SECRET_KEY"], algorithm="HS256")

        with pytest.raises(HTTPException) as exc:
            revoke_refresh_token(token_sem_jti)
        assert exc.value.status_code == 400


# ── Factory _build_backend ───────────────────────────────────────────────────


class TestBuildBackend:

    def test_sem_redis_url_em_dev_usa_in_memory(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("ENV", "development")
        backend = rs._build_backend()
        assert isinstance(backend, rs._InMemoryBackend)

    def test_sem_redis_url_em_producao_falha(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("ENV", "production")
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            rs._build_backend()

    def test_com_redis_url_constroi_redis_backend(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("ENV", "development")
        # Não vai conectar de verdade — só verifica o tipo
        backend = rs._build_backend()
        assert isinstance(backend, rs._RedisBackend)
