"""
Shim de compatibilidade — `api.routes.auditoria` historicamente importava
um único módulo `api.services.auditoria` que foi dividido em três:

- `auditoria_nfae`      → processar_nfae, gerar_pdf_nfae, resultados_store
- `auditoria_bigfour`   → processar_lote_auditoria (pipeline completo)
- `auditoria_tasks`     → tasks_status (proxy de DB)

Este módulo reexporta os símbolos para manter o import legado funcionando.
"""
from __future__ import annotations

from api.services.auditoria_bigfour import processar_lote_auditoria
from api.services.auditoria_nfae import (
    gerar_pdf_nfae,
    processar_nfae,
    resultados_store,
)
from api.services.auditoria_tasks import tasks_status

__all__ = [
    "gerar_pdf_nfae",
    "processar_lote_auditoria",
    "processar_nfae",
    "resultados_store",
    "tasks_status",
]
