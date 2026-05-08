"""
Pacote de schemas Pydantic da API ORGATEC.
Importe diretamente do submodulo ou use os atalhos abaixo.
"""
from pydantic import BaseModel


# ── Agente IA ──────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    pergunta: str
    contexto: str | None = ""


class ChatResponse(BaseModel):
    response: str


from api.schemas.auditoria import (
    UploadAuditoriaParams,
    validar_arquivos,
)
from api.schemas.clientes import (
    ClienteCreate,
    ClienteListResponse,
    ClienteResponse,
    ClienteUpdate,
)
from api.schemas.laudos import (
    LaudoListResponse,
    LaudoResponse,
    TaskStatusResponse,
    UploadResponse,
)
from api.schemas.usuarios import (
    LoginRequest,
    MeResponse,
    SenhaUpdate,
    TokenResponse,
    UsuarioResponse,
)

__all__ = [
    # Agente IA
    "ChatRequest",
    "ChatResponse",
    # Clientes
    "ClienteCreate",
    "ClienteUpdate",
    "ClienteResponse",
    "ClienteListResponse",
    # Laudos / Tasks
    "LaudoResponse",
    "LaudoListResponse",
    "TaskStatusResponse",
    "UploadResponse",
    # Usuários / Auth
    "UsuarioResponse",
    "LoginRequest",
    "SenhaUpdate",
    "TokenResponse",
    "MeResponse",
    # Auditoria helpers
    "UploadAuditoriaParams",
    "validar_arquivos",
]
