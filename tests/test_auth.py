"""Testes para api/auth/security.py — JWT, refresh token, validações."""

import os
import sys
from pathlib import Path

import pytest

# Setar JWT_SECRET_KEY antes de importar o módulo
os.environ["JWT_SECRET_KEY"] = "a" * 64

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from jose import jwt as jose_jwt

from api.auth.security import (
    TokenPair,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    get_current_user,
    hash_password,
    verify_password,
    verify_refresh_token,
)


class TestBcrypt:

    def test_hash_e_verify(self):
        plain = "SenhaForte123!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_senha_errada_falha(self):
        hashed = hash_password("correta")
        assert verify_password("errada", hashed) is False


class TestAccessToken:

    def test_cria_token_valido(self):
        token = create_access_token({"sub": "1", "email": "a@b.com", "role": "user"})
        payload = jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        assert payload["sub"] == "1"
        assert payload["type"] == "access"

    def test_token_contem_expiracao(self):
        token = create_access_token({"sub": "1"})
        payload = jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        assert "exp" in payload


class TestRefreshToken:

    def test_cria_refresh_token(self):
        token = create_refresh_token({"sub": "1", "email": "a@b.com", "role": "admin"})
        payload = jose_jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=["HS256"])
        assert payload["type"] == "refresh"
        assert payload["sub"] == "1"

    def test_verify_refresh_token_valido(self):
        token = create_refresh_token({"sub": "42", "email": "x@y.com", "role": "user"})
        data = verify_refresh_token(token)
        assert data.sub == "42"
        assert data.email == "x@y.com"

    def test_verify_rejeita_access_como_refresh(self):
        token = create_access_token({"sub": "1"})
        with pytest.raises(HTTPException) as exc_info:
            verify_refresh_token(token)
        assert exc_info.value.status_code == 401

    def test_verify_rejeita_token_invalido(self):
        with pytest.raises(HTTPException):
            verify_refresh_token("token.invalido.aqui")


class TestTokenPair:

    def test_cria_par(self):
        pair = create_token_pair({"sub": "1", "email": "a@b.com", "role": "user"})
        assert isinstance(pair, TokenPair)
        assert pair.access_token != pair.refresh_token
        assert pair.token_type == "bearer"
        assert pair.expires_in > 0


class TestGetCurrentUser:

    def test_valida_access_token(self):
        token = create_access_token({"sub": "5", "email": "e@f.com", "role": "admin"})
        data = get_current_user(token)
        assert data.sub == "5"
        assert data.role == "admin"

    def test_rejeita_refresh_como_access(self):
        token = create_refresh_token({"sub": "5"})
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(token)
        assert exc_info.value.status_code == 401

    def test_rejeita_token_expirado(self):
        from datetime import timedelta
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(HTTPException):
            get_current_user(token)
