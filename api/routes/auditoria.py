import logging
import re
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from api.services.auditoria import (
    gerar_pdf_nfae,
    processar_lote_auditoria,
    processar_nfae,
    resultados_store,
    tasks_status,
)

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])
_logger = logging.getLogger("orgaudi")

_RE_DIGITS = re.compile(r"\D")


def _validar_cpf(cpf: str) -> bool:
    d = _RE_DIGITS.sub("", cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for i in range(2):
        total = sum(int(d[j]) * (10 + i - j) for j in range(9 + i))
        resto = (total * 10) % 11
        if (0 if resto == 10 else resto) != int(d[9 + i]):
            return False
    return True


def _validar_cnpj(cnpj: str) -> bool:
    d = _RE_DIGITS.sub("", cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for i, pesos in enumerate([pesos1, [6] + pesos1]):
        total = sum(int(d[j]) * pesos[j] for j in range(len(pesos)))
        resto = total % 11
        if (0 if resto < 2 else 11 - resto) != int(d[12 + i]):
            return False
    return True


# ── Schemas ──────────────────────────────────────────────────────────────────

class NotaInput(BaseModel):
    numero: str = Field(..., min_length=1, max_length=20)
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    natureza: str = Field(..., min_length=1, max_length=100)
    valor_total: float = Field(..., ge=0, le=1_000_000_000)
    remetente_cpf: str = Field(default="", max_length=18)
    remetente_nome: str = Field(default="", max_length=200)
    destinatario_cpf: str = Field(default="", max_length=18)
    destinatario_nome: str = Field(default="", max_length=200)
    cfop: str = Field(default="", max_length=5)
    cabecas: int = Field(default=0, ge=0, le=100_000)
    municipio: str = Field(default="", max_length=100)
    ie_remetente: str = Field(default="", max_length=20)
    posicao: str = Field(default="REMETENTE", max_length=20)
    tipo_doc: str = Field(default="nfa-e", max_length=10)
    atividade: str = Field(default="", max_length=100)


class AuditoriaCompletaRequest(BaseModel):
    contribuinte_cpf: str = Field(..., min_length=11, max_length=18)
    contribuinte_nome: str = Field(..., min_length=2, max_length=200)
    notas: List[NotaInput] = Field(..., min_length=1, max_length=5000)
    is_pj: bool = False
    is_segurado_especial: bool = False

    @field_validator("contribuinte_cpf")
    @classmethod
    def validar_documento(cls, v: str) -> str:
        digits = _RE_DIGITS.sub("", v)
        if len(digits) == 11:
            if not _validar_cpf(v):
                raise ValueError("CPF inválido — dígitos verificadores incorretos")
        elif len(digits) == 14:
            if not _validar_cnpj(v):
                raise ValueError("CNPJ inválido — dígitos verificadores incorretos")
        else:
            raise ValueError("Documento deve ser CPF (11 dígitos) ou CNPJ (14 dígitos)")
        return v


# ── Endpoints legados (PDF upload → background task) ─────────────────────────

@router.post("/upload/{client_id}")
async def iniciar_auditoria(
    client_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    task_id = str(uuid.uuid4())
    tasks_status[task_id] = {"status": "iniciado", "progress": 0}
    background_tasks.add_task(processar_lote_auditoria, task_id, files, "Cliente Mock", "000.000.000-00")
    return {"task_id": task_id, "message": "Auditoria iniciada com sucesso."}


@router.get("/status/{task_id}")
async def consultar_status(task_id: str):
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return tasks_status[task_id]


# ── Pipeline HORIZON-BLUE ─────────────────────────────────────────────────────

@router.post("/nfae")
async def auditoria_nfae(request: AuditoriaCompletaRequest):
    """Pipeline HORIZON-BLUE: RE-1 → XGBoost → LSTM → Precalc → S1–S7."""
    try:
        resultado = await processar_nfae(request)
        result_id = str(uuid.uuid4())
        resultados_store[result_id] = resultado
        resultado["result_id"] = result_id
        return resultado
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Pipeline timeout — tente novamente")
    except Exception:
        _logger.error("erro_pipeline_nfae", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno no pipeline de auditoria")


@router.get("/resultado/{result_id}")
async def obter_resultado(result_id: str):
    if result_id not in resultados_store:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    return resultados_store[result_id]


@router.get("/relatorio/{result_id}/pdf")
async def download_relatorio_pdf(result_id: str):
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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        _logger.error("erro_relatorio_nfae", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar relatório")
