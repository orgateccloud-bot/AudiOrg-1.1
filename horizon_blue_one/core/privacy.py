"""Protocolo @Delta — Anonimização de PII antes de enviar dados para LLMs.

Conformidade LGPD Art. 37: toda operação de anonimização/des-anonimização
gera entrada de log estruturado contendo requisicao_id, agente e hash SHA-256
dos dados em claro (nunca o dado plaintext).

Uso recomendado: BaseAgent._call_llm() chama anonymize_payload() antes de
qualquer chamada a call_model(). Agentes não devem chamar call_model() direto.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Any

import structlog

# ── Regex de identificadores ─────────────────────────────────────────────────

RE_CPF   = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
RE_CNPJ  = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Campos cujo valor textual é nome próprio (não passa por regex)
_CAMPOS_SENSIVEIS = frozenset({
    "nome", "razao_social", "proprietario",
    "remetente_nome", "destinatario_nome",
    "nome_contribuinte", "nome_responsavel",
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
) -> None:
    """Loga a operação @Delta sem nunca registrar o valor original em claro."""
    _privacy_logger.info(
        "delta_operacao",
        operacao=operacao,
        requisicao_id=requisicao_id,
        agente=agente,
        qtd_cpf=len(cpfs),
        qtd_cnpj=len(cnpjs),
        qtd_email=len(emails),
        qtd_nome=len(nomes),
        # Hashes permitem auditoria posterior (titular pede: viu meu CPF?)
        hashes_cpf=[_hash_curto(v) for v in cpfs],
        hashes_cnpj=[_hash_curto(v) for v in cnpjs],
        hashes_email=[_hash_curto(v) for v in emails],
        hashes_nome=[_hash_curto(v) for v in nomes],
    )


# ── API pública ──────────────────────────────────────────────────────────────


def anonymize_pii(text: str) -> tuple[str, list[str], list[str], list[str]]:
    """Substitui CPF/CNPJ/email no texto por placeholders.

    Retorna (texto_anonimizado, cpfs_encontrados, cnpjs_encontrados, emails).
    Os valores em claro são devolvidos APENAS para que o caller possa logar
    hashes — nunca devem ser persistidos pelo agente.
    """
    if not isinstance(text, str):
        return text, [], [], []
    cpfs   = RE_CPF.findall(text)
    cnpjs  = RE_CNPJ.findall(text)
    emails = RE_EMAIL.findall(text)
    texto  = RE_CPF.sub("[CPF_PROTEGIDO]", text)
    texto  = RE_CNPJ.sub("[CNPJ_PROTEGIDO]", texto)
    texto  = RE_EMAIL.sub("[EMAIL_PROTEGIDO]", texto)
    return texto, cpfs, cnpjs, emails


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
    cpfs_vistos: list[str]   = []
    cnpjs_vistos: list[str]  = []
    emails_vistos: list[str] = []
    nomes_vistos: list[str]  = []

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
            texto, cpfs, cnpjs, emails = anonymize_pii(node)
            cpfs_vistos.extend(cpfs)
            cnpjs_vistos.extend(cnpjs)
            emails_vistos.extend(emails)
            return texto
        return node

    resultado = _walk(payload)

    if cpfs_vistos or cnpjs_vistos or emails_vistos or nomes_vistos:
        _registrar_operacao(
            "anonimizar",
            requisicao_id,
            agente,
            cpfs_vistos,
            cnpjs_vistos,
            emails_vistos,
            nomes_vistos,
        )

    return resultado


def get_privacy_log_path() -> Path | None:
    """Caminho configurável do log de privacidade (LGPD_DELTA_LOG env)."""
    valor = os.getenv("LGPD_DELTA_LOG", "").strip()
    return Path(valor) if valor else None
