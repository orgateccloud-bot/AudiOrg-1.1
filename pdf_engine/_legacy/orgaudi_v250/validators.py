"""
orgaudi.validators
══════════════════
Validações de documentos brasileiros (CPF/CNPJ com dígito verificador real)
e formatadores em pt-BR (moeda, percentual, data, máscaras).

Não tem dependências internas — pode ser importado de qualquer lugar do pacote.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


# ═══════════════════════════════════════════════════════════════════════════════
#  VALIDAÇÕES — CPF e CNPJ com dígito verificador
# ═══════════════════════════════════════════════════════════════════════════════

def validar_cpf(cpf: str) -> bool:
    """Valida CPF com dígito verificador real (não só formato)."""
    cpf_num = re.sub(r"\D", "", cpf)
    if len(cpf_num) != 11 or cpf_num == cpf_num[0] * 11:
        return False
    for i in (9, 10):
        s = sum(int(cpf_num[j]) * ((i + 1) - j) for j in range(i))
        d = (s * 10) % 11
        if d == 10:
            d = 0
        if d != int(cpf_num[i]):
            return False
    return True


def validar_cnpj(cnpj: str) -> bool:
    """Valida CNPJ com dígito verificador."""
    c = re.sub(r"\D", "", cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    # Pesos para 1º DV (12 dígitos) e 2º DV (13 dígitos)
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(c[i]) * pesos1[i] for i in range(12))
    d1 = 11 - s % 11
    d1 = 0 if d1 >= 10 else d1
    if d1 != int(c[12]):
        return False
    s = sum(int(c[i]) * pesos2[i] for i in range(13))
    d2 = 11 - s % 11
    d2 = 0 if d2 >= 10 else d2
    return d2 == int(c[13])


# ═══════════════════════════════════════════════════════════════════════════════
#  FORMATADORES pt-BR
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_brl(valor: Decimal | float | int, sinal: bool = True) -> str:
    """Formata valor em padrão brasileiro: R$ 1.234.567,89."""
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    valor = valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}" if sinal else s


def fmt_brl_compact(valor: Decimal | float | int) -> str:
    """
    Formato BR completo (sem K/M abreviado) — modelo da moeda real brasileira.
    Usado nos KPIs da capa: R$ 3.827.533,91, R$ 730.076,89, etc.
    """
    return fmt_brl(valor)


def fmt_pct(valor: float, casas: int = 2) -> str:
    """Formata percentual em pt-BR: 12,77%."""
    return f"{valor:.{casas}f}%".replace(".", ",")


def fmt_data(d: date | str) -> str:
    """Formata data como DD/MM/YYYY."""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return d
    return d.strftime("%d/%m/%Y")


def mascara_cpf(cpf: str) -> str:
    """Aplica máscara XXX.XXX.XXX-XX a um CPF de 11 dígitos."""
    c = re.sub(r"\D", "", cpf)
    if len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    return cpf


def mascara_cnpj(cnpj: str) -> str:
    """Aplica máscara XX.XXX.XXX/XXXX-XX a um CNPJ."""
    c = re.sub(r"\D", "", cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj
