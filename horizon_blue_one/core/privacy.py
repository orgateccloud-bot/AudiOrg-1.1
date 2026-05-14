"""Protocolo @Delta — Anonimização de PII antes de enviar dados para LLMs.

Conformidade LGPD Art. 37: toda operação de anonimização/des-anonimização
gera entrada de log estruturado contendo requisicao_id, agente e hash SHA-256
dos dados em claro (nunca o dado plaintext).

Uso recomendado: BaseAgent._call_llm() chama anonymize_payload() antes de
qualquer chamada a call_model(). Agentes não devem chamar call_model() direto.

Identificadores detectados:
- CPF (com/sem máscara)
- CNPJ (com/sem máscara)
- Email
- Telefone brasileiro (fixo/celular, com/sem DDI/DDD)
- Placa de veículo Mercosul (AAA-0000 e AAA-0A00)
- CEP brasileiro (00000-000)
- Campos textuais "sensíveis" (nome, razão social, etc.) por nome de chave
"""
from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

import structlog

# ── Regex de identificadores ─────────────────────────────────────────────────

RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
RE_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Telefone BR — captura formatos como (62) 99999-9999, 62999999999, +55 62 99999-9999
RE_TELEFONE = re.compile(
    r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-\s]?\d{4}\b"
)

# Placa Mercosul (AAA0A00) e antiga (AAA-0000)
RE_PLACA = re.compile(r"\b[A-Z]{3}[-\s]?\d[A-Z0-9]\d{2}\b")

# CEP BR (00000-000 ou 00000000)
RE_CEP = re.compile(r"\b\d{5}-?\d{3}\b")

# Campos cujo valor textual é nome próprio (não passa por regex)
_CAMPOS_SENSIVEIS = frozenset({
    "nome", "razao_social", "proprietario",
    "remetente_nome", "destinatario_nome",
    "nome_contribuinte", "nome_responsavel",
    "endereco", "logradouro", "complemento",
})

# ── Log dedicado de privacidade (append-only) ────────────────────────────────

_privacy_logger = structlog.get_logger("privacy")


def _hash_curto(valor: str) -> str:
    """SHA-256 truncado em 16 chars — suficiente para rastreio sem expor PII."""
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]


def _registrar_operacao(
    operacao: str,
    requisicao_id: str,
    agente: str,
    cpfs: list[str],
    cnpjs: list[str],
    emails: list[str],
    nomes: list[str],
    telefones: list[str] | None = None,
    placas: list[str] | None = None,
    ceps: list[str] | None = None,
) -> None:
    """Loga a operação @Delta sem nunca registrar o valor original em claro."""
    telefones = telefones or []
    placas = placas or []
    ceps = ceps or []
    _privacy_logger.info(
        "delta_operacao",
        operacao=operacao,
        requisicao_id=requisicao_id,
        agente=agente,
        qtd_cpf=len(cpfs),
        qtd_cnpj=len(cnpjs),
        qtd_email=len(emails),
        qtd_nome=len(nomes),
        qtd_telefone=len(telefones),
        qtd_placa=len(placas),
        qtd_cep=len(ceps),
        hashes_cpf=[_hash_curto(v) for v in cpfs],
        hashes_cnpj=[_hash_curto(v) for v in cnpjs],
        hashes_email=[_hash_curto(v) for v in emails],
        hashes_nome=[_hash_curto(v) for v in nomes],
        hashes_telefone=[_hash_curto(v) for v in telefones],
        hashes_placa=[_hash_curto(v) for v in placas],
        hashes_cep=[_hash_curto(v) for v in ceps],
    )


# ── API pública ──────────────────────────────────────────────────────────────


def anonymize_pii(text: str) -> tuple[str, dict[str, list[str]]]:
    """Substitui CPF/CNPJ/email/telefone/placa/CEP no texto por placeholders.

    Retorna (texto_anonimizado, identificadores_encontrados).
    O dict de identificadores tem chaves: cpfs, cnpjs, emails, telefones, placas, ceps.
    Os valores em claro são devolvidos APENAS para que o caller possa logar
    hashes — nunca devem ser persistidos pelo agente.
    """
    if not isinstance(text, str):
        return text, {"cpfs": [], "cnpjs": [], "emails": [], "telefones": [], "placas": [], "ceps": []}

    cpfs = RE_CPF.findall(text)
    cnpjs = RE_CNPJ.findall(text)
    emails = RE_EMAIL.findall(text)

    # CPF/CNPJ primeiro (têm precedência sobre telefone — evita confusão de dígitos)
    texto = RE_CPF.sub("[CPF_PROTEGIDO]", text)
    texto = RE_CNPJ.sub("[CNPJ_PROTEGIDO]", texto)
    texto = RE_EMAIL.sub("[EMAIL_PROTEGIDO]", texto)

    telefones = RE_TELEFONE.findall(texto)
    texto = RE_TELEFONE.sub("[TELEFONE_PROTEGIDO]", texto)

    placas = RE_PLACA.findall(texto)
    texto = RE_PLACA.sub("[PLACA_PROTEGIDA]", texto)

    ceps = RE_CEP.findall(texto)
    texto = RE_CEP.sub("[CEP_PROTEGIDO]", texto)

    return texto, {
        "cpfs": cpfs,
        "cnpjs": cnpjs,
        "emails": emails,
        "telefones": telefones,
        "placas": placas,
        "ceps": ceps,
    }


def anonymize_payload(
    payload: Any,
    *,
    requisicao_id: str | None = None,
    agente: str = "desconhecido",
) -> dict | list | Any:
    """Anonimiza recursivamente um payload destinado a um LLM.

    Acumula CPFs/CNPJs/nomes vistos durante a varredura e emite UM log
    estruturado por chamada (não por valor encontrado, para não inflar log).
    """
    requisicao_id = requisicao_id or str(uuid.uuid4())
    cpfs_vistos: list[str] = []
    cnpjs_vistos: list[str] = []
    emails_vistos: list[str] = []
    nomes_vistos: list[str] = []
    telefones_vistos: list[str] = []
    placas_vistas: list[str] = []
    ceps_vistos: list[str] = []

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            saida: dict = {}
            for k, v in node.items():
                if k in _CAMPOS_SENSIVEIS and isinstance(v, str) and v:
                    nomes_vistos.append(v)
                    saida[k] = f"[NOME_REDACTED_{len(v)}]"
                else:
                    saida[k] = _walk(v)
            return saida
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if isinstance(node, str):
            texto, achados = anonymize_pii(node)
            cpfs_vistos.extend(achados["cpfs"])
            cnpjs_vistos.extend(achados["cnpjs"])
            emails_vistos.extend(achados["emails"])
            telefones_vistos.extend(achados["telefones"])
            placas_vistas.extend(achados["placas"])
            ceps_vistos.extend(achados["ceps"])
            return texto
        return node

    saida = _walk(payload)
    _registrar_operacao(
        "anonymize",
        requisicao_id,
        agente,
        cpfs_vistos,
        cnpjs_vistos,
        emails_vistos,
        nomes_vistos,
        telefones_vistos,
        placas_vistas,
        ceps_vistos,
    )
    return saida


__all__ = [
    "RE_CPF",
    "RE_CNPJ",
    "RE_EMAIL",
    "RE_TELEFONE",
    "RE_PLACA",
    "RE_CEP",
    "anonymize_pii",
    "anonymize_payload",
]
