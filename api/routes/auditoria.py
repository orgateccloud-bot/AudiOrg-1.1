import uuid
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import List, Optional

from api.services.auditoria import (
    processar_lote_auditoria,
    processar_nfae,
    gerar_pdf_nfae,
    tasks_status,
    resultados_store,
)

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


# ── Schemas para o endpoint /nfae (HORIZON-BLUE integration) ─────────────────

class NotaInput(BaseModel):
    numero: str
    data: str                          # YYYY-MM-DD
    natureza: str                      # VENDA | COMPRA | TRÂNSITO | DEVOLUÇÃO
    valor_total: float = Field(..., ge=0)
    remetente_cpf: str = ""
    remetente_nome: str = ""
    destinatario_cpf: str = ""
    destinatario_nome: str = ""
    cfop: str = ""
    cabecas: int = Field(default=0, ge=0)
    municipio: str = ""
    ie_remetente: str = ""
    posicao: str = "REMETENTE"         # REMETENTE | DESTINATÁRIO
    tipo_doc: str = "nfa-e"
    atividade: str = ""


class AuditoriaCompletaRequest(BaseModel):
    contribuinte_cpf: str
    contribuinte_nome: str
    notas: List[NotaInput] = Field(..., min_length=1)
    is_pj: bool = False
    is_segurado_especial: bool = False


# ── Endpoints legados (PDF upload → background task) ─────────────────────────

@router.post("/upload/{client_id}")
async def iniciar_auditoria(
    client_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    task_id = str(uuid.uuid4())
    tasks_status[task_id] = {"status": "iniciado", "progress": 0}

    client_name = "Cliente Mock"
    client_cpf  = "000.000.000-00"

    background_tasks.add_task(processar_lote_auditoria, task_id, files, client_name, client_cpf)
    return {"task_id": task_id, "message": "Auditoria iniciada com sucesso."}


@router.get("/status/{task_id}")
async def consultar_status(task_id: str):
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return tasks_status[task_id]


# ── Pipeline HORIZON-BLUE ─────────────────────────────────────────────────────

@router.post("/nfae")
async def auditoria_nfae(request: AuditoriaCompletaRequest):
    """Pipeline HORIZON-BLUE: RE-1 → XGBoost → F1-F6 → A-07 → A-08."""
    try:
        resultado = await processar_nfae(request)
        result_id = str(uuid.uuid4())
        resultados_store[result_id] = resultado
        resultado["result_id"] = result_id
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no pipeline: {str(e)}")


@router.get("/resultado/{result_id}")
async def obter_resultado(result_id: str):
    """Retorna resultado armazenado de uma auditoria NFA-e."""
    if result_id not in resultados_store:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    return resultados_store[result_id]


@router.get("/relatorio/{result_id}/pdf")
async def download_relatorio_pdf(result_id: str):
    """Gera e devolve relatório PDF de uma auditoria NFA-e armazenada."""
    if result_id not in resultados_store:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    pdf_bytes = gerar_pdf_nfae(resultados_store[result_id])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=relatorio_nfae_{result_id[:8]}.pdf"},
    )


@router.post("/nfae/relatorio")
async def auditoria_e_relatorio(request: AuditoriaCompletaRequest):
    """Executa pipeline completo e devolve o PDF diretamente."""
    try:
        resultado = await processar_nfae(request)
        pdf_bytes = gerar_pdf_nfae(resultado)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=relatorio_nfae.pdf"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar relatório: {str(e)}")
