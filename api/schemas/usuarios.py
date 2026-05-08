"""
Schemas Pydantic — domínio Usuários e Autenticação
"""
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ── Usuário ───────────────────────────────────────────────────────────────────

class UsuarioResponse(BaseModel):
    """Serialização de saída de um usuário (sem hashed_password)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    role: str
    is_active: bool


# ── Auth Requests ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Payload JSON para POST /auth/login (alternativa ao OAuth2PasswordRequestForm)."""

    email: EmailStr
    password: str = Field(..., min_length=6, description="Senha do usuário")


class SenhaUpdate(BaseModel):
    """Payload para troca de senha."""

    senha_atual: str = Field(..., min_length=6)
    nova_senha: str = Field(..., min_length=8)

    @field_validator("nova_senha")
    @classmethod
    def complexidade_senha(cls, v: str) -> str:
        erros = []
        if not re.search(r"[A-Z]", v):
            erros.append("uma letra maiúscula")
        if not re.search(r"[a-z]", v):
            erros.append("uma letra minúscula")
        if not re.search(r"\d", v):
            erros.append("um número")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", v):
            erros.append("um caractere especial")
        if erros:
            raise ValueError(f"Senha fraca — faltam: {', '.join(erros)}.")
        return v


# ── Auth Responses ────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Resposta JWT após autenticação bem-sucedida."""

    access_token: str
    token_type: str = "bearer"
    user: UsuarioResponse


class MeResponse(BaseModel):
    """Dados do usuário autenticado (GET /auth/me)."""

    id: int
    email: str
    nome: str
    role: str
