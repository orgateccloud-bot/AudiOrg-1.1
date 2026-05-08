"""ORGATEC – Rotas de Métricas e Observabilidade (admin-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth.security import get_current_user, TokenData

router = APIRouter(prefix="/metrics", tags=["Observabilidade"])


@router.get("/ai")
def ai_metrics(current_user: TokenData = Depends(get_current_user)):
    """Retorna métricas do circuit breaker dos provedores de IA."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
    from nfa_extractor.infrastructure.ai_client import get_ai_metrics
    return get_ai_metrics()
