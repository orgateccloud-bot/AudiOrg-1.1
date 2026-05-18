"""scripts/gerar_relatorio_fragmentacao.py

Gera PDF consolidado da análise T-02 (fragmentação fiscal) executada por
scripts/analise_fragmentacao_t02.py. Lê o JSON consolidado e produz
relatório forense com lista detalhada de achados.

Saída: reports_nfa/RELATORIO_FRAGMENTACAO_T02_<data>.pdf
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DEST = RAIZ / "reports_nfa"
LOGO = RAIZ / "pdf_engine" / "orgaudi_v240" / "assets" / "logo_orgatec.png"

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (Image as RLImage, PageBreak, Paragraph,
                                   SimpleDocTemplate, Spacer, Table, TableStyle)

from pdf_engine.orgaudi_v240.styles import AZUL, AZUL_M, BRANCO, CTXT, CTXT_DARK, CBORD

CRITICO  = HexColor("#D63333")
ALTO     = HexColor("#E68A00")
CONFORME = HexColor("#1F8B4C")
CINZA_F  = HexColor("#F5F7FA")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                     fontSize=18, textColor=AZUL, alignment=TA_CENTER, leading=22)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                     fontSize=12, textColor=AZUL, alignment=TA_LEFT, leading=15,
                     spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica",
                       fontSize=9, textColor=CTXT_DARK, alignment=TA_LEFT, leading=12)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica",
                        fontSize=7.5, textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)
SUB = ParagraphStyle("Sub", parent=styles["Normal"], fontName="Helvetica-Oblique",
                      fontSize=9, textColor=CTXT, alignment=TA_CENTER, leading=11)


def brl(v) -> str:
    try: d = Decimal(str(v))
    except: return "—"
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def main() -> None:
    data_str = datetime.now().strftime("%Y-%m-%d")
    json_path = DEST / f"ANALISE_FRAGMENTACAO_T02_{data_str}.json"
    if not json_path.exists():
        print(f"[ERRO] Execute primeiro: python scripts/analise_fragmentacao_t02.py")
        sys.exit(1)
    dados = json.loads(json_path.read_text(encoding="utf-8"))

    # Filtra clientes com achados
    com_achados = [c for c in dados if c.get("achados")]
    total_a = sum(c["qtd_a"] for c in dados)
    total_b = sum(c["qtd_b"] for c in dados)
    total_notas = sum(c["qtd_notas"] for c in dados)

    saida = DEST / f"RELATORIO_FRAGMENTACAO_T02_{data_str}.pdf"
    doc = SimpleDocTemplate(
        str(saida), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title="Relatório T-02 — Fragmentação Fiscal",
        author="ORGATEC AUDITORIA FISCAL SOBERANA",
    )

    story = []
    # ── Capa ──────────────────────────────────────────────────────────────
    if LOGO.exists():
        story.append(Spacer(1, 4 * mm))
        story.append(Table(
            [[RLImage(str(LOGO), width=28 * mm, height=28 * mm,
                       kind="proportional", mask="auto")]],
            colWidths=[170 * mm],
            style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("<b>ORGATEC</b>", ParagraphStyle(
        "logo", fontName="Helvetica-Bold", fontSize=16, textColor=AZUL,
        alignment=TA_CENTER, leading=20)))
    story.append(Paragraph("CONTABILIDADE E AUDITORIA", ParagraphStyle(
        "logo2", fontName="Helvetica-Bold", fontSize=9, textColor=AZUL,
        alignment=TA_CENTER, leading=12)))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("ANÁLISE FORENSE T-02", H1))
    story.append(Paragraph("FRAGMENTAÇÃO FISCAL (SMURFING)", H1))
    story.append(Paragraph(
        f"<i>Bateria de testes sobre {len(dados)} contribuintes · "
        f"{total_notas} NFA-e analisadas · período 2025</i>", SUB))
    story.append(Spacer(1, 6 * mm))

    # ── Resumo ────────────────────────────────────────────────────────────
    story.append(Paragraph("RESUMO EXECUTIVO", H2))
    story.append(Paragraph(
        f"O Teste T-02 do skill OrgAudi 1.1 detectou <b>{total_a + total_b} achados "
        f"críticos</b> em <b>{len(com_achados)} contribuintes</b> da carteira "
        f"(de {len(dados)} auditados). Critérios aplicados:",
        BODY))
    story.append(Spacer(1, 2 * mm))
    rows_crit = [
        [Paragraph("<b>CRÍTICO-A</b>", BODY),
         Paragraph("≥ 3 NFA-e para o mesmo destinatário no MESMO DIA com 3+ valores idênticos", BODY),
         Paragraph(f"<b>{total_a}</b>", ParagraphStyle("ct", parent=BODY, alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=CRITICO))],
        [Paragraph("<b>CRÍTICO-B</b>", BODY),
         Paragraph("≥ 5 NFA-e para o mesmo destinatário em 7 DIAS com 2+ valores iguais", BODY),
         Paragraph(f"<b>{total_b}</b>", ParagraphStyle("ct2", parent=BODY, alignment=TA_CENTER, fontName="Helvetica-Bold", textColor=ALTO))],
    ]
    tbl = Table(rows_crit, colWidths=[26 * mm, 120 * mm, 24 * mm])
    tbl.setStyle(TableStyle([
        ("GRID",        (0, 0), (-1, -1), 0.3, CBORD),
        ("BACKGROUND",  (0, 0), (-1, -1), CINZA_F),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))

    # ── Tabela mapa ────────────────────────────────────────────────────────
    story.append(Paragraph("MAPA DE FRAGMENTAÇÃO POR CONTRIBUINTE", H2))
    cab = [
        Paragraph("<b>#</b>", BODY),
        Paragraph("<b>CONTRIBUINTE</b>", BODY),
        Paragraph("<b>NOTAS</b>", BODY),
        Paragraph("<b>T-02 A</b>", BODY),
        Paragraph("<b>T-02 B</b>", BODY),
        Paragraph("<b>STATUS</b>", BODY),
    ]
    rows = [cab]
    for i, c in enumerate(sorted(dados, key=lambda x: -(x["qtd_a"] + x["qtd_b"])), 1):
        if c["qtd_a"] + c["qtd_b"] > 0:
            status = f'<font color="#{CRITICO.hexval()[2:]}"><b>DETECTADO</b></font>'
        elif c["qtd_notas"] > 0:
            status = f'<font color="#{CONFORME.hexval()[2:]}"><b>CONFORME</b></font>'
        else:
            status = '<font color="#888888">SEM OPS</font>'
        rows.append([
            Paragraph(str(i), SMALL),
            Paragraph(c["prefixo"], SMALL),
            Paragraph(str(c["qtd_notas"]), ParagraphStyle("c1", parent=SMALL, alignment=TA_CENTER)),
            Paragraph(str(c["qtd_a"]), ParagraphStyle("c2", parent=SMALL, alignment=TA_CENTER)),
            Paragraph(str(c["qtd_b"]), ParagraphStyle("c3", parent=SMALL, alignment=TA_CENTER)),
            Paragraph(status, ParagraphStyle("c4", parent=SMALL, alignment=TA_CENTER)),
        ])
    tbl_mapa = Table(rows, colWidths=[8*mm, 50*mm, 20*mm, 20*mm, 20*mm, 35*mm], repeatRows=1)
    tbl_mapa.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",        (0, 0), (-1, -1), 0.3, CBORD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA_F]),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl_mapa)
    story.append(PageBreak())

    # ── Detalhamento dos achados ──────────────────────────────────────────
    story.append(Paragraph("DETALHAMENTO DOS ACHADOS CRÍTICOS", H1))
    story.append(Spacer(1, 4 * mm))
    for c in com_achados:
        story.append(Paragraph(
            f"<b>{c['prefixo']}</b> &nbsp;·&nbsp; {len(c['achados'])} achado(s) em "
            f"{c['qtd_notas']} NFA-e analisadas", H2))
        for a in c["achados"]:
            cor = CRITICO if a["tipo"] == "CRITICO_A" else ALTO
            tag = "CRÍTICO-A" if a["tipo"] == "CRITICO_A" else "CRÍTICO-B"
            cor_hex = cor.hexval()[2:]
            story.append(Paragraph(
                f'<font color="#{cor_hex}"><b>[{tag}]</b></font> &nbsp; '
                f'<b>Destinatário:</b> {a["destinatario"]} '
                f'(CPF {a["cpf"]})', BODY))
            if a["tipo"] == "CRITICO_A":
                story.append(Paragraph(
                    f'&nbsp;&nbsp;<b>Data:</b> {a["data"]} &nbsp;·&nbsp; '
                    f'<b>Notas:</b> {a["qtd_notas"]} '
                    f'({a["qtd_iguais"]} com valor IDÊNTICO) &nbsp;·&nbsp; '
                    f'<b>Total:</b> {brl(a["valor_total"])}', BODY))
            else:
                story.append(Paragraph(
                    f'&nbsp;&nbsp;<b>Período:</b> {a["periodo"]} &nbsp;·&nbsp; '
                    f'<b>Notas em 7 dias:</b> {a["qtd_notas"]} '
                    f'({a["qtd_iguais"]} com valor igual) &nbsp;·&nbsp; '
                    f'<b>Total:</b> {brl(a["valor_total"])}', BODY))
            nfas = ", ".join(a["notas"][:9])
            if len(a["notas"]) > 9: nfas += f"...  (+{len(a['notas']) - 9})"
            story.append(Paragraph(f'&nbsp;&nbsp;<b>NFA-e:</b> {nfas}', SMALL))
            story.append(Spacer(1, 4 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("INTERPRETAÇÃO E CRUZAMENTOS RECOMENDADOS", H2))
    story.append(Paragraph(
        "<b>CRÍTICO-A</b> (3+ notas idênticas no mesmo dia) é o padrão clássico de "
        "<i>smurfing</i>: fracionamento intencional para manter cada operação "
        "abaixo de limiares de triagem fiscal (AN-01 do catálogo OrgAudi). "
        "Hipóteses: uso de 'laranja', lavagem de gado, ou simples má-fé.",
        BODY))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<b>CRÍTICO-B</b> (5+ notas/7d com valores repetidos) sugere padrão similar "
        "diluído no tempo. Pode indicar relação comercial recorrente legítima — "
        "ou camuflagem mais sofisticada.",
        BODY))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "<b>Cruzamentos obrigatórios para CADA achado:</b><br/>"
        "• GTAs AGRODEFESA-GO de TODAS as notas envolvidas<br/>"
        "• Extrato bancário do período (PIX/depósitos casados com cada NFA-e)<br/>"
        "• CAEPF do destinatário (Receita Federal — confirma status de produtor rural)<br/>"
        "• Vínculo familiar/societário contribuinte ↔ destinatário (JUCEG/RFB QSA)<br/>"
        "• Capacidade do imóvel rural do destinatário (SiCAR/CAR — descarta laranja)",
        BODY))

    # Assinatura
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("DECLARAÇÃO DE ALCANCE", H2))
    story.append(Paragraph(
        f"Análise realizada por algoritmo determinístico T-02 do skill OrgAudi 1.1 "
        f"sobre os PDFs GIEF/SEFAZ-GO emitidos em 17/04/2026 e 08/05/2026. "
        f"Não substitui análise documental primária. Os achados constituem "
        f"<i>indícios objetivos</i> que requerem cruzamento com documentação externa "
        f"antes de qualquer conclusão definitiva.",
        BODY))
    story.append(Spacer(1, 6 * mm))

    bloco = Table([
        [Paragraph("<b>Apuração por:</b>", BODY),
         Paragraph("<b>Sistema:</b> OrgAudi 1.1 · T-02", ParagraphStyle("rt", parent=BODY, alignment=TA_RIGHT))],
        [Paragraph("<b>ROBSON ALAIN VELOSO</b>", ParagraphStyle(
             "ass", parent=BODY, fontName="Helvetica-Bold", fontSize=11, textColor=AZUL)),
         Paragraph(f"<b>Emitido em:</b> {data_str}", ParagraphStyle("rt2", parent=BODY, alignment=TA_RIGHT))],
        [Paragraph("CRC TO-002032/O-5 T-GO — Ciências Contábeis", SMALL), ""],
        [Paragraph("ORGATEC AUDITORIA FISCAL SOBERANA", SMALL), ""],
    ], colWidths=[100*mm, 60*mm])
    bloco.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, CBORD),
        ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",(0, 0), (-1, -1), 3),
    ]))
    story.append(bloco)

    doc.build(story)
    print(f"[OK] PDF: {saida} ({saida.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
