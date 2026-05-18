"""
pdf_engine — Motor único de geração de PDFs OrgAudi 1.1
═══════════════════════════════════════════════════════════

A partir do OrgAudi 1.1, **um único gerador** é oficial e suportado:

    from pdf_engine import gerar_pdf_auditoria_cruzada

    pdf_bytes = gerar_pdf_auditoria_cruzada(resultado, modo="simplificado")
    # modo="completo" → laudo com catálogo AN-01..AN-18 + RE-1 + tipologias

O schema de `resultado` está documentado em:
  • docs/schemas/auditoria_cruzada_v2.json    (16 chaves — modo simplificado)
  • docs/schemas/auditoria_cruzada.json       (21 chaves — modo completo)

Implementação:
  api/services/auditoria_cruzada_pdf.py
    └── pdf_engine/orgaudi_v240/{styles, domain, gerador_achados, ...}
        (módulos auxiliares; não chamar diretamente)

Geradores anteriores (orgaudi_v250 HTML/Chrome, LaudoOrgAudi ReportLab,
scripts ad-hoc, etc.) foram movidos para `pdf_engine/_legacy/` e não
devem ser referenciados em código novo.
"""
from __future__ import annotations

# Re-export do gerador canônico (importação preguiçosa evita acoplamento)
def gerar_pdf_auditoria_cruzada(resultado: dict, modo: str = "completo") -> bytes:
    """Gera o PDF do laudo a partir do dict-resposta da auditoria cruzada.

    Args:
        resultado: payload retornado por `processar_auditoria_cruzada` ou
                    qualquer dict que respeite o schema auditoria_v2.json.
        modo: "simplificado" (6 páginas) ou "completo" (16 páginas).

    Returns:
        bytes do PDF (A4, retrato).
    """
    from api.services.auditoria_cruzada_pdf import (
        gerar_pdf_auditoria_cruzada as _impl,
    )
    return _impl(resultado, modo=modo)


__all__ = ["gerar_pdf_auditoria_cruzada"]
__version__ = "1.1.0"
