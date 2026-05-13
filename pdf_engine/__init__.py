"""
pdf_engine — Motor de geração de PDFs do OrgAudi
═════════════════════════════════════════════════
Pacote consolidado (v2.5.0) com toda a geração de laudos.

API pública:
    from pdf_engine import gerar_laudo_v250          # padrão (HTML/Chrome)
    from pdf_engine import gerar_laudo               # alias
    from pdf_engine import LaudoOrgAudi              # alternativa (ReportLab)
    from pdf_engine import gerar_laudo_orgaudi      # adapter nfa-repo

Estrutura:
    pdf_engine/
      ├─ orgaudi/        ⭐ motor unificado (v2.5 + v2.4)
      ├─ excel_export.py    exportador Excel (auxiliar)
      └─ _legacy/        versões antigas arquivadas (v240, v250, v4, ir_report, pdf_report)
"""
from .orgaudi import (
    gerar_laudo,
    gerar_laudo_v250,
    LaudoOrgAudi,
    gerar_laudo_orgaudi,
    Achado,
    CategoriaContabil,
    Contribuinte,
    NaturezaNota,
    NotaFiscal,
    Periodo,
    Severidade,
)

__all__ = [
    "gerar_laudo",
    "gerar_laudo_v250",
    "LaudoOrgAudi",
    "gerar_laudo_orgaudi",
    "Achado",
    "CategoriaContabil",
    "Contribuinte",
    "NaturezaNota",
    "NotaFiscal",
    "Periodo",
    "Severidade",
]

__version__ = "2.5.0"
