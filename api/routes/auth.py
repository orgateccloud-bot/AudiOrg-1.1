"""
ORGATEC – Rotas de Autenticação
POST /auth/login    → recebe email+senha, devolve access + refresh token
POST /auth/refresh  → recebe refresh token, devolve novo par de tokens
POST /auth/logout   → revoga o refresh token (jti vai para blacklist Redis)
GET  /auth/me       → devolve dados do usuário autenticado
POST /auth/seed     → cria usuário admin inicial (apenas se não existir)
"""

import os

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth.security import (
    create_token_pair,
    get_current_user,
    hash_password,
    needs_rehash,
    revoke_refresh_token,
    verify_password,
    verify_refresh_token,
    TokenData,
    TokenPair,
)
from api.dependencies import get_db
from nfa_extractor.infrastructure.database_v2 import User

router = APIRouter(prefix="/auth", tags=["Auth"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: int
    email: str
    nome: str
    role: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Autentica e retorna par access + refresh token."""
    user = db.query(User).filter(User.email == form.username).first()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada. Contate o administrador.")

    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(form.password)
        db.commit()

    token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
    pair = create_token_pair(token_data)

    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": pair.token_type,
        "expires_in": pair.expires_in,
        "user": {"id": user.id, "email": user.email, "nome": user.nome, "role": user.role},
    }


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    """Renova tokens usando refresh token válido."""
    token_data = verify_refresh_token(body.refresh_token)

    # Verificar se o usuário ainda existe e está ativo
    user = db.query(User).filter(User.id == int(token_data.sub)).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Conta desativada.")

    new_pair = create_token_pair(
        {"sub": str(user.id), "email": user.email, "role": user.role}
    )

    return {
        "access_token": new_pair.access_token,
        "refresh_token": new_pair.refresh_token,
        "token_type": new_pair.token_type,
        "expires_in": new_pair.expires_in,
        "user": {"id": user.id, "email": user.email, "nome": user.nome, "role": user.role},
    }


@router.post("/logout", status_code=200)
def logout(body: RefreshRequest):
    """Revoga o refresh token apresentado.

    Idempotente: se o jti já estiver revogado, segue retornando 200.
    Acaba retornando 401 só quando o token é inválido (assinatura ruim, tipo
    errado, expirado) — nesses casos não há o que revogar.
    """
    data = revoke_refresh_token(body.refresh_token)
    return {"detail": "Refresh token revogado.", "jti": data.jti}


@router.get("/me", response_model=MeResponse)
def me(current_user: TokenData = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == int(current_user.sub)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"id": user.id, "email": user.email, "nome": user.nome, "role": user.role}


@router.post("/seed", status_code=201)
def seed_admin(
    x_seed_token: str | None = Header(default=None, alias="X-Seed-Token"),
    db: Session = Depends(get_db),
):
    """Cria o usuário admin inicial.

    Segurança:
    - Exige header X-Seed-Token igual a env SEED_BOOTSTRAP_TOKEN
    - Senha do admin lida de env ADMIN_INITIAL_PASSWORD (mín 12 chars)
    - Falha se já houver qualquer admin no banco (one-shot)
    - Senha NÃO retornada na resposta
    """
    seed_token_env = os.getenv("SEED_BOOTSTRAP_TOKEN", "")
    if not seed_token_env or x_seed_token != seed_token_env:
        # Resposta neutra para não revelar existência do endpoint
        raise HTTPException(status_code=404, detail="Not Found")

    admin_email = os.getenv("ADMIN_EMAIL", "admin@orgatec.com.br")
    admin_password = os.getenv("ADMIN_INITIAL_PASSWORD", "")
    if not admin_password or len(admin_password) < 12:
        raise HTTPException(
            status_code=400,
            detail="ADMIN_INITIAL_PASSWORD não configurado ou < 12 caracteres.",
        )

    # One-shot: se já existe qualquer admin, recusa
    if db.query(User).filter(User.role == "admin").first():
        raise HTTPException(status_code=409, detail="Admin já existe.")

    admin = User(
        nome="Administrador ORGATEC",
        email=admin_email,
        hashed_password=hash_password(admin_password),
        role="admin",
        is_active=True,
    )
    db.add(admin)
    db.commit()
    return {"detail": "Usuário admin criado.", "email": admin_email}
