"""
orgaudi_v240 — Geração de laudos de auditoria
════════════════════════════════════════════════
Sub-pacote responsável pela geração do PDF com análise forense.
"""

from .domain import (
    Achado,
    CategoriaContabil,
    Contribuinte,
    NaturezaNota,
    NotaFiscal,
    Periodo,
    Severidade,
)

__all__ = [
    "Achado",
    "CategoriaContabil",
    "Contribuinte",
    "NaturezaNota",
    "NotaFiscal",
    "Periodo",
    "Severidade",
]
