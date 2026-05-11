"""
pdf_engine — Motor de geração de laudos PDF (OrgAudi)
══════════════════════════════════════════════════════
Pacote raiz com três motores coexistentes:

  orgaudi_v4   → legado, single-file 152 KB + adapter NFA→NotaFiscal
                 (ainda usado por api/services/auditoria_bigfour.py)
  orgaudi_v240 → ReportLab Platypus, 11 páginas, dataclasses de domínio
  orgaudi_v250 → HTML+CSS + Chrome headless · ATUAL · Manrope + JetBrains
                 · capa editorial com gradiente

API pública recomendada (atalho para o v250):
    from pdf_engine import gerar_laudo_v250, gerar_laudo_sem_objeto_v250

    gerar_laudo_v250(notas, "NOME", "CPF", Path("laudo.pdf"))
    gerar_laudo_sem_objeto_v250("NOME", "CPF", Path("laudo.pdf"))

Quando `notas == []`, `gerar_laudo_v250` delega automaticamente para
`gerar_laudo_sem_objeto_v250` (auditoria sem objeto).
"""
from .orgaudi_v250 import gerar_laudo_sem_objeto_v250, gerar_laudo_v250

__all__ = ["gerar_laudo_v250", "gerar_laudo_sem_objeto_v250"]
__version__ = "2.5.0"
