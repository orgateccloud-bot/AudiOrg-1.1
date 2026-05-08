import re
from typing import Any

def clean_document(doc: str) -> str:
    """Remove caracteres não numéricos de CPF/CNPJ."""
    return re.sub(r"\D", "", str(doc))

def format_currency(value: float) -> str:
    """Formata valor float para padrão monetário brasileiro BRL."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_brl_to_float(value: Any) -> float:
    """Converte string monetária (R$ 1.234,56) para float (1234.56)."""
    if not value: return 0.0
    if isinstance(value, (int, float)): return float(value)
    
    clean_val = str(value).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(clean_val)
    except ValueError:
        return 0.0
