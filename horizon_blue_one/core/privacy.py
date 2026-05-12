"""Protocolo @Delta — Anonimização de PII antes de enviar dados para LLMs."""
from __future__ import annotations

import re
from typing import Any

RE_CPF  = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
RE_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")

_CAMPOS_SENSIVEIS = {
    "nome", "razao_social", "proprietario",
    "remetente_nome", "destinatario_nome",
}


def anonymize_pii(text: Any) -> Any:
    # Guarda defensiva: pode receber None/int em estruturas heterogêneas (ledger,
    # payloads parciais). Retorna a entrada inalterada para não quebrar o caller.
    if not isinstance(text, str):
        return text
    text = RE_CPF.sub("[CPF_PROTEGIDO]", text)
    return RE_CNPJ.sub("[CNPJ_PROTEGIDO]", text)


def anonymize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    novo: dict[str, Any] = {}
    for k, v in payload.items():
        if k in _CAMPOS_SENSIVEIS and isinstance(v, str):
            novo[k] = f"[NOME_REDACTED_{len(v)}]"
        elif isinstance(v, dict):
            novo[k] = anonymize_payload(v)
        elif isinstance(v, list):
            novo[k] = [anonymize_payload(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, str):
            novo[k] = anonymize_pii(v)
        else:
            novo[k] = v
    return novo
