"""
pdf_engine.orgaudi.handlers  (PATCH — CRC integrado)
Alterações:
  - Rodapé e cabeçalho consomem RESPONSAVEL de credenciais.py
  - Fim das strings hardcoded de nome/CRC
"""
from __future__ import annotations

import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors as rl_colors

from .styles import AZUL, AZUL_CL, BRANCO, CBORD, CTXT, _get_logo_h, _get_logo_t

# CRC oficial — fonte única da verdade
try:
    from horizon_blue_one.orgaudi.credenciais import RESPONSAVEL
    _RODAPE_NOME = RESPONSAVEL.linha_rodape()
    _ASSINATURA  = RESPONSAVEL.linha_assinatura()
except ImportError:
    # Fallback se horizon_blue_one não estiver no path
    _RODAPE_NOME = "Robson Alain Veloso — Ciências Contábeis · CRC TO-002032/O-5 T-GO"
    _ASSINATURA  = "Robson Alain Veloso\nCiências Contábeis · CRC TO-002032/O-5 T-GO\nORGATEC CONTABILIDADE E AUDITORIA"

_OURO     = rl_colors.HexColor("#C08B18")
_ACCENT_H = 2.0  # mm

logger = logging.getLogger("orgaudi")


def criar_handler_pagina(total_paginas: int = 8):
    """
    Cria handlers first/later com CRC lido de credenciais.py.
    Thread-safe via closure.
    """
    estado = {"atual": 0, "total": total_paginas}

    _logo_h_cache = _logo_h_size = None
    _logo_t_cache = _logo_t_size = None

    logo_h_path = _get_logo_h()
    if logo_h_path:
        try:
            _logo_h_cache = ImageReader(logo_h_path)
            _logo_h_size  = _logo_h_cache.getSize()
        except Exception as e:
            logger.debug("Logo header não carregada: %s", e)

    logo_t_path = _get_logo_t()
    if logo_t_path:
        try:
            _logo_t_cache = ImageReader(logo_t_path)
            _logo_t_size  = _logo_t_cache.getSize()
        except Exception as e:
            logger.debug("Logo transparente não carregada: %s", e)

    def _desenhar_cabecalho(canvas):
        w, h = A4
        lm, rm = 14 * mm, w - 14 * mm

        # Banda dourada
        ah = _ACCENT_H * mm
        canvas.setFillColor(_OURO)
        canvas.rect(0, h - ah, w, ah, fill=1, stroke=0)

        # Bloco azul
        CH = 15 * mm
        CY = h - ah - CH
        canvas.setFillColor(AZUL)
        canvas.rect(0, CY, w, CH, fill=1, stroke=0)

        logo_w = 0
        if _logo_h_cache is not None:
            try:
                iw, ih = _logo_h_size
                aspect = iw / ih if ih > 0 else 1.0
                lh = CH * 0.80
                lw = lh * aspect
                ly = CY + (CH - lh) / 2
                canvas.drawImage(
                    _logo_h_cache, lm + 1 * mm, ly,
                    width=lw, height=lh,
                    preserveAspectRatio=True, mask="auto",
                )
                logo_w = lw + 3 * mm
            except Exception as e:
                logger.debug("Logo header não desenhada: %s", e)

        xt = lm + max(logo_w, 16 * mm)
        canvas.setFillColor(BRANCO)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.drawString(xt, CY + CH * 0.60, "ORGATEC")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(xt, CY + CH * 0.24, "CONTABILIDADE E AUDITORIA")

        estado["atual"] += 1
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(
            rm - 1 * mm, CY + CH * 0.60,
            f"Página {estado['atual']} de {estado['total']}",
        )
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(rm - 1 * mm, CY + CH * 0.24, "OrgAudi 1.0")

        canvas.setStrokeColor(_OURO)
        canvas.setLineWidth(1.5)
        canvas.line(0, CY - 0.4 * mm, w, CY - 0.4 * mm)

    def _desenhar_rodape(canvas):
        w, h = A4
        lm, rm = 14 * mm, w - 14 * mm

        canvas.setStrokeColor(CBORD)
        canvas.setLineWidth(0.5)
        canvas.line(lm, 14 * mm, rm, 14 * mm)
        canvas.setStrokeColor(_OURO)
        canvas.setLineWidth(0.8)
        canvas.line(lm, 13.3 * mm, rm, 13.3 * mm)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(CTXT)
        # Usa linha_rodape() de credenciais.py — sem hardcode
        canvas.drawCentredString(
            w / 2, 9.5 * mm,
            f"ORGATEC CONTABILIDADE E AUDITORIA  ·  "
            f"{_RODAPE_NOME}  ·  OrgAudi 1.0",
        )
        canvas.setFont("Helvetica", 6)
        canvas.drawCentredString(
            w / 2, 6.5 * mm,
            "Documento de uso restrito — para fins fiscais e contábeis exclusivamente",
        )

    def _handler_first(canvas, doc):
        canvas.saveState()
        _desenhar_cabecalho(canvas)

        if _logo_t_cache is not None:
            try:
                w, h = A4
                iw, ih = _logo_t_size
                aspect = iw / ih if ih > 0 else 1.0
                lg_h = 28 * mm
                lg_w = lg_h * aspect
                ah = _ACCENT_H * mm
                CH = 15 * mm
                CY = h - ah - CH
                logo_x = (w - lg_w) / 2
                logo_y = CY - 5 * mm - lg_h
                canvas.drawImage(
                    _logo_t_cache, logo_x, logo_y,
                    width=lg_w, height=lg_h,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception as e:
                logger.debug("Logo grande não desenhada: %s", e)

        _desenhar_rodape(canvas)
        canvas.restoreState()

    def _handler_later(canvas, doc):
        canvas.saveState()
        _desenhar_cabecalho(canvas)
        _desenhar_rodape(canvas)
        canvas.restoreState()

    return _handler_first, _handler_later
