"""Rotas de auditoria — upload PDF, pipeline NFA-e e download de laudo.

Hardening v1.2:
- Todos os endpoints exigem autenticação JWT (Depends(get_current_user)).
- client_id é validado contra a tabela Cliente; usuários não-admin só acessam
  recursos do(s) cliente(s) ao qual estão associados (futuro: tabela user_clientes).
- Upload de PDF passa por _validar_pdf() com path traversal, magic bytes,
  content-type e limites de tamanho (commit 330983c).
"""
import os
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth.security import TokenData, get_current_user
from api.dependencies import get_db
from api.services.auditoria import (
    gerar_pdf_nfae,
    processar_lote_auditoria,
    processar_nfae,
    resultados_store,
    tasks_status,
)
from nfa_extractor.infrastructure.database_v2 import Cliente

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


# ── Limites de upload (configuráveis via env) ────────────────────────────────

UPLOAD_MAX_BYTES      = int(os.getenv("UPLOAD_MAX_BYTES",      str(10 * 1024 * 1024)))
UPLOAD_LOTE_MAX_BYTES = int(os.getenv("UPLOAD_LOTE_MAX_BYTES", str(50 * 1024 * 1024)))
UPLOAD_MAX_FILES      = int(os.getenv("UPLOAD_MAX_FILES",      "20"))

_MIME_PDF_VALIDOS = {"application/pdf", "application/x-pdf", "application/acrobat"}
_PDF_MAGIC = b"%PDF-"


# ── Autorização sobre cliente ────────────────────────────────────────────────


def _autorizar_cliente(db: Session, client_id: int, user: TokenData) -> Cliente:
    """Verifica que o cliente existe e que o usuário tem acesso a ele.

    Política atual:
    - role=admin tem acesso a qualquer cliente
    - outros roles só acessam clientes aos quais estão explicitamente associados
      (tabela user_clientes — TODO: implementar quando multi-tenant for ativado)

    Por enquanto, qualquer usuário autenticado pode acessar qualquer cliente
    existente, mas o client_id precisa de fato existir no banco.
    """
    cliente = db.query(Cliente).filter(Cliente.id == client_id).first()
    if cliente is None:
        raise HTTPException(status_code=404, detail=f"Cliente {client_id} não encontrado.")
    # Hook para multi-tenancy futura — admin sempre passa, demais ainda passam
    # mas deixamos o ponto pronto para inserir verificação user_clientes.
    if user.role != "admin":
        # TODO: db.query(UserCliente).filter_by(user_id=user.sub, cliente_id=client_id).first()
        pass
    return cliente


# ── Validação de PDF ─────────────────────────────────────────────────────────


async def _validar_pdf(arquivo: UploadFile) -> bytes:
    """Valida um único upload de PDF e retorna o conteúdo lido.

    - Nome não pode estar vazio nem conter separadores de path
    - content-type precisa ser de PDF (ou ausente, validado por magic bytes)
    - Tamanho não pode exceder UPLOAD_MAX_BYTES
    - Magic bytes precisa ser %PDF- (impede imagem renomeada .pdf)
    """
    nome = (arquivo.filename or "").strip()
    if not nome or "/" in nome or "\\" in nome or ".." in nome:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    if not nome.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail=f"Apenas arquivos .pdf são aceitos (recebido: {nome}).")

    ctype = (arquivo.content_type or "").lower()
    if ctype and ctype not in _MIME_PDF_VALIDOS:
        raise HTTPException(status_code=415, detail=f"content-type não suportado: {ctype}.")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail=f"Arquivo vazio: {nome}.")
    if len(conteudo) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo '{nome}' excede o limite de {UPLOAD_MAX_BYTES // (1024 * 1024)} MB.",
        )
    if not conteudo.startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=415,
            detail=f"Conteúdo de '{nome}' não é um PDF válido (magic-bytes ausente).",
        )

    await arquivo.seek(0)
    return conteudo


# ── Schemas para o endpoint /nfae (HORIZON-BLUE) ─────────────────────────────


class NotaInput(BaseModel):
    numero: str
    data: str
    natureza: str
    valor_total: float = Field(..., ge=0)
    remetente_cpf: str = ""
    remetente_nome: str = ""
    destinatario_cpf: str = ""
    destinatario_nome: str = ""
    cfop: str = ""
    cabecas: int = Field(default=0, ge=0)
    municipio: str = ""
    ie_remetente: str = ""
    posicao: str = "REMETENTE"
    tipo_doc: str = "nfa-e"
    atividade: str = ""


class AuditoriaCompletaRequest(BaseModel):
    contribuinte_cpf: str
    contribuinte_nome: str
    notas: List[NotaInput] = Field(..., min_length=1)
    is_pj: bool = False
    is_segurado_especial: bool = False


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/upload/{client_id}")
async def iniciar_auditoria(
    client_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    cliente = _autorizar_cliente(db, client_id, current_user)

    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    if len(files) > UPLOAD_MAX_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Lote excede o limite de {UPLOAD_MAX_FILES} arquivos.",
        )

    total_bytes = 0
    for arquivo in files:
        conteudo = await _validar_pdf(arquivo)
        total_bytes += len(conteudo)
        if total_bytes > UPLOAD_LOTE_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Lote excede o limite de {UPLOAD_LOTE_MAX_BYTES // (1024 * 1024)} MB.",
            )

    task_id = str(uuid.uuid4())
    tasks_status[task_id] = {"status": "iniciado", "progress": 0, "user_id": current_user.sub}

    background_tasks.add_task(
        processar_lote_auditoria, task_id, files, cliente.nome, cliente.cpf_cnpj,
    )
    return {"task_id": task_id, "message": "Auditoria iniciada com sucesso."}


@router.get("/status/{task_id}")
async def consultar_status(
    task_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    info = tasks_status.get(task_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    # Usuário só vê tasks que ele mesmo iniciou (admin vê tudo)
    dono = info.get("user_id")
    if current_user.role != "admin" and dono is not None and dono != current_user.sub:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return info


@router.post("/nfae")
async def auditoria_nfae(
    request: AuditoriaCompletaRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Pipeline HORIZON-BLUE: RE-1 → XGBoost → F1-F6 → A-07 → A-08."""
    try:
        resultado = await processar_nfae(request)
        result_id = str(uuid.uuid4())
        resultado["result_id"] = result_id
        resultado["_user_id"] = current_user.sub
        resultados_store[result_id] = resultado
        return resultado
    except Exception as exc:
        # Log completo no servidor, mensagem genérica ao cliente
        import logging
        logging.getLogger("orgaudi").exception("Erro no pipeline NFA-e", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro interno no pipeline de auditoria.")


@router.get("/resultado/{result_id}")
async def obter_resultado(
    result_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    res = resultados_store.get(result_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    if current_user.role != "admin" and res.get("_user_id") not in (None, current_user.sub):
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    return {k: v for k, v in res.items() if not k.startswith("_")}


@router.get("/relatorio/{result_id}/pdf")
async def download_relatorio_pdf(
    result_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    res = resultados_store.get(result_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    if current_user.role != "admin" and res.get("_user_id") not in (None, current_user.sub):
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    pdf_bytes = gerar_pdf_nfae(res)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=relatorio_nfae_{result_id[:8]}.pdf"},
    )


@router.post("/nfae/relatorio")
async def auditoria_e_relatorio(
    request: AuditoriaCompletaRequest,
    current_user: TokenData = Depends(get_current_user),
):
    try:
        resultado = await processar_nfae(request)
        pdf_bytes = gerar_pdf_nfae(resultado)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=relatorio_nfae.pdf"},
        )
    except Exception as exc:
        import logging
        logging.getLogger("orgaudi").exception("Erro ao gerar relatório", exc_info=exc)
        raise HTTPException(status_code=500, detail="Erro interno ao gerar relatório.")
