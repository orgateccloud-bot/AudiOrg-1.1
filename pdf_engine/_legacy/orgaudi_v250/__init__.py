"""
orgaudi — Motor unificado de geração de laudos OrgAudi
═══════════════════════════════════════════════════════
Pasta consolidada (ex-v240 + v250 + v4/adapter) com toda a geração de PDFs.

Estrutura interna:
  ─ Núcleo compartilhado (dados + lógica fiscal):
      domain.py            — dataclasses + enums (Contribuinte, NotaFiscal, Achado…)
      validators.py        — CPF/CNPJ + formatadores pt-BR (fmt_brl, fmt_data…)
      data_processing.py   — motor fiscal F1-F6, testes T-01/02/04/07, planilhas
      catalog.py           — 18 tipologias × 5 eixos

  ─ Motor v2.5 (HTML/Chrome — PADRÃO EM PRODUÇÃO):
      report_builder.py    — orquestrador (entrada: gerar_laudo_v250)
      template_builder.py  — HTML self-contained (Manrope + JetBrains Mono)
      renderer.py          — Chrome headless → PDF

  ─ Motor v2.4 (ReportLab — alternativa modular):
      report_builder_rl.py — orquestrador (entrada: LaudoOrgAudi)
      pages.py             — 8 páginas do laudo
      handlers.py          — header/footer canvas
      styles.py            — paleta + componentes ReportLab

  ─ Adapter:
      adapter.py           — converte nfa-repo.NFA → NotaFiscal

  ─ CLI:
      cli.py + __main__.py — `python -m pdf_engine.orgaudi`

API pública:
    from pdf_engine.orgaudi import gerar_laudo_v250          # HTML/Chrome (padrão)
    from pdf_engine.orgaudi import LaudoOrgAudi              # ReportLab (alternativa)
    from pdf_engine.orgaudi import gerar_laudo_orgaudi       # adapter nfa-repo
    from pdf_engine.orgaudi import (
        Achado, Contribuinte, NotaFiscal, Periodo,
        Severidade, NaturezaNota, CategoriaContabil,
    )

Design specs (v2.5):
  Formato     : A4 · 210 × 297 mm
  Tipografia  : Manrope · JetBrains Mono
  Cor primária: #0B3B5C   Acento: #14B8A6
  Severidade  : Crítico · Alto · Médio · Atenção · Conforme
  Conformidade: NBC TA · CPC 47 / 25 / 27
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
from .report_builder import gerar_laudo_v250
from .report_builder_rl import LaudoOrgAudi
from .adapter import gerar_laudo_orgaudi

# Alias semântico — padrão atual em produção
gerar_laudo = gerar_laudo_v250

__all__ = [
    # API principal
    "gerar_laudo",
    "gerar_laudo_v250",
    "LaudoOrgAudi",
    "gerar_laudo_orgaudi",
    # Dataclasses + enums
    "Achado",
    "CategoriaContabil",
    "Contribuinte",
    "NaturezaNota",
    "NotaFiscal",
    "Periodo",
    "Severidade",
]

__version__ = "2.5.0"
