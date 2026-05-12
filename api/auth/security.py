"""
ORGATEC – Camada de autenticação e autorização (JWT).

Expõe:
- hash_password / verify_password / needs_rehash — argon2id com fallback bcrypt
- create_access_token / create_refresh_token — JWT HS256 com tipo "access"/"refresh"
- create_token_pair — gera o par e o payload de resposta
- verify_refresh_token / get_current_user — validação com HTTPException(401)
- revoke_refresh_token — marca jti como revogado (Redis/in-memory)
- TokenData / TokenPair — schemas Pydantic v2

Senhas: argon2id é o padrão para hashes novos. Hashes bcrypt herdados ($2a/$2b/$2y$)
continuam verificáveis para não deslogar usuários antigos; verify_password() detecta
o algoritmo pelo prefixo e o login endpoint deve chamar needs_rehash() para regerar
o hash em argon2 transparentemente no próximo login bem-sucedido.

Revogação de refresh tokens: cada refresh token carrega um `jti` aleatório.
verify_refresh_token() consulta o store de revogação (Redis em prod, in-memory em dev)
antes de aceitar o token. POST /auth/logout chama revoke_refresh_token() para marcar
o jti como inválido até a data de expiração natural.
"""
from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from api.auth.revocation_store import get_store as _get_revocation_store

# ── Configurações ────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def _secret_key() -> str:
    """Lê JWT_SECRET_KEY no momento do uso (permite que testes setem antes).

    Em produção (APP_ENV=production), levanta RuntimeError se a variável
    não estiver configurada ou for muito curta. Em dev/test, usa fallback
    previsível APENAS para permitir testes locais sem configurar segredo.
    """
    key = os.getenv("JWT_SECRET_KEY")
    if not key or len(key) < 32:
        if os.getenv("APP_ENV", "").lower() == "production":
            raise RuntimeError(
                "JWT_SECRET_KEY ausente ou < 32 caracteres em produção. "
                "Gere com: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        return "ORGATEC_DEV_FALLBACK_KEY_NAO_USAR_EM_PRODUCAO_32BYTES"
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
    jti: Optional[str] = None
    exp: Optional[int] = None


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
    payload["exp"] = datetime.now(UTC) + expires_delta
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Emite access token (type=access, exp curta)."""
    delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return _encode(data, delta, "access")


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Emite refresh token (type=refresh, exp longa).

    Inclui `jti` aleatório (token_urlsafe(16)) para permitir revogação granular
    sem invalidar todos os tokens do usuário.
    """
    delta = expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = data.copy()
    payload.setdefault("jti", secrets.token_urlsafe(16))
    return _encode(payload, delta, "refresh")


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
        jti=payload.get("jti"),
        exp=payload.get("exp"),
    )


def verify_refresh_token(token: str) -> TokenData:
    """Valida refresh token; rejeita access, inválido ou revogado com 401."""
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não é do tipo refresh.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    jti = payload.get("jti")
    if jti and _get_revocation_store().is_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revogado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _to_token_data(payload)


def revoke_refresh_token(token: str) -> TokenData:
    """Revoga um refresh token válido pelo seu jti. Idempotente.

    Retorna o TokenData do token revogado para que o caller possa logar/auditar.
    O TTL no Redis é calibrado para o `exp` restante — sem desperdício de memória.
    """
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Apenas refresh tokens podem ser revogados.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    jti = payload.get("jti")
    if not jti:
        # Tokens antigos (pré-#21) não têm jti — nada a revogar individualmente.
        # O cliente deve descartar o token e refazer login.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token sem jti — emita um novo par via /auth/login.",
        )
    exp = int(payload.get("exp", 0))
    ttl_seconds = max(exp - int(datetime.now(UTC).timestamp()), 0)
    _get_revocation_store().revoke(jti, ttl_seconds)
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
