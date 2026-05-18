"""Gera PDF de auditoria completo a partir do laudo JSON da ADELA.

Inclui:
- Cabecalho ORGATEC
- Identificacao do contribuinte
- Score de risco (A-07)
- F1-F6 fiscal
- DETECCAO CUSTOMIZADA (carrossel, devolucoes amplificadas, transferencia inter-CPF)
- Audit hash + assinatura
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Cores oficiais OrgAudi
CYAN = colors.HexColor("#0ea5e9")
DARK = colors.HexColor("#0f172a")
LIGHT = colors.HexColor("#f0f9ff")
RED = colors.HexColor("#dc2626")
ORANGE = colors.HexColor("#ea580c")
YELLOW = colors.HexColor("#ca8a04")


def fmt_brl(v: float) -> str:
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def cor_criticidade(nivel: str):
    return {"CRITICO": RED, "ALTA": RED, "MEDIA-ALTA": ORANGE, "MEDIA": YELLOW}.get(nivel.upper(), colors.grey)


def gerar_pdf(laudo: dict, saida: Path) -> None:
    doc = SimpleDocTemplate(
        str(saida), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Relatorio de Auditoria NFA-e - ORGATEC",
        author="OrgAudi Sovereign v8.0",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=CYAN, fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=DARK, fontSize=13, spaceBefore=10, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], textColor=DARK, fontSize=11, spaceBefore=6, spaceAfter=4)
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=8, textColor=colors.HexColor("#475569"))

    story = []

    # ── CABEÇALHO ────────────────────────────────────────────────────────────
    story.append(Paragraph("ORGATEC - Relatorio de Auditoria Fiscal NFA-e", h1))
    story.append(Paragraph(
        "<b>Sistema:</b> OrgAudi Sovereign v8.0 | "
        "<b>Pipeline:</b> RE-1 -> XGBoost -> F1-F6 -> A-07 -> Deteccao Customizada",
        small,
    ))
    story.append(Spacer(1, 10))

    # ── IDENTIFICAÇÃO ────────────────────────────────────────────────────────
    contrib = laudo.get("contribuinte", {})
    ident = [
        ["Contribuinte", contrib.get("nome", "-")],
        ["CPF/CNPJ", contrib.get("cpf", "-")],
        ["Regime", contrib.get("regime", "Produtor Rural PF")],
        ["Periodo", "01/01/2025 a 31/12/2025"],
        ["Gerado em", laudo.get("timestamp", "")[:19].replace("T", " ") + " UTC"],
        ["Result ID", laudo.get("result_id", "-")[:16] + "..."],
    ]
    t = Table(ident, colWidths=[5 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), DARK),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # ── SCORE DE RISCO ───────────────────────────────────────────────────────
    aa = laudo.get("analise_assurance", {})
    sr = laudo.get("score_risco", {})
    score = sr.get("score", 0)
    nivel = sr.get("nivel", "-")
    prob = aa.get("probabilidade_fraude", 0)
    cor_score = cor_criticidade(nivel)

    story.append(Paragraph("RESUMO EXECUTIVO", h2))
    score_tbl = Table(
        [[
            f"Score de Risco\n{score}/100",
            f"Nivel\n{nivel}",
            f"Probabilidade Fraude\n{prob * 100:.0f}%",
            f"Recomendacao\n{aa.get('recomendacao', '-')}",
        ]],
        colWidths=[4.25 * cm, 4.25 * cm, 4.25 * cm, 4.25 * cm],
    )
    score_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cor_score),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("ROWPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(score_tbl)
    story.append(Spacer(1, 14))

    # ── F1-F6 FISCAL ─────────────────────────────────────────────────────────
    rf = laudo.get("resumo_fiscal", {})
    story.append(Paragraph("APURACAO FISCAL (F1-F6)", h2))
    fiscal_rows = [
        ["Campo", "Valor", "Observacao"],
        ["F1 - Receita Imediata", fmt_brl(rf.get("f1_receita_imediata", 0)), "Vendas confirmadas"],
        ["F2 - Gado em Transito", fmt_brl(rf.get("f2_transito", 0)), "Remessas pendentes"],
        ["F3 - Receita Leilao", fmt_brl(rf.get("f3_receita_leilao", 0)), "Operacoes leilao"],
        ["F4 - Receita Bruta", fmt_brl(rf.get("f4_receita_bruta", 0)), "Base FUNRURAL/IRPF"],
        ["F5 - Resultado Rural", fmt_brl(rf.get("f5_resultado_rural", 0)), "Liquido apos F6"],
        ["F6 - Despesas Dedutiveis", fmt_brl(rf.get("f6_despesa", 0)), "Custeio/insumos"],
        ["FUNRURAL Devido", fmt_brl(rf.get("funrural", 0)), f"Aliquota {float(rf.get('aliquota_funrural', 0)) * 100:.2f}%"],
        ["IRPF Estimado", fmt_brl(rf.get("irpf_estimado", 0)), "Tabela progressiva"],
        ["Total de Notas", str(rf.get("total_notas", 0)), "NFA-e processadas"],
    ]
    t = Table(fiscal_rows, colWidths=[6 * cm, 5 * cm, 6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CYAN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWPADDING", (0, 0), (-1, -1), 5),
        ("FONTNAME", (0, 7), (-1, 8), "Helvetica-Bold"),  # FUNRURAL e IRPF em negrito
        ("BACKGROUND", (0, 7), (-1, 8), colors.HexColor("#fef3c7")),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # ── A-07 (PIPELINE) ──────────────────────────────────────────────────────
    story.append(Paragraph("ANALISE FORENSE A-07 (Pipeline OrgAudi)", h2))
    padroes = aa.get("padroes_detectados", [])
    a07_rows = [
        ["Score A-07", f"{aa.get('score_risco', 0)}"],
        ["Probabilidade Fraude", f"{aa.get('probabilidade_fraude', 0) * 100:.0f}%"],
        ["Criticidade", aa.get("criticidade", "-")],
        ["Recomendacao", aa.get("recomendacao", "-")],
        ["Confianca", f"{aa.get('confianca', 0) * 100:.0f}%"],
        ["Padroes Detectados", ", ".join(padroes) if padroes else "(nenhum)"],
        ["Modo XGBoost", sr.get("modo", "-")],
    ]
    t = Table(a07_rows, colWidths=[6 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), DARK),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # SHAP features (top 5)
    shap = sr.get("shap_values", {})
    if shap:
        story.append(Paragraph("Features XGBoost (SHAP - top 5)", h3))
        shap_sorted = sorted(shap.items(), key=lambda x: -abs(x[1]))[:5]
        features_rows = [["Feature", "Peso SHAP"]]
        for k, v in shap_sorted:
            features_rows.append([k, f"{v:.2f}"])
        t = Table(features_rows, colWidths=[10 * cm, 3 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), CYAN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
    story.append(PageBreak())

    # ── DETECÇÃO CUSTOMIZADA ─────────────────────────────────────────────────
    custom = laudo.get("deteccao_customizada", {})
    alertas = custom.get("alertas", [])

    story.append(Paragraph(f"DETECCAO CUSTOMIZADA - {len(alertas)} ALERTAS", h2))
    story.append(Paragraph(
        "Detectores complementares aos do pipeline padrao A-07, focados em padroes especificos "
        "de fraude rural detectados pela analise manual + cruzamento de dados.",
        small,
    ))
    story.append(Spacer(1, 10))

    # Agrupar por tipo
    for i, alerta in enumerate(alertas, 1):
        tipo = alerta.get("tipo", "?")
        crit = alerta.get("criticidade", "-")
        evid = alerta.get("evidencia", "-")
        cor = cor_criticidade(crit)

        # Cabecalho do alerta
        story.append(Paragraph(f"<b>Alerta #{i} - {tipo}</b> [{crit}]", h3))

        # Tabela de detalhes
        details = [["Campo", "Valor"]]
        for k, v in alerta.items():
            if k in ("tipo", "criticidade", "evidencia"):
                continue
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            details.append([k.replace("_", " ").title(), str(v)])

        t = Table(details, colWidths=[5 * cm, 12 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), cor),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("ROWPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)

        # Evidencia
        story.append(Paragraph(f"<b>Evidencia:</b> {evid}", small))
        story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ── RECOMENDAÇÕES FINAIS ─────────────────────────────────────────────────
    story.append(Paragraph("RECOMENDACOES FINAIS", h2))

    recoms = [
        "1. <b>AUDITORIA URGENTE</b>: Score 66.9 + Nivel ALTO + 9 alertas customizados exigem fiscalizacao prioritaria.",
        "2. <b>Foco em ADMILSON ROMEIRO</b> (CPF 604.849.181-68): 3 alertas envolvendo este CPF "
        "(carrossel ida-e-volta + 2 devolucoes amplificadas).",
        "3. <b>Reclassificar NFA 25510606</b> de TRANSFERENCIA para VENDA - CPFs distintos invalidam a natureza declarada.",
        "4. <b>Verificar dupla inscricao estadual</b> de ANDRE FERNANDES (CPF 104.956.191-08): "
        "IE 115732616 como remetente e IE 115771433 como destinatario.",
        "5. <b>Cruzar dados na SEFAZ-GO</b>: verificar GTAs (Guias de Transporte Animal) "
        "para confirmar deslocamento fisico do gado nas operacoes 25813736/25813404 (mesmo dia).",
        "6. <b>FUNRURAL devido</b> de R$ 20.621,95 deve ser cobrado independente da auditoria forense.",
    ]
    for r in recoms:
        story.append(Paragraph(r, normal))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 16))

    # ── ASSINATURA / AUDITORIA ───────────────────────────────────────────────
    story.append(Paragraph("RASTREABILIDADE", h2))
    story.append(Paragraph(
        f"<b>Audit Hash:</b> <font face='Courier' size='8'>{laudo.get('audit_hash', '-')}</font>",
        normal,
    ))
    story.append(Paragraph(
        f"<b>Hash type:</b> SHA-256 do payload completo + timestamp UTC",
        small,
    ))
    story.append(Paragraph(
        f"<b>Result ID:</b> <font face='Courier' size='8'>{laudo.get('result_id', '-')}</font>",
        normal,
    ))
    story.append(Paragraph(
        f"<b>Sistema:</b> OrgAudi Sovereign v8.0 | "
        f"<b>Pipeline:</b> Anthropic Claude + XGBoost + Detectores Determinísticos",
        small,
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<i>Este documento foi gerado automaticamente pelo motor de auditoria OrgAudi e contem dados "
        "anonimizados via Protocolo @Delta antes de qualquer interacao com LLM. "
        "Reproducao restrita a fins fiscais oficiais.</i>",
        small,
    ))

    doc.build(story)


def main():
    # Pega o laudo v2 mais recente
    laudos = sorted(Path("reports_nfa").glob("laudo_adela_v2_*.json"))
    if not laudos:
        print("Nenhum laudo encontrado. Execute 'python scripts/auditoria_adela.py' primeiro.")
        return

    laudo_path = laudos[-1]
    print(f"Lendo: {laudo_path}")
    laudo = json.loads(laudo_path.read_text(encoding="utf-8"))

    pdf_path = laudo_path.with_suffix(".pdf")
    gerar_pdf(laudo, pdf_path)
    print(f"PDF gerado: {pdf_path}")
    print(f"Tamanho: {pdf_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
