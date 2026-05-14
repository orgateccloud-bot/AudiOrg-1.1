"""
orgaudi.pdf.handlers
════════════════════
Handlers que desenham diretamente no canvas do ReportLab (cabeçalho azul
com logo + paginação, rodapé com créditos, logo grande centralizada na
capa).

Estes handlers são chamados pelo SimpleDocTemplate via `onFirstPage` e
`onLaterPages` durante o build do PDF.

Dependências internas: orgaudi.styles (paleta + caminhos de logo)
Dependências externas: reportlab
"""
from __future__ import annotations

import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from reportlab.lib import colors as rl_colors

from .styles import AZUL, AZUL_CL, BRANCO, CBORD, CTXT, _get_logo_h, _get_logo_t

# Banda de acento dourado no topo — identidade premium ORGATEC
_OURO = rl_colors.HexColor("#C08B18")   # ouro institucional
_ACCENT_H = 2.0  # mm — altura da banda dourada


logger = logging.getLogger("orgaudi")


def criar_handler_pagina(total_paginas: int = 8):
    """
    Cria handlers de página com contador encapsulado em closure (thread-safe).

    Retorna tupla (handler_first, handler_later):
      - handler_first: primeira página — cabeçalho azul + logo grande centralizada no corpo
      - handler_later: demais páginas — apenas cabeçalho azul (sem logo no corpo)

    Ambos compartilham o mesmo contador de páginas.

    O parâmetro `total_paginas` deve ser ajustado para o total real do PDF
    (descoberto via two-pass build no LaudoOrgAudi.gerar_pdf).

    OTIMIZAÇÃO: ImageReaders das logos são criados UMA ÚNICA VEZ no closure
    e reutilizados em todas as páginas. Sem isso, cada `drawImage` chamado
    com um ImageReader recém-criado embeda a imagem de novo no PDF — gerando
    um PDF de ~657 KB para 8 páginas com a mesma logo, em vez de ~70 KB.
    """
    estado = {"atual": 0, "total": total_paginas}

    # ─── Cache de ImageReaders (criado uma vez, reutilizado em todas as páginas) ───
    # ReportLab deduplica imagens automaticamente quando o MESMO objeto
    # ImageReader é passado para drawImage múltiplas vezes.
    _logo_h_cache = None
    _logo_h_size = None
    _logo_t_cache = None
    _logo_t_size = None

    logo_h_path = _get_logo_h()
    if logo_h_path:
        try:
            _logo_h_cache = ImageReader(logo_h_path)
            _logo_h_size = _logo_h_cache.getSize()
        except Exception as e:
            logger.debug("Logo header não pôde ser carregado: %s", e)

    logo_t_path = _get_logo_t()
    if logo_t_path:
        try:
            _logo_t_cache = ImageReader(logo_t_path)
            _logo_t_size = _logo_t_cache.getSize()
        except Exception as e:
            logger.debug("Logo transparente não pôde ser carregada: %s", e)

    def _desenhar_cabecalho(canvas):
        """Cabeçalho azul padrão: banda dourada + logo + ORGATEC + paginação."""
        w, h = A4
        lm, rm = 14 * mm, w - 14 * mm

        # ── Banda dourada premium no topo da página ──────────────────────────
        ah = _ACCENT_H * mm
        canvas.setFillColor(_OURO)
        canvas.rect(0, h - ah, w, ah, fill=1, stroke=0)

        # ── Cabeçalho azul (abaixo da banda dourada) ──────────────────────────
        CH = 15 * mm                      # altura do bloco azul
        CY = h - ah - CH                  # base do bloco azul

        canvas.setFillColor(AZUL)
        canvas.rect(0, CY, w, CH, fill=1, stroke=0)

        logo_header_w = 0  # largura ocupada pela logo (para posicionar texto)
        if _logo_h_cache is not None:
            try:
                iw, ih = _logo_h_size
                aspect = iw / ih if ih > 0 else 1.0
                lh = CH * 0.80
                lw = lh * aspect
                ly = CY + (CH - lh) / 2
                canvas.drawImage(_logo_h_cache, lm + 1 * mm, ly,
                                 width=lw, height=lh,
                                 preserveAspectRatio=True, mask="auto")
                logo_header_w = lw + 3 * mm
            except Exception as e:
                logger.debug("Logo header não pôde ser desenhado: %s", e)

        xt = lm + max(logo_header_w, 16 * mm)
        canvas.setFillColor(BRANCO)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.drawString(xt, CY + CH * 0.60, "ORGATEC")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(xt, CY + CH * 0.24, "CONTABILIDADE E AUDITORIA")

        estado["atual"] += 1
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(rm - 1 * mm, CY + CH * 0.60,
                               f"Página {estado['atual']} de {estado['total']}")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(rm - 1 * mm, CY + CH * 0.24, "OrgAudi 1.0")

        # Linha de separação dourada entre header e conteúdo
        canvas.setStrokeColor(_OURO)
        canvas.setLineWidth(1.5)
        canvas.line(0, CY - 0.4 * mm, w, CY - 0.4 * mm)

    def _desenhar_rodape(canvas):
        """Rodapé aprimorado: linha dupla + créditos com separadores de ponto."""
        w, h = A4
        lm, rm = 14 * mm, w - 14 * mm

        # Linha principal do rodapé
        canvas.setStrokeColor(CBORD)
        canvas.setLineWidth(0.5)
        canvas.line(lm, 14 * mm, rm, 14 * mm)
        # Linha dourada fina abaixo
        canvas.setStrokeColor(_OURO)
        canvas.setLineWidth(0.8)
        canvas.line(lm, 13.3 * mm, rm, 13.3 * mm)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(CTXT)
        canvas.drawCentredString(
            w / 2, 9.5 * mm,
            "ORGATEC CONTABILIDADE E AUDITORIA  ·  "
            "Robson Alain Veloso — Ciências Contábeis  ·  "
            "OrgAudi 1.0")
        # Micro-texto de confidencialidade
        canvas.setFont("Helvetica", 6)
        canvas.drawCentredString(
            w / 2, 6.5 * mm,
            "Documento de uso restrito — para fins fiscais e contábeis exclusivamente")

    def _handler_first(canvas, doc):
        """Primeira página: cabeçalho + logo grande centralizada + rodapé."""
        canvas.saveState()
        _desenhar_cabecalho(canvas)

        # Logo grande centralizada no corpo da página 1 (reutiliza cache)
        if _logo_t_cache is not None:
            try:
                w, h = A4
                iw, ih = _logo_t_size
                aspect = iw / ih if ih > 0 else 1.0

                # Tamanho da logo grande
                lg_h = 28 * mm
                lg_w = lg_h * aspect

                # Posicionar centralizada: abaixo da banda dourada + header azul
                ah = _ACCENT_H * mm
                CH = 15 * mm
                CY = h - ah - CH  # base do header
                logo_x = (w - lg_w) / 2
                logo_y = CY - 5 * mm - lg_h
                canvas.drawImage(_logo_t_cache, logo_x, logo_y,
                                 width=lg_w, height=lg_h,
                                 preserveAspectRatio=True, mask="auto")
            except Exception as e:
                logger.debug("Logo grande (p1) não pôde ser desenhada: %s", e)

        _desenhar_rodape(canvas)
        canvas.restoreState()

    def _handler_later(canvas, doc):
        """Demais páginas: apenas cabeçalho + rodapé (sem logo no corpo)."""
        canvas.saveState()
        _desenhar_cabecalho(canvas)
        _desenhar_rodape(canvas)
        canvas.restoreState()

    return _handler_first, _handler_later
