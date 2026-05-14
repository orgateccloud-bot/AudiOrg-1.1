"""Endpoint de chat conversacional sobre laudo emitido (Fase 1).

POST /chat/{result_id} → recebe pergunta, devolve resposta de Claude com
@Delta aplicado. Usuário só pode conversar sobre laudos que ele mesmo
gerou (admin vê todos).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth.security import TokenData, get_current_user
from api.services.auditoria import resultados_store

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Sessão de chat (in-memory por enquanto; P0-2 vai migrar para DB) ─────────

_chat_sessions: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    resposta: str
    pergunta: str
    result_id: str
    qtd_perguntas: int


def _historico(result_id: str) -> list[dict]:
    return _chat_sessions.setdefault(result_id, [])


@router.post("/{result_id}", response_model=ChatResponse)
async def conversar_sobre_laudo(
    result_id: str,
    body: ChatRequest,
    current_user: TokenData = Depends(get_current_user),
) -> ChatResponse:
    """Chat conversacional sobre laudo — agente foi arquivado em cleanup.

    Retorna confirmação básica de pergunta recebida.
    (AChatAgent foi arquivado por ser prototype sem integração produção)
    """
    laudo: dict[str, Any] | None = resultados_store.get(result_id)
    if laudo is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado.")

    # Autorização: dono do laudo ou admin
    dono = laudo.get("_user_id")
    if current_user.role != "admin" and dono not in (None, current_user.sub):
        raise HTTPException(status_code=404, detail="Laudo não encontrado.")

    historico = _historico(result_id)

    resposta_texto = f"Pergunta registrada: {body.pergunta[:100]}... (Chat agent arquivado)"
    historico.append({"q": body.pergunta, "r": resposta_texto})
    if len(historico) > 20:
        del historico[:-20]

    return ChatResponse(
        resposta=resposta_texto,
        pergunta=body.pergunta,
        result_id=result_id,
        qtd_perguntas=len(historico),
    )


@router.get("/{result_id}/historico")
async def historico_chat(
    result_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    laudo = resultados_store.get(result_id)
    if laudo is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado.")
    dono = laudo.get("_user_id")
    if current_user.role != "admin" and dono not in (None, current_user.sub):
        raise HTTPException(status_code=404, detail="Laudo não encontrado.")
    return {"result_id": result_id, "historico": _historico(result_id)}


@router.delete("/{result_id}/historico", status_code=204)
async def limpar_historico_chat(
    result_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    laudo = resultados_store.get(result_id)
    if laudo is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado.")
    dono = laudo.get("_user_id")
    if current_user.role != "admin" and dono not in (None, current_user.sub):
        raise HTTPException(status_code=404, detail="Laudo não encontrado.")
    _chat_sessions.pop(result_id, None)
    return None
