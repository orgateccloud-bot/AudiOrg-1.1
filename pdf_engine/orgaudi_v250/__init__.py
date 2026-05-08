"""
orgaudi_v250 — OrgAudi v2.5.0
════════════════════════════════
Novo motor de PDF baseado em HTML/CSS + Chrome headless.

Design specs:
  Formato     : A4 · 210 × 297 mm
  Engine      : Chrome headless (--print-to-pdf)
  Tipografia  : Manrope · JetBrains Mono
  Cor primária: #0B3B5C   Acento: #14B8A6
  Capa        : Editorial com gradiente
  Severidade  : Crítico · Alto · Médio · Atenção · Conforme
  Conformidade: NBC TA · CPC 47 / 25 / 27

Uso:
    from pdf_engine.orgaudi_v250 import gerar_laudo_v250
    gerar_laudo_v250(notas, "NOME", "CPF11", Path("saida.pdf"))
"""
from .report_builder import gerar_laudo_v250

__all__ = ["gerar_laudo_v250"]
__version__ = "2.5.0"
