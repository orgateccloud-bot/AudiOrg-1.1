"""Endpoint de batch — auditoria de múltiplos clientes com ranking de risco.

POST /batch/ranking → recebe N result_ids já processados e devolve sumário
                      executivo + classificação CRITICO/ATENCAO/OK.

Apenas role=admin pode consumir (operação sobre múltiplos clientes).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth.security import TokenData, get_current_user
from api.services.auditoria import resultados_store

router = APIRouter(prefix="/batch", tags=["Batch"])


class RankingRequest(BaseModel):
    result_ids: List[str] = Field(..., min_length=1, max_length=200)


def _exigir_admin(user: TokenData) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem rodar ranking em lote.",
        )


@router.post("/ranking")
async def ranking_de_risco(
    body: RankingRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Agrega laudos já emitidos — ranking agent arquivado em cleanup.

    Retorna sumário básico dos laudos processados.
    (ARankingAgent foi arquivado por ser prototype sem integração produção)
    """
    _exigir_admin(current_user)

    laudos = []
    nao_encontrados = []
    for rid in body.result_ids:
        laudo = resultados_store.get(rid)
        if laudo is None:
            nao_encontrados.append(rid)
            continue
        laudos.append(laudo)

    if not laudos:
        raise HTTPException(
            status_code=404,
            detail={"erro": "nenhum result_id válido", "nao_encontrados": nao_encontrados},
        )

    return {
        "sumario": {
            "qtd_processados": len(laudos),
            "resultado_ids": body.result_ids,
        },
        "nao_encontrados": nao_encontrados,
    }
