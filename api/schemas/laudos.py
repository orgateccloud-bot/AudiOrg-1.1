"""
Schemas Pydantic — domínio Laudos e Tarefas de Auditoria
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Laudo ─────────────────────────────────────────────────────────────────────

class LaudoResponse(BaseModel):
    """Serialização de saída de um laudo gerado."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    data_auditoria: datetime | None = None
    qtd_notas: int | None = None
    valor_total: float | None = None
    qtd_anomalias: int | None = None
    pdf_path: str | None = None
    veredito_resumo: str | None = None   # truncado em 300 chars na resposta


class LaudoListResponse(BaseModel):
    """Lista de laudos (histórico)."""

    items: list[LaudoResponse]
    total: int


# ── Status de Tarefa ──────────────────────────────────────────────────────────

StatusLiteral = Literal[
    "iniciado",
    "extraindo",
    "processando",
    "analisando",
    "gerando_relatorio",
    "concluido",
    "erro",
]

class TaskStatusResponse(BaseModel):
    """Resposta do endpoint GET /auditoria/status/{task_id}."""

    status: str = Field(..., description="Estado atual da tarefa")
    progress: int = Field(0, ge=0, le=100, description="Progresso percentual")
    label: str | None = Field(None, description="Descrição legível do estado atual")
    resultado: str | None = Field(None, description="Resumo final quando concluído")
    erro: str | None = Field(None, description="Mensagem de erro se status == 'erro'")


# ── Upload Response ───────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Resposta imediata ao POST /auditoria/upload/{client_id}."""

    task_id: str
    message: str
    arquivos: dict   # {"pdf": int, "xml": int, "total": int}
