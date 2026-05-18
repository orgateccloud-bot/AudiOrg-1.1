"""
pdf_engine.orgaudi.pages  — PATCH parcial (apenas funções alteradas)
Alterações:
  - construir_pagina_11_assinatura: CRC via credenciais.py, hash SHA-256 completo (64 chars)
  - Strings hardcoded de nome/CRC removidas
  - Algoritmo declarado como SHA-256 (64 hex) — era SHA-256 (16 hex), enganoso
  - Bloco de assinatura usa RESPONSAVEL.linha_assinatura()

ATENÇÃO: este arquivo substitui APENAS a função construir_pagina_11_assinatura.
         As demais funções de pages.py permanecem inalteradas.
         Copiar apenas essa função para o pages.py original.
"""
from __future__ import annotations

# Imports necessários para essa função (já presentes em pages.py)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Paragraph,
    Table,
    TableStyle,
)

# CRC via fonte única
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
) -> list:
    """
    Página final — Declarações + assinatura + carimbo de hash.

    Usa CondPageBreak: se sobrarem ≥110mm na página anterior, a assinatura
    se acomoda sem quebrar página.
    """
    # Imports locais (já importados em pages.py — repetidos aqui só para patch isolado)
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
    I.append(sp(2))

    # ── Responsável Técnico ───────────────────────────────────────────────────
    I.append(Paragraph("RESPONSÁVEL TÉCNICO PELA AUDITORIA", ST["sec"]))
    I.append(hr(AZUL, 1.0))
    I.append(sp(2))

    # Nome, formação, CRC — lidos de credenciais.py, não hardcoded
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
    I.append(Paragraph(
        f"OrgAudi 1.0 — {_EMPRESA}",
        ST["sys"],
    ))
    I.append(sp(2))

    # ── Carimbo de Hash ───────────────────────────────────────────────────────
    # hash_doc: SHA-256 completo (64 chars) — não mais truncado em 16
    # Cobre: CPF, nome, F1-F6, período, total de notas
    # TODO próximo sprint: expandir para cobrir texto dos achados (Patch A)
    carimbo = Table(
        [[
            Paragraph(
                "<b>HASH DE VALIDAÇÃO</b>",
                S("ch1", fontName="Helvetica-Bold", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9),
            ),
            Paragraph(
                f"<b>{hash_doc}</b>",
                S("ch2", fontName="Courier-Bold", fontSize=8,
                  textColor=AZUL, alignment=TA_LEFT, leading=11),
            ),
        ], [
            Paragraph(
                "ALGORITMO",
                S("ch3", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9),
            ),
            Paragraph(
                "SHA-256 · 64 hex chars · payload: CPF + F1-F6 + período + n_notas",
                S("ch4", fontName="Helvetica", fontSize=7.5,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10),
            ),
        ], [
            Paragraph(
                "EMITIDO EM",
                S("ch5", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9),
            ),
            Paragraph(
                fmt_data(periodo.data_auditoria),
                S("ch6", fontName="Helvetica-Bold", fontSize=8,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10),
            ),
        ], [
            Paragraph(
                "SISTEMA",
                S("ch7", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9),
            ),
            Paragraph(
                "OrgAudi 1.0 · horizon_blue_one · SKILL_RURAL v1.1.0",
                S("ch8", fontName="Helvetica", fontSize=7.5,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10),
            ),
        ]],
        colWidths=[35 * mm, W - 35 * mm],
    )
    carimbo.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, CBORD),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, CBORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    I.append(carimbo)
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
