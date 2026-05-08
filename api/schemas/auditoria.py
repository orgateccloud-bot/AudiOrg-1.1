from typing import Literal

from fastapi import UploadFile
from pydantic import BaseModel, field_validator

EXTENSOES_ACEITAS = {".pdf", ".xml"}
MIME_ACEITOS      = {
    "application/pdf",
    "text/xml",
    "application/xml",
    # Browsers às vezes enviam octet-stream
    "application/octet-stream",
}

TAMANHO_MAX_MB  = 50
TAMANHO_MAX     = TAMANHO_MAX_MB * 1024 * 1024  # bytes


class UploadAuditoriaParams(BaseModel):
    """Parâmetros de query para o endpoint de upload de auditoria."""

    modo_relatorio: Literal["simples", "detalhado"] = "simples"
    formato_relatorio: Literal["html", "pdf"] = "html"


class ArquivoUpload(BaseModel):
    """Validação individual de arquivo enviado."""

    nome: str
    tamanho: int
    content_type: str

    @field_validator("nome")
    @classmethod
    def extensao_aceita(cls, v: str) -> str:
        import os
        ext = os.path.splitext(v)[1].lower()
        if ext not in EXTENSOES_ACEITAS:
            raise ValueError(f"Extensão '{ext}' não suportada. Aceito: {sorted(EXTENSOES_ACEITAS)}")
        return v

    @field_validator("tamanho")
    @classmethod
    def tamanho_valido(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Arquivo vazio não é permitido.")
        if v > TAMANHO_MAX:
            raise ValueError(
                f"Arquivo excede o limite de {TAMANHO_MAX_MB} MB "
                f"({v / 1024 / 1024:.1f} MB enviado)."
            )
        return v


def validar_arquivos(files: list[UploadFile]) -> list[str]:
    """Valida lista de UploadFiles e retorna lista de erros (vazia = tudo ok)."""
    import os
    erros: list[str] = []

    if not files:
        return ["Nenhum arquivo enviado."]

    if len(files) > 100:
        return [f"Máximo de 100 arquivos por upload. Recebidos: {len(files)}."]

    for f in files:
        nome = f.filename or ""
        ext  = os.path.splitext(nome)[1].lower()

        if ext not in EXTENSOES_ACEITAS:
            erros.append(f"'{nome}': extensão '{ext}' não suportada (aceito: PDF, XML).")
            continue

        # Tamanho: UploadFile.size pode ser None em alguns middlewares;
        # validamos depois da leitura no endpoint quando necessário.
        if f.size is not None and f.size > TAMANHO_MAX:
            erros.append(
                f"'{nome}': excede {TAMANHO_MAX_MB} MB "
                f"({f.size / 1024 / 1024:.1f} MB)."
            )

    return erros
