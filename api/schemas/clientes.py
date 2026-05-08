"""
Schemas Pydantic — domínio Clientes
"""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── helpers de validação ──────────────────────────────────────────────────────

def _apenas_digitos(v: str) -> str:
    return re.sub(r"\D", "", v)

def _validar_cpf(digitos: str) -> bool:
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    # Primeiro dígito verificador
    soma = sum(int(d) * (10 - i) for i, d in enumerate(digitos[:9]))
    r1 = 0 if (soma * 10 % 11) >= 10 else (soma * 10 % 11)
    # Segundo dígito verificador
    soma = sum(int(d) * (11 - i) for i, d in enumerate(digitos[:10]))
    r2 = 0 if (soma * 10 % 11) >= 10 else (soma * 10 % 11)
    return r1 == int(digitos[9]) and r2 == int(digitos[10])

def _validar_cnpj(digitos: str) -> bool:
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(int(d) * p for d, p in zip(digitos[:12], pesos1, strict=False))
    d1 = 0 if (soma1 % 11) < 2 else (11 - soma1 % 11)
    soma2 = sum(int(d) * p for d, p in zip(digitos[:13], pesos2, strict=False))
    d2 = 0 if (soma2 % 11) < 2 else (11 - soma2 % 11)
    return d1 == int(digitos[12]) and d2 == int(digitos[13])


# ── schemas ───────────────────────────────────────────────────────────────────

class ClienteCreate(BaseModel):
    """Payload de criação de um cliente."""

    nome: str = Field(..., min_length=3, max_length=255, description="Nome completo ou razão social")
    cpf_cnpj: str = Field(..., description="CPF (11 dígitos) ou CNPJ (14 dígitos)")

    @field_validator("nome")
    @classmethod
    def nome_strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("cpf_cnpj")
    @classmethod
    def validar_cpf_cnpj(cls, v: str) -> str:
        digitos = _apenas_digitos(v)
        if len(digitos) == 11:
            if not _validar_cpf(digitos):
                raise ValueError("CPF inválido.")
            return digitos
        if len(digitos) == 14:
            if not _validar_cnpj(digitos):
                raise ValueError("CNPJ inválido.")
            return digitos
        raise ValueError("CPF deve ter 11 dígitos e CNPJ 14 dígitos (somente números).")


class ClienteUpdate(BaseModel):
    """Payload de atualização parcial de um cliente."""

    nome: str | None = Field(None, min_length=3, max_length=255)
    cpf_cnpj: str | None = Field(None)

    @field_validator("nome", mode="before")
    @classmethod
    def nome_strip(cls, v):
        return v.strip() if v else v

    @field_validator("cpf_cnpj", mode="before")
    @classmethod
    def validar_cpf_cnpj(cls, v):
        if v is None:
            return v
        digitos = _apenas_digitos(v)
        if len(digitos) == 11:
            if not _validar_cpf(digitos):
                raise ValueError("CPF inválido.")
            return digitos
        if len(digitos) == 14:
            if not _validar_cnpj(digitos):
                raise ValueError("CNPJ inválido.")
            return digitos
        raise ValueError("CPF deve ter 11 dígitos e CNPJ 14 dígitos.")


class ClienteResponse(BaseModel):
    """Serialização de saída de um cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    cpf_cnpj: str
    data_cadastro: datetime | None = None


class ClienteListResponse(BaseModel):
    """Lista paginada de clientes."""

    items: list[ClienteResponse]
    total: int
