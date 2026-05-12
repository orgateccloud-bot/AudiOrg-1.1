"""
ORGATEC – Camada de autenticação e autorização (JWT).

Expõe:
- hash_password / verify_password / needs_rehash — argon2id com fallback bcrypt
- create_access_token / create_refresh_token — JWT HS256 com tipo "access"/"refresh"
- create_token_pair — gera o par e o payload de resposta
- verify_refresh_token / get_current_user — validação com HTTPException(401)
- TokenData / TokenPair — schemas Pydantic v2

Senhas: argon2id é o padrão para hashes novos. Hashes bcrypt herdados ($2a/$2b/$2y$)
continuam verificáveis para não deslogar usuários antigos; verify_password() detecta
o algoritmo pelo prefixo e o login endpoint deve chamar needs_rehash() para regerar
o hash em argon2 transparentemente no próximo login bem-sucedido.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# ── Configurações ────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def _secret_key() -> str:
    """Lê JWT_SECRET_KEY no momento do uso (permite que testes setem antes)."""
    key = os.getenv("JWT_SECRET_KEY")
    if not key or len(key) < 32:
        # Fallback dev — produção exige env válido
        return "ORGATEC_SOVEREIGN_SHIELD_2026_DEV_FALLBACK_64BYTES_PLACEHOLDER"
    return key


_argon2 = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=True)


# ── Schemas ──────────────────────────────────────────────────────────────────


class TokenData(BaseModel):
    sub: str
    email: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ── Senhas (argon2id + fallback bcrypt) ──────────────────────────────────────


def hash_password(plain: str) -> str:
    """Gera hash argon2id da senha em texto puro."""
    return _argon2.hash(plain)


def get_password_hash(plain: str) -> str:
    """Alias retrocompatível — chamadores antigos usavam este nome."""
    return hash_password(plain)


def _verify_bcrypt(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def verify_password(plain: str, hashed: str) -> bool:
    """Confere senha contra hash armazenado (argon2 ou bcrypt legacy)."""
    if hashed.startswith(_BCRYPT_PREFIXES):
        return _verify_bcrypt(plain, hashed)
    try:
        _argon2.verify(hashed, plain)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True quando o hash deve ser regerado: bcrypt legacy ou argon2 com parâmetros antigos."""
    if hashed.startswith(_BCRYPT_PREFIXES):
        return True
    try:
        return _argon2.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


# ── JWT — emissão ────────────────────────────────────────────────────────────


def _encode(data: dict, expires_delta: timedelta, token_type: str) -> str:
    payload = data.copy()
    payload["type"] = token_type
    payload["exp"] = datetime.utcnow() + expires_delta
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Emite access token (type=access, exp curta)."""
    delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return _encode(data, delta, "access")


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Emite refresh token (type=refresh, exp longa)."""
    delta = expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return _encode(data, delta, "refresh")


def create_token_pair(data: dict) -> TokenPair:
    """Gera par access+refresh para resposta de /auth/login e /auth/refresh."""
    return TokenPair(
        access_token=create_access_token(data),
        refresh_token=create_refresh_token(data),
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ── JWT — validação ──────────────────────────────────────────────────────────


def _decode(token: str) -> dict:
    """Decodifica e levanta HTTPException(401) em qualquer falha."""
    try:
        return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _to_token_data(payload: dict) -> TokenData:
    return TokenData(
        sub=str(payload.get("sub", "")),
        email=payload.get("email"),
        role=payload.get("role"),
        type=payload.get("type"),
    )


def verify_refresh_token(token: str) -> TokenData:
    """Valida refresh token; rejeita access ou inválido com 401."""
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não é do tipo refresh.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _to_token_data(payload)


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """Dependency FastAPI: extrai e valida access token; rejeita refresh ou inválido."""
    payload = _decode(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não é do tipo access.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _to_token_data(payload)
