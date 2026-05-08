"""ORGATEC – Rota do Agente IA (chat protegido por JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth.security import get_current_user, TokenData
from api.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/agente", tags=["Agente"])


@router.post("/chat", response_model=ChatResponse)
async def chat_agente(
    request: ChatRequest,
    _: TokenData = Depends(get_current_user),
):
    from nfa_extractor.infrastructure.ai_client import perguntar

    try:
        res = perguntar(notas=[], context_ia=request.contexto, pergunta=request.pergunta)
        return ChatResponse(response=res)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
