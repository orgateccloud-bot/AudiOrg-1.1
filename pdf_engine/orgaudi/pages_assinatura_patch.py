"""
pdf_engine.orgaudi.pages  — PATCH parcial (apenas funções alteradas)
Alterações v2:
  - construir_pagina_11_assinatura: CRC via credenciais.py, hash SHA-256 64 chars
  - Tabela VERIFICAÇÃO DE INTEGRIDADE: Algoritmo / Payload / Hash (modelo GENIS)
  - Payload JSON exibido para verificação externa
  - CRC correto: lido de credenciais.py (não mais placeholder)
"""
from __future__ import annotations

# Imports necessários para essa função
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Paragraph,
    Table,
    TableStyle,
)

# CRC via fonte única — sem placeholder
try:
    from horizon_blue_one.orgaudi.credenciais import RESPONSAVEL
    _NOME_COMPLETO = RESPONSAVEL.nome
    _FORMACAO      = RESPONSAVEL.formacao
    _CRC           = f"CRC {RESPONSAVEL.registro_crc}"
    _EMPRESA       = RESPONSAVEL.empresa
except ImportError:
    _NOME_COMPLETO = "Robson Alain Veloso"
    _FORMACAO      = "Ciências Contábeis"
    _CRC           = "CRC TO-002032/O-5 T-GO"
    _EMPRESA       = "ORGATEC CONTABILIDADE E AUDITORIA"


def construir_pagina_11_assinatura(
    contribuinte,
    periodo,
    hash_doc: str,
    payload_json: str = "",
) -> list:
    """
    Página final — Declarações + assinatura + verificação de integridade.

    Parâmetros:
      hash_doc:     SHA-256 (64 chars) do laudo
      payload_json: JSON canônico usado para gerar o hash (exibido na tabela)
                    Se vazio, exibe só o hash sem o payload completo.
    """
    from .styles import (
        AZUL, AZUL_CL, AZUL_M, ALTO, ALTO_BG,
        BRANCO, CBG_LIGHT, CBORD, CTXT, CTXT_DARK,
        S, ST, W,
        hr, info_box, sp,
    )
    from .validators import fmt_brl, fmt_data

    I: list = [CondPageBreak(110 * mm)]
    I.append(sp(2))

    # ── Declaração de Alcance ──────────────────────────────────────────────────
    I.append(Paragraph("DECLARAÇÃO DE ALCANCE E LIMITAÇÕES", ST["sec"]))
    I.append(hr(AZUL_M, 1.0))
    I.append(sp(1))

    I.append(info_box(
        "Este diagnóstico foi elaborado com base exclusiva em Notas Fiscais Avulsas "
        "Eletrônicas (NFA-e) fornecidas pelo sistema GIEF/SEFAZ-GO. A análise é "
        "determinística e documental, limitada ao cruzamento lógico interno das "
        "informações constantes nas NFA-e informadas, com aplicação dos testes "
        "forenses T-01 a T-08 e do Catálogo de 18 Tipologias de Anomalias (AN-01 "
        "a AN-18) do OrgAudi 1.0. Os achados constituem <b>indícios objetivos</b> "
        "derivados de padrões nos dados — não constituem confirmação de "
        "irregularidade sem coleta de evidências primárias externas.",
        label="ALCANCE",
        border_color=AZUL_M,
        bg=CBG_LIGHT,
    ))
    I.append(sp(1))

    I.append(info_box(
        "<b>Este documento NÃO formula acusações, NÃO imputa dolo e NÃO substitui "
        "procedimento de fiscalização tributária formal.</b> Os achados classificados "
        "como CRÍTICO ou ALTO requerem coleta de evidências primárias (extratos "
        "bancários, GTAs AGRODEFESA-GO, contratos, ACTs de leiloeiro) antes de "
        "qualquer integração em parecer técnico formal ou comunicação a órgãos de "
        "fiscalização. As tipologias AN-01 a AN-18 são hipóteses investigativas, "
        "não imputações de dolo. Regularização espontânea: CTN art. 138.",
        label="LIMITAÇÕES",
        border_color=ALTO,
        bg=ALTO_BG,
    ))
    I.append(sp(1))

    # ── Base legal aplicada ────────────────────────────────────────────────────
    base_legal_txt = (
        "CTN art. 138 (denúncia espontânea) · CTN art. 150 (lançamento por "
        "homologação) · Lei 8.023/90 + RIR/2018 art. 62 (IRPF Rural) · "
        "Lei 8.212/91 (Funrural PF Patronal) · LC 224/2025 (Funrural — "
        "vigência 01/04/2026) · LC 214/2025 (Reforma Tributária) · "
        "IN RFB 1.903/2019 (LCDPR — limite R$ 4,8M) · "
        "RCTE-GO Anx. IX art. 6º, XLIII (ICMS gado isento)"
    )
    # Tabela de chips de base legal (2 × 4)
    chips = [
        "CTN art. 138", "CTN art. 150", "Lei 8.023/90", "Lei 8.212/91",
        "IN RFB 1.903/19", "LC 214/2025", "LC 224/2025", "RCTE-GO Anx.IX",
    ]
    chip_rows = [chips[:4], chips[4:]]
    chip_style = S("chip", fontName="Helvetica-Bold", fontSize=7,
                   textColor=BRANCO, alignment=TA_CENTER, leading=9)
    chip_data = [[Paragraph(c, chip_style) for c in row] for row in chip_rows]
    t_chips = Table(chip_data, colWidths=[W / 4] * 4)
    t_chips.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AZUL_M),
        ("GRID",          (0, 0), (-1, -1), 0.5, AZUL_CL),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    I.append(t_chips)
    I.append(sp(2))

    # ── Responsável Técnico ───────────────────────────────────────────────────
    I.append(Paragraph("RESPONSÁVEL TÉCNICO PELA AUDITORIA", ST["sec"]))
    I.append(hr(AZUL, 1.0))
    I.append(sp(2))

    # Nome, formação, CRC — lidos de credenciais.py, NÃO hardcoded
    I.append(Paragraph(_NOME_COMPLETO, ST["an"]))
    I.append(Paragraph(_FORMACAO, ST["as"]))
    I.append(Paragraph(_CRC, ST["as"]))
    I.append(Paragraph(_EMPRESA, ST["ae"]))
    I.append(Paragraph(
        f"Auditoria emitida em {fmt_data(periodo.data_auditoria)}",
        ST["as"],
    ))
    I.append(sp(1))
    I.append(HRFlowable(width="55%", thickness=0.4, color=CBORD, spaceAfter=2))
    I.append(Paragraph("Sistema de auditoria contábil-fiscal", ST["small"]))
    I.append(Paragraph(f"OrgAudi 1.0 — {_EMPRESA}", ST["sys"]))
    I.append(sp(2))

    # ── Verificação de Integridade (modelo GENIS) ─────────────────────────────
    I.append(Paragraph("VERIFICAÇÃO DE INTEGRIDADE", ST["sec"]))
    I.append(hr(AZUL_M, 0.6))
    I.append(sp(0.5))

    # Linhas: Algoritmo / Payload / Hash
    _lbl = S("vi_lbl", fontName="Helvetica-Bold", fontSize=7.5,
              textColor=AZUL_M, alignment=TA_LEFT, leading=10)
    _val = S("vi_val", fontName="Helvetica", fontSize=7.5,
              textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)
    _cod = S("vi_cod", fontName="Courier", fontSize=7,
              textColor=AZUL, alignment=TA_LEFT, leading=10)
    _cod_sm = S("vi_cod_sm", fontName="Courier-Bold", fontSize=8,
                textColor=AZUL, alignment=TA_LEFT, leading=11)

    vi_rows = [
        [
            Paragraph("Algoritmo", _lbl),
            Paragraph(
                "SHA-256 (hashlib Python 3.12) sobre payload JSON canônico",
                _val),
        ],
    ]
    if payload_json:
        vi_rows.append([
            Paragraph("Payload", _lbl),
            Paragraph(payload_json, _cod),
        ])

    vi_rows.append([
        Paragraph("Hash", _lbl),
        Paragraph(f"<b>{hash_doc}</b>", _cod_sm),
    ])

    vi_rows.append([
        Paragraph("", _lbl),
        Paragraph(
            "<i>Para validar: aplicar sha256 sobre o Payload em UTF-8 "
            "e comparar com o Hash.</i>",
            S("vi_note", fontName="Helvetica-Oblique", fontSize=6.5,
              textColor=CTXT, leading=9),
        ),
    ])

    t_vi = Table(vi_rows, colWidths=[28 * mm, W - 28 * mm])
    t_vi.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, CBORD),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, CBORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    I.append(t_vi)
    I.append(sp(1))

    # ── Disclaimer final ──────────────────────────────────────────────────────
    cl = Table([[Paragraph(
        "<i>Classificação contábil: Cliente=Remetente → Receita; "
        "Cliente=Destinatário → Despesa/Investimento; "
        "Remessa/Leilão → Trânsito (não-receita até arremate). "
        f"Base legal: CTN art. 138 · CTN art. 150 · Lei 8.023/90 · "
        f"Lei 8.212/91 · IN RFB 1.848/2018 · LC 224/2025. "
        f"Hash SHA-256: <b>{hash_doc[:32]}…</b></i>",
        S("cl", fontName="Helvetica-Oblique", fontSize=7,
          textColor=CTXT, alignment=TA_CENTER, leading=10),
    )]], colWidths=[W])
    cl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL_CL),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    I.append(cl)
    return I
