"""Validadores e formatadores de documentos brasileiros para o nfa_extractor.

Reúne helpers genéricos (limpeza de máscara, formatação BRL) e validação real
de CPF/CNPJ com dígito verificador. Mantém compatibilidade com a API anterior
(clean_document, format_currency, parse_brl_to_float) e expande para fornecer
validação completa.

Implementações de dígito verificador seguem os mesmos algoritmos usados em
pdf_engine/orgaudi/validators.py — evita drift entre os dois módulos.
"""
from __future__ import annotations

import re
from typing import Any


# ─── Limpeza e formatação básicas ────────────────────────────────────────────


def clean_document(doc: Any) -> str:
    """Remove caracteres não numéricos de CPF/CNPJ/qualquer documento."""
    return re.sub(r"\D", "", str(doc or ""))


def format_currency(value: float | int | str) -> str:
    """Formata valor numérico para padrão monetário brasileiro BRL."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 0.0
    return f"R$ {num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_brl_to_float(value: Any) -> float:
    """Converte string monetária (R$ 1.234,56) para float (1234.56).

    Aceita também valores numéricos passados direto — retorna como float.
    Retorna 0.0 em caso de input inválido ou vazio.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    limpo = (
        str(value)
        .replace("R$", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(limpo)
    except ValueError:
        return 0.0


# ─── Validação real (dígito verificador) ─────────────────────────────────────


def validar_cpf(cpf: Any) -> bool:
    """Valida CPF com dígito verificador real (não só formato)."""
    num = clean_document(cpf)
    if len(num) != 11 or num == num[0] * 11:
        return False
    for i in (9, 10):
        s = sum(int(num[j]) * ((i + 1) - j) for j in range(i))
        d = (s * 10) % 11
        if d == 10:
            d = 0
        if d != int(num[i]):
            return False
    return True


def validar_cnpj(cnpj: Any) -> bool:
    """Valida CNPJ com dígito verificador real."""
    num = clean_document(cnpj)
    if len(num) != 14 or num == num[0] * 14:
        return False
    pesos1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    pesos2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

    s1 = sum(int(num[i]) * pesos1[i] for i in range(12))
    d1 = 11 - s1 % 11
    d1 = 0 if d1 >= 10 else d1
    if d1 != int(num[12]):
        return False

    s2 = sum(int(num[i]) * pesos2[i] for i in range(13))
    d2 = 11 - s2 % 11
    d2 = 0 if d2 >= 10 else d2
    return d2 == int(num[13])


def validar_documento(doc: Any) -> bool:
    """Valida CPF (11) ou CNPJ (14) automaticamente pelo comprimento."""
    num = clean_document(doc)
    if len(num) == 11:
        return validar_cpf(num)
    if len(num) == 14:
        return validar_cnpj(num)
    return False


# ─── Máscaras (formatação) ───────────────────────────────────────────────────


def mascara_cpf(cpf: Any) -> str:
    """Aplica máscara XXX.XXX.XXX-XX a um CPF de 11 dígitos."""
    c = clean_document(cpf)
    if len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return str(cpf)


def mascara_cnpj(cnpj: Any) -> str:
    """Aplica máscara XX.XXX.XXX/XXXX-XX a um CNPJ de 14 dígitos."""
    c = clean_document(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return str(cnpj)


def mascara_documento(doc: Any) -> str:
    """Aplica máscara automática (CPF se 11 dígitos, CNPJ se 14)."""
    c = clean_document(doc)
    if len(c) == 11:
        return mascara_cpf(c)
    if len(c) == 14:
        return mascara_cnpj(c)
    return str(doc)


__all__ = [
    "clean_document",
    "format_currency",
    "parse_brl_to_float",
    "validar_cpf",
    "validar_cnpj",
    "validar_documento",
    "mascara_cpf",
    "mascara_cnpj",
    "mascara_documento",
]
