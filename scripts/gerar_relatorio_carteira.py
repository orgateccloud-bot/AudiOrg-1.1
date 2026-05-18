"""scripts/gerar_relatorio_carteira.py

Gera um PDF consolidado da carteira: síntese executiva dos 26 clientes
auditados. Útil para o auditor ter visão agregada antes de mergulhar em
cada laudo individual.

Saída: reports_nfa/RELATORIO_CARTEIRA_<YYYY-MM-DD>.pdf
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage, KeepTogether, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from pdf_engine.orgaudi_v240.styles import AZUL, AZUL_M, BRANCO, CTXT, CTXT_DARK, CBORD

OUTPUTS = RAIZ / "outputs"
DEST_DIR = RAIZ / "reports_nfa"
DEST_DIR.mkdir(parents=True, exist_ok=True)
LOGO_PATH = RAIZ / "pdf_engine" / "orgaudi_v240" / "assets" / "logo_orgatec.png"

CRITICO = HexColor("#D63333")
ALTO    = HexColor("#E68A00")
CONFORME = HexColor("#1F8B4C")
CINZA_F = HexColor("#F5F7FA")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                     fontSize=18, textColor=AZUL, alignment=TA_CENTER, leading=22)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                     fontSize=13, textColor=AZUL, alignment=TA_LEFT, leading=16,
                     spaceBefore=8, spaceAfter=6)
SUB = ParagraphStyle("Sub", parent=styles["Normal"], fontName="Helvetica-Oblique",
                      fontSize=9, textColor=CTXT, alignment=TA_CENTER, leading=11)
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontName="Helvetica",
                       fontSize=9, textColor=CTXT_DARK, alignment=TA_LEFT, leading=12)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontName="Helvetica",
                        fontSize=7.5, textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)


def brl(v) -> str:
    try:
        d = Decimal(str(v or 0))
    except Exception:
        return "—"
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def carregar_clientes() -> list[dict]:
    """Lê todos os auditoria_v2.json e retorna lista de dicts simplificados."""
    out = []
    for path in sorted(OUTPUTS.glob("*/auditoria_v2.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        nome = d["contribuinte"]["nome"]
        cpf = d["contribuinte"].get("cpf", "")
        cpf_dig = "".join(c for c in cpf if c.isdigit())
        cat = "PJ" if len(cpf_dig) == 14 else "PF"
        ip = d.get("indicadores_principais", {})
        sev = d.get("severidades", {})
        p = d.get("planilha_gado_ir", {}).get("totais", {})
        out.append({
            "slug": path.parent.name,
            "nome": nome,
            "cpf": cpf,
            "uf": d["contribuinte"].get("estado", "GO"),
            "cat": cat,
            "volume": Decimal(ip.get("VOLUME_BRUTO", {}).get("valor", "0")),
            "f6": Decimal(ip.get("F6_COMPRAS", {}).get("valor", "0")),
            "f5": Decimal(ip.get("F5_RESULTADO_RURAL", {}).get("valor", "0")),
            "irpf": Decimal(ip.get("IRPF_ESTIMADO", {}).get("valor", "0")),
            "funrural": Decimal(ip.get("FUNRURAL", {}).get("valor", "0")),
            "qv": p.get("vendas", {}).get("qtd_notas", 0),
            "qr": p.get("remessas", {}).get("qtd_notas", 0),
            "qc": p.get("compras", {}).get("qtd_notas", 0),
            "cri": sev.get("CRITICO", 0),
            "alt": sev.get("ALTO", 0),
            "med": sev.get("MEDIO", 0),
            "ate": sev.get("ATENCAO", 0),
            "audit_hash": d.get("audit_hash", ""),
        })
    return out


def construir_capa(clientes: list[dict]) -> list:
    """Página 1: capa + totais agregados."""
    total_volume = sum((c["volume"] for c in clientes), Decimal(0))
    total_compras = sum((c["f6"] for c in clientes), Decimal(0))
    total_resultado = total_volume - total_compras
    total_irpf = sum((c["irpf"] for c in clientes), Decimal(0))
    total_funrural = sum((c["funrural"] for c in clientes), Decimal(0))
    total_cri = sum(c["cri"] for c in clientes)
    total_alt = sum(c["alt"] for c in clientes)
    total_med = sum(c["med"] for c in clientes)
    total_ate = sum(c["ate"] for c in clientes)

    elems = []
    if LOGO_PATH.exists():
        elems.append(Spacer(1, 6 * mm))
        elems.append(Table(
            [[RLImage(str(LOGO_PATH), width=32 * mm, height=32 * mm,
                       kind="proportional", mask="auto")]],
            colWidths=[170 * mm],
            style=TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")])))
    elems.append(Spacer(1, 4 * mm))
    elems.append(Paragraph("<b>ORGATEC</b>", ParagraphStyle(
        "logo", fontName="Helvetica-Bold", fontSize=16, textColor=AZUL,
        alignment=TA_CENTER, leading=20)))
    elems.append(Paragraph("CONTABILIDADE E AUDITORIA", ParagraphStyle(
        "logo2", fontName="Helvetica-Bold", fontSize=9, textColor=AZUL,
        alignment=TA_CENTER, leading=12)))
    elems.append(Spacer(1, 8 * mm))
    elems.append(Paragraph("RELATÓRIO CONSOLIDADO DA CARTEIRA", H1))
    elems.append(Paragraph(
        f"<i>Período auditado: 01/01/2025 a 31/12/2025 · "
        f"{len(clientes)} contribuintes</i>", SUB))
    elems.append(Spacer(1, 6 * mm))

    # Tabela de totais agregados
    elems.append(Paragraph("TOTAIS AGREGADOS", H2))
    rows = [
        ["INDICADOR", "VALOR"],
        ["Volume bruto saídas (consolidado)", brl(total_volume)],
        ["Compras / F6 (consolidado)", brl(total_compras)],
        ["Resultado rural líquido (saídas − compras)", brl(total_resultado)],
        ["IRPF estimado (Σ 20% × F5)", brl(total_irpf)],
        ["Funrural estimado (consolidado)", brl(total_funrural)],
    ]
    tbl = Table(rows, colWidths=[110 * mm, 50 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("ALIGN",       (1, 0), (1, -1), "RIGHT"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",        (0, 0), (-1, -1), 0.3, CBORD),
        ("BACKGROUND",  (0, 1), (-1, -1), CINZA_F),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 8 * mm))

    # Cards de severidade
    elems.append(Paragraph("MAPA DE ACHADOS POR SEVERIDADE", H2))
    sev_rows = [
        ["CRÍTICO",  str(total_cri), "Detectados em achados manuais (smurfing, concentração singular)"],
        ["ALTO",     str(total_alt), "Concentração PFs, perfil de revenda atípica"],
        ["MÉDIO",    str(total_med), "Obrigações acessórias (LCDPR, Funrural) — quase universal"],
        ["ATENÇÃO",  str(total_ate), "Compras relevantes (AT-01), devoluções (AT-02)"],
    ]
    cores = {0: CRITICO, 1: ALTO, 2: AZUL_M, 3: AZUL}
    cabecalho = [["SEVERIDADE", "QTD", "PRINCIPAIS GATILHOS"]]
    tbl2 = Table(cabecalho + sev_rows, colWidths=[30 * mm, 18 * mm, 112 * mm])
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",  (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ALIGN",      (0, 0), (0, -1), "CENTER"),
        ("ALIGN",      (1, 0), (1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",       (0, 0), (-1, -1), 0.3, CBORD),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, _ in enumerate(sev_rows):
        estilo.append(("BACKGROUND", (0, i + 1), (0, i + 1), cores.get(i, AZUL)))
        estilo.append(("TEXTCOLOR",  (0, i + 1), (0, i + 1), BRANCO))
        estilo.append(("FONTNAME",   (0, i + 1), (0, i + 1), "Helvetica-Bold"))
    tbl2.setStyle(TableStyle(estilo))
    elems.append(tbl2)

    return elems


def construir_tabela_clientes(clientes: list[dict]) -> list:
    """Página 2: tabela com os 26 clientes (compacta)."""
    elems = [Paragraph("CARTEIRA DETALHADA", H1), Spacer(1, 4 * mm)]
    cab = [
        Paragraph("<b>#</b>", BODY),
        Paragraph("<b>CONTRIBUINTE</b>", BODY),
        Paragraph("<b>UF</b>", BODY),
        Paragraph("<b>VOLUME</b>", BODY),
        Paragraph("<b>COMPRAS</b>", BODY),
        Paragraph("<b>F5 RESULT.</b>", BODY),
        Paragraph("<b>V/R/C</b>", BODY),
        Paragraph("<b>ACHADOS</b>", BODY),
    ]
    rows = [cab]
    for i, c in enumerate(clientes, 1):
        f5_color = CRITICO if c["f5"] < 0 else CONFORME
        f5_str = f'<font color="#{f5_color.hexval()[2:]}">{brl(c["f5"])}</font>'
        achados = f'C:{c["cri"]} A:{c["alt"]} M:{c["med"]} At:{c["ate"]}'
        rows.append([
            Paragraph(str(i), SMALL),
            Paragraph(c["nome"][:38], SMALL),
            Paragraph(c["uf"], SMALL),
            Paragraph(brl(c["volume"]), ParagraphStyle("rA", parent=SMALL, alignment=TA_RIGHT)),
            Paragraph(brl(c["f6"]), ParagraphStyle("rB", parent=SMALL, alignment=TA_RIGHT)),
            Paragraph(f5_str, ParagraphStyle("rC", parent=SMALL, alignment=TA_RIGHT)),
            Paragraph(f"{c['qv']}/{c['qr']}/{c['qc']}", SMALL),
            Paragraph(achados, SMALL),
        ])
    tbl = Table(rows, colWidths=[8 * mm, 56 * mm, 8 * mm, 28 * mm, 28 * mm,
                                  26 * mm, 14 * mm, 22 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",        (0, 0), (-1, -1), 0.3, CBORD),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA_F]),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elems.append(tbl)
    return elems


def construir_bandeiras_vermelhas(clientes: list[dict]) -> list:
    """Página 3: bandeiras vermelhas + concentração."""
    elems = [Paragraph("BANDEIRAS VERMELHAS DETECTADAS", H1), Spacer(1, 4 * mm)]

    # 1) F5 negativo
    neg = [c for c in clientes if c["f5"] < 0]
    neg.sort(key=lambda x: x["f5"])
    elems.append(Paragraph(
        f"<b>1. Resultado rural NEGATIVO (compras &gt; saídas) — {len(neg)} clientes</b>", H2))
    elems.append(Paragraph(
        "F5 negativo não é ilegal, mas anula o IRPF Rural do exercício e pode "
        "indicar AN-08 (transferência intrafamiliar disfarçada), AN-14 (ciclo "
        "operacional implausível) ou AN-18 (caixa dois agropecuário) quando "
        "compras superam saídas sem comprovação de plantel em formação.",
        BODY))
    elems.append(Spacer(1, 3 * mm))
    rows = [["#", "CONTRIBUINTE", "VOLUME", "COMPRAS", "F5 NEGATIVO"]]
    for i, c in enumerate(neg, 1):
        rows.append([
            str(i), c["nome"][:40], brl(c["volume"]), brl(c["f6"]), brl(c["f5"]),
        ])
    tbl = Table(rows, colWidths=[8 * mm, 70 * mm, 30 * mm, 30 * mm, 32 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("ALIGN",       (2, 0), (-1, -1), "RIGHT"),
        ("TEXTCOLOR",   (4, 1), (4, -1), CRITICO),
        ("FONTNAME",    (4, 1), (4, -1), "Helvetica-Bold"),
        ("GRID",        (0, 0), (-1, -1), 0.3, CBORD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA_F]),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 6 * mm))

    # 2) Concentração TOP 3
    top3 = sorted(clientes, key=lambda c: c["volume"], reverse=True)[:3]
    total_top3 = sum(c["volume"] for c in top3)
    total_geral = sum((c["volume"] for c in clientes), Decimal(0))
    pct = (total_top3 / total_geral * 100) if total_geral else 0
    elems.append(Paragraph(
        f"<b>2. Concentração em 3 clientes = {pct:.1f}% do volume total</b>", H2))
    elems.append(Paragraph(
        f"Apenas 3 dos {len(clientes)} contribuintes ({100*3/len(clientes):.0f}% da "
        f"carteira) concentram <b>{brl(total_top3)}</b>. Auditoria documental "
        "prioritária deveria focar nesses 3 — qualquer divergência neles tem "
        "impacto fiscal desproporcional sobre a carteira.",
        BODY))
    elems.append(Spacer(1, 3 * mm))
    rows2 = [["#", "CONTRIBUINTE", "UF", "VOLUME", "% TOTAL"]]
    for i, c in enumerate(top3, 1):
        pct_c = (c["volume"] / total_geral * 100) if total_geral else 0
        rows2.append([str(i), c["nome"][:45], c["uf"], brl(c["volume"]),
                       f"{pct_c:.1f}%"])
    tbl2 = Table(rows2, colWidths=[8 * mm, 70 * mm, 12 * mm, 40 * mm, 20 * mm])
    tbl2.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR",   (0, 0), (-1, 0), BRANCO),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("ALIGN",       (3, 0), (-1, -1), "RIGHT"),
        ("GRID",        (0, 0), (-1, -1), 0.3, CBORD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CINZA_F]),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elems.append(tbl2)
    elems.append(Spacer(1, 6 * mm))

    # 3) Clientes vazios + duplicação
    vazios = [c for c in clientes if c["volume"] == 0 and c["f6"] == 0]
    if vazios:
        elems.append(Paragraph(
            f"<b>3. Clientes sem operações ({len(vazios)})</b>", H2))
        for c in vazios:
            elems.append(Paragraph(
                f"• <b>{c['nome']}</b> (CPF {c['cpf']}) — sem notas no período. "
                "Confirmar se cadastro está ativo no exercício 2025.", BODY))
        elems.append(Spacer(1, 3 * mm))

    # Detecta duplicação por CPF
    por_cpf = {}
    for c in clientes:
        por_cpf.setdefault(c["cpf"], []).append(c)
    duplicados = {cpf: cs for cpf, cs in por_cpf.items() if len(cs) > 1}
    if duplicados:
        elems.append(Paragraph(
            f"<b>4. Duplicações de cadastro ({len(duplicados)})</b>", H2))
        for cpf, cs in duplicados.items():
            slugs = ", ".join(c["slug"] for c in cs)
            elems.append(Paragraph(
                f"• CPF {cpf}: {slugs} — mesmo contribuinte com 2+ entradas. Remover redundância.",
                BODY))

    return elems


def construir_recomendacoes_e_assinatura(clientes: list[dict]) -> list:
    """Página 4: plano de ação + assinatura."""
    elems = [Paragraph("PLANO DE AÇÃO PRIORIZADO", H1), Spacer(1, 4 * mm)]

    elems.append(Paragraph("<b>FASE 1 — 30 DIAS (auditoria documental dos 3 maiores)</b>", H2))
    elems.append(Paragraph(
        "Concentrar levantamento de evidências em DEUSDETE, GEAN e HELIO JOSE. "
        "Solicitar: GTAs AGRODEFESA-GO de TODAS as notas; extratos bancários do "
        "exercício; ACTs dos leiloeiros (se aplicável); LCDPR completo; "
        "lançamentos contábeis 1.1.2.01 (Gado em Rebanho) × 2.1.1.1.01 (Fornecedores).",
        BODY))
    elems.append(Spacer(1, 4 * mm))

    elems.append(Paragraph("<b>FASE 2 — 60 DIAS (investigar F5 negativo extremo)</b>", H2))
    elems.append(Paragraph(
        "Aprofundar análise nos clientes com compras 2× maiores que saídas (FABIO, "
        "JOSMAIR, DEUSDETE): risco de AN-08/AN-14/AN-18. Cruzar GTAs com bancário "
        "para descartar caixa dois agropecuário. Verificar CAEPF de fornecedores e "
        "vínculos via JUCEG/RFB.",
        BODY))
    elems.append(Spacer(1, 4 * mm))

    elems.append(Paragraph("<b>FASE 3 — 90 DIAS (conformidade tributária da carteira)</b>", H2))
    elems.append(Paragraph(
        "Reconstituir LCDPR de TODOS os clientes (44 achados MEDIO M-01). Apurar "
        "IRPF Rural por contribuinte. Conferir Funrural recolhido contra estimativa "
        "(R$ 850.998,25 consolidado). Adequar emissão de NFA-e/NF-e à Reforma "
        "Tributária (LC 214/2025, CBS/IBS a partir 2027).",
        BODY))
    elems.append(Spacer(1, 8 * mm))

    # Assinatura
    elems.append(Paragraph("DECLARAÇÃO DE ALCANCE", H2))
    elems.append(Paragraph(
        "Este relatório consolida os 26 laudos individuais emitidos em "
        f"{datetime.now().strftime('%d/%m/%Y')} pelo sistema OrgAudi 1.1. "
        "Não substitui a leitura dos laudos individuais para tomada de decisão "
        "específica por contribuinte. Os achados constituem indícios objetivos; "
        "a confirmação depende de etapa subsequente de coleta de evidências "
        "primárias (extratos, GTAs, ACTs). Eventual regularização espontânea "
        "pelo art. 138 do CTN preserva o contribuinte de autuação.",
        BODY))
    elems.append(Spacer(1, 6 * mm))

    # Bloco final assinatura
    h = hashlib.sha256()
    h.update(f"carteira|{len(clientes)}|{datetime.now(timezone.utc).date()}".encode())
    h.update("|".join(c["audit_hash"] for c in clientes).encode())
    carteira_hash = h.hexdigest()

    bloco = Table([
        [Paragraph("<b>Apuração realizada por:</b>", BODY),
         Paragraph(f"<b>Sistema:</b> OrgAudi 1.1", ParagraphStyle(
             "rt", parent=BODY, alignment=TA_RIGHT))],
        [Paragraph("<b>ROBSON ALAIN VELOSO</b>", ParagraphStyle(
             "ass", parent=BODY, fontName="Helvetica-Bold", fontSize=11,
             textColor=AZUL)),
         Paragraph(f"<b>Emitido em:</b> {datetime.now().strftime('%Y-%m-%d')}",
                    ParagraphStyle("rt2", parent=BODY, alignment=TA_RIGHT))],
        [Paragraph("CRC TO-002032/O-5 T-GO — Ciências Contábeis", SMALL),
         Paragraph(f"<b>Carteira hash:</b> {carteira_hash[:32]}…",
                    ParagraphStyle("rt3", parent=SMALL, alignment=TA_RIGHT))],
        [Paragraph("ORGATEC AUDITORIA FISCAL SOBERANA", SMALL), ""],
    ], colWidths=[100 * mm, 60 * mm])
    bloco.setStyle(TableStyle([
        ("LINEABOVE",  (0, 0), (-1, 0), 0.5, CBORD),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    elems.append(bloco)

    return elems, carteira_hash


def main() -> None:
    clientes = carregar_clientes()
    # Filtra duplicação GENIS (mesmo CPF)
    visto = set()
    unicos = []
    for c in clientes:
        if c["cpf"] not in visto:
            unicos.append(c)
            visto.add(c["cpf"])
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"[INFO] {len(clientes)} JSONs encontrados -> {len(unicos)} contribuintes unicos")

    data_str = datetime.now().strftime("%Y-%m-%d")
    saida = DEST_DIR / f"RELATORIO_CARTEIRA_{data_str}.pdf"

    doc = SimpleDocTemplate(
        str(saida), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Relatório Consolidado da Carteira — {data_str}",
        author="ORGATEC AUDITORIA FISCAL SOBERANA",
    )

    story = []
    story += construir_capa(unicos)
    story += [PageBreak()]
    story += construir_tabela_clientes(unicos)
    story += [PageBreak()]
    story += construir_bandeiras_vermelhas(unicos)
    story += [PageBreak()]
    final, h = construir_recomendacoes_e_assinatura(unicos)
    story += final

    doc.build(story)
    print(f"[OK] PDF gerado: {saida}")
    print(f"     Tamanho:   {saida.stat().st_size:,} bytes")
    print(f"     Carteira hash: {h}")


if __name__ == "__main__":
    main()
