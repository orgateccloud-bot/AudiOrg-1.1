"""
nfa_ai_parser.py — FastAPI
══════════════════════════
Endpoint de serviço para o parser semântico de NFA-e.

Rotas:
  POST /nfa/parse          → extrai NFA-e de 1+ PDFs (sync, até ~50 notas)
  POST /nfa/parse/async    → enfileira extração longa (background task)
  GET  /nfa/parse/status/{task_id}  → polling do job assíncrono
  GET  /nfa/parse/result/{task_id}  → ResultadoExtracaoPDF do job concluído

Headers obrigatórios:
  Authorization: Bearer <JWT>   (mesmo middleware do restante da API)

Query params comuns:
  usar_ia   bool  (default: true)  — ativa fallback Claude
  modelo    str   (default: "claude-haiku-4-5-20251001")
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Auth: reutiliza o mesmo utilitário das outras rotas
try:
    from api.routes.auth import verificar_token  # type: ignore
except ImportError:
    # Fallback para dev sem auth
    async def verificar_token():  # type: ignore
        return {"sub": "dev"}

from nfa_extractor.domain.nfa_parser_ai import NFAParserAI
from nfa_extractor.domain.nfa_ai_schemas import ResultadoExtracaoPDF

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nfa", tags=["NFA Parser IA"])

# ─── Cache em memória dos jobs assíncronos ───────────────────────────────────
# Em produção usar Redis ou o mesmo _DbTasksProxy da API principal
_jobs: dict[str, dict] = {}

# ─── Modelos de resposta extras ──────────────────────────────────────────────

class JobStatus(BaseModel):
    task_id: str
    status:  str          # "processando" | "concluido" | "erro"
    progresso: int = 0    # 0–100
    mensagem:  str = ""


class JobCriado(BaseModel):
    task_id:  str
    mensagem: str
    arquivos: list[str]


# ─── Helper: valida e salva uploads ─────────────────────────────────────────

def _salvar_uploads(files: list[UploadFile], temp_dir: str) -> list[Path]:
    """Salva uploads no diretório temporário. Retorna caminhos válidos."""
    salvos: list[Path] = []
    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext != ".pdf":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Apenas PDF aceito. Arquivo '{f.filename}' ignorado.",
            )
        dest = Path(temp_dir) / f.filename
        content = f.file.read()
        if len(content) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Arquivo '{f.filename}' está vazio ou corrompido.",
            )
        dest.write_bytes(content)
        salvos.append(dest)
    return salvos


# ─── Background task ─────────────────────────────────────────────────────────

def _executar_extracao(
    task_id: str,
    caminhos: list[str],
    usar_ia:  bool,
    modelo:   str,
):
    """Roda a extração em background e grava resultado em _jobs."""
    _jobs[task_id]["status"] = "processando"
    _jobs[task_id]["progresso"] = 10

    try:
        parser = NFAParserAI(
            api_key  = os.getenv("ANTHROPIC_API_KEY"),
            modelo   = modelo,
        )
        _jobs[task_id]["progresso"] = 30

        resultado = parser.extrair_multiplos(caminhos, usar_claude=usar_ia)

        _jobs[task_id].update({
            "status":     "concluido",
            "progresso":  100,
            "resultado":  resultado.model_dump(),
            "mensagem":   (
                f"{resultado.total_extraidas} notas extraídas "
                f"({resultado.por_regex} regex + {resultado.por_claude} claude)"
            ),
        })
        logger.info(
            "Job %s concluído: %d notas | tokens in=%d out=%d",
            task_id, resultado.total_extraidas,
            resultado.tokens_input, resultado.tokens_output,
        )

    except Exception as e:
        logger.error("Job %s falhou: %s", task_id, e, exc_info=True)
        _jobs[task_id].update({
            "status":    "erro",
            "progresso": 100,
            "mensagem":  str(e),
        })
    finally:
        # Limpa arquivos temporários
        for c in caminhos:
            try:
                Path(c).unlink(missing_ok=True)
            except OSError:
                pass


# ─── Rotas ───────────────────────────────────────────────────────────────────

@router.post(
    "/parse",
    response_model=ResultadoExtracaoPDF,
    summary="Extrai NFA-e de PDFs GIEF (síncrono)",
    description=(
        "Recebe 1 ou 2 PDFs GIEF/SEFAZ-GO (ex: REM + DEST) e retorna "
        "as NFA-e estruturadas com Pydantic. Usa regex + Claude fallback. "
        "Para PDFs grandes (>100 notas) prefira /nfa/parse/async."
    ),
)
async def parse_sync(
    files:     Annotated[list[UploadFile], File(description="1–2 PDFs GIEF")],
    usar_ia:   bool = Query(True,  description="Ativar fallback Claude"),
    modelo:    str  = Query(
        "claude-haiku-4-5-20251001",
        description="Modelo Claude para fallback"
    ),
    _token = Depends(verificar_token),
):
    if not files:
        raise HTTPException(400, "Envie ao menos um arquivo PDF.")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            caminhos = _salvar_uploads(files, tmp)
        except HTTPException:
            raise

        if not caminhos:
            raise HTTPException(400, "Nenhum PDF válido recebido.")

        t0 = time.monotonic()
        parser = NFAParserAI(
            api_key = os.getenv("ANTHROPIC_API_KEY"),
            modelo  = modelo,
        )

        try:
            resultado = parser.extrair_multiplos(
                [str(c) for c in caminhos],
                usar_claude=usar_ia,
            )
        except Exception as e:
            logger.error("Extração síncrona falhou: %s", e, exc_info=True)
            raise HTTPException(500, f"Falha na extração: {e}")

        logger.info(
            "parse_sync: %d notas em %.1fs",
            resultado.total_extraidas, time.monotonic() - t0
        )
        return resultado


@router.post(
    "/parse/async",
    response_model=JobCriado,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Extrai NFA-e de PDFs GIEF (assíncrono)",
    description="Enfileira a extração. Poll em GET /nfa/parse/status/{task_id}.",
)
async def parse_async(
    background_tasks: BackgroundTasks,
    files:   Annotated[list[UploadFile], File(description="1–2 PDFs GIEF")],
    usar_ia: bool = Query(True,  description="Ativar fallback Claude"),
    modelo:  str  = Query("claude-haiku-4-5-20251001"),
    _token = Depends(verificar_token),
):
    if not files:
        raise HTTPException(400, "Envie ao menos um arquivo PDF.")

    # Salva em diretório persistente (não tempdir — o job roda depois do request)
    job_dir = Path("data") / "nfa_jobs"
    job_dir.mkdir(parents=True, exist_ok=True)

    task_id  = uuid.uuid4().hex
    task_dir = job_dir / task_id
    task_dir.mkdir()

    try:
        caminhos = _salvar_uploads(files, str(task_dir))
    except HTTPException:
        task_dir.rmdir()
        raise

    nomes = [f.filename for f in files if f.filename]

    _jobs[task_id] = {
        "status":    "aguardando",
        "progresso": 0,
        "mensagem":  f"Job criado com {len(caminhos)} arquivo(s)",
        "resultado": None,
    }

    background_tasks.add_task(
        _executar_extracao,
        task_id,
        [str(c) for c in caminhos],
        usar_ia,
        modelo,
    )

    return JobCriado(
        task_id=task_id,
        mensagem=f"Extração enfileirada ({len(caminhos)} PDFs).",
        arquivos=nomes,
    )


@router.get(
    "/parse/status/{task_id}",
    response_model=JobStatus,
    summary="Consulta status do job assíncrono",
)
async def parse_status(
    task_id: str,
    _token = Depends(verificar_token),
):
    job = _jobs.get(task_id)
    if not job:
        raise HTTPException(404, f"Job '{task_id}' não encontrado.")
    return JobStatus(
        task_id   = task_id,
        status    = job["status"],
        progresso = job.get("progresso", 0),
        mensagem  = job.get("mensagem", ""),
    )


@router.get(
    "/parse/result/{task_id}",
    response_model=ResultadoExtracaoPDF,
    summary="Retorna resultado do job assíncrono concluído",
)
async def parse_result(
    task_id: str,
    _token = Depends(verificar_token),
):
    job = _jobs.get(task_id)
    if not job:
        raise HTTPException(404, f"Job '{task_id}' não encontrado.")
    if job["status"] != "concluido":
        raise HTTPException(
            409,
            f"Job ainda não concluído. Status atual: {job['status']}",
        )
    return job["resultado"]


@router.delete(
    "/parse/result/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove job da memória",
)
async def parse_delete(
    task_id: str,
    _token = Depends(verificar_token),
):
    if task_id not in _jobs:
        raise HTTPException(404, f"Job '{task_id}' não encontrado.")
    _jobs.pop(task_id, None)
    # Limpa diretório do job
    job_dir = Path("data") / "nfa_jobs" / task_id
    if job_dir.exists():
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)
