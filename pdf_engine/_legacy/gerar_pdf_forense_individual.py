"""scripts/gerar_pdf_forense_individual.py

Gera um PDF individual por cliente com a bateria forense ENDURECIDA
completa (T-01..T-08 + AN-02..AN-17), aplicando as **regras visuais
institucionais ORGATEC** do pdf_engine/orgaudi_v240:

  • Banda dourada superior + cabeçalho azul ORGATEC com logo
  • Paleta institucional (AZUL, OURO, severidades)
  • section_header / achado_header / sev_card / risk_strip / kpi_row / info_box
  • Rodapé com créditos e linha dourada
  • Paginação "Página X de Y"

Consome JSONs:
  • reports_nfa/ANALISE_FORENSE_HARD_<data>.json
  • reports_nfa/ANOMALIAS_AN18_<data>.json

Saída:
  reports_nfa/forense_individual/LAUDO_FORENSE_<slug>_<data>.pdf
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak, PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle, Spacer,
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Importa engine institucional
from pdf_engine.orgaudi.styles import (
    AZUL, AZUL_M, AZUL_CL, AZUL_DEEP, OURO, OURO_BG, BRANCO,
    CBG, CBG_LIGHT, CBORD, CTXT, CTXT_DARK,
    CRITICO, CRITICO_BG, CRITICO_BORD,
    ALTO, ALTO_BG, ALTO_BORD,
    MEDIO, MEDIO_BG, MEDIO_BORD,
    ATENCAO, ATENCAO_BG, ATENCAO_BORD,
    CONFORME, CONFORME_BG, CONFORME_BORD,
    PH, PW, W, S, ST,
    achado_header, divider_section, hr, info_box, kpi_card, kpi_row,
    risk_strip, section_header, sev_card, sp, td, tfoot, th, tsb,
)
from pdf_engine.orgaudi.domain import Severidade
from pdf_engine.orgaudi.handlers import criar_handler_pagina

DEST = RAIZ / "reports_nfa" / "forense_individual"
DEST.mkdir(parents=True, exist_ok=True)
DATA = datetime.now().strftime("%Y-%m-%d")
ARQ_HARD = RAIZ / "reports_nfa" / f"ANALISE_FORENSE_HARD_{DATA}.json"
ARQ_AN18 = RAIZ / "reports_nfa" / f"ANOMALIAS_AN18_{DATA}.json"


# ── Helpers ──────────────────────────────────────────────────────────────

def fmt_brl(v) -> str:
    if v is None: return "—"
    if isinstance(v, str):
        try: v = Decimal(v)
        except Exception: return v
    if isinstance(v, (int, float)): v = Decimal(str(v))
    s = f"{Decimal(str(v)):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _contar_tipos(lista):
    from collections import Counter
    return dict(Counter(a["tipo"] for a in lista))


# ── Capa institucional ───────────────────────────────────────────────────

def construir_capa(fh, fan, cascatas):
    """Capa v2.4.1: título + identificação + risk_strip + sev_card + KPIs."""
    nome = fan.get("contribuinte_nome", fh.get("slug"))
    cpf = fan.get("contribuinte_cpf", "—") or "—"
    qtd_notas = fh.get("qtd_notas", 0)

    story = []
    # Logo grande ocupa o topo via handler — abrir com espaço
    story.append(sp(34))

    story.append(Paragraph("LAUDO FORENSE ENDURECIDO", ST["h1"]))
    story.append(Paragraph("Bateria T-01..T-08 + Catálogo AN-01..AN-18",
                            ST["kicker"]))
    story.append(Paragraph(
        "Pipeline OrgAudi 1.1 — Detectores determinísticos sobre GIEF SEFAZ-GO",
        ST["sub"]))
    story.append(sp(2))

    # Tabela de identificação
    ident = Table([
        [td("Contribuinte", bold=True, color=AZUL), td(nome, bold=True)],
        [td("CPF/CNPJ", bold=True, color=AZUL), td(cpf)],
        [td("Período", bold=True, color=AZUL), td("01/01/2025 a 31/12/2025")],
        [td("Documento base", bold=True, color=AZUL),
          td("PDF GIEF SEFAZ-GO (REM + DEST)")],
        [td("Notas analisadas", bold=True, color=AZUL),
          td(str(qtd_notas), bold=True)],
        [td("Sistema", bold=True, color=AZUL),
          td("OrgAudi 1.1 — Pipeline Forense Determinístico")],
        [td("Emitido em", bold=True, color=AZUL),
          td(datetime.now().strftime("%d/%m/%Y às %H:%M"))],
    ], colWidths=[40 * mm, W - 40 * mm])
    ident.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CBG_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.3, CBORD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ident)
    story.append(sp(4))

    # Calcula nível de risco
    t01_c = len([a for a in fh.get("t01", []) if a["tipo"] == "CRITICO"])
    t02_c = len(fh.get("t02", []))
    t03_c = len([a for a in (fh.get("t03") or {}).get("achados", [])
                  if a.get("tipo") == "CRITICO"])
    t04_c = 1 if (fh.get("t04") or {}).get("tipo") == "CRITICO" else 0
    an02_c = len([a for a in fan.get("an02", []) if a["tipo"] == "CRITICO"])
    an03_c = len([a for a in fan.get("an03", []) if a["tipo"] == "CRITICO"])
    an08_c = len([a for a in fan.get("an08", []) if a["tipo"] == "CRITICO"])
    an11_c = len([a for a in fan.get("an11", []) if a["tipo"] == "CRITICO"])
    qtd_critico = t01_c + t02_c + t03_c + t04_c + an02_c + an03_c + an08_c + an11_c
    qtd_cascata = len(cascatas)

    if qtd_critico >= 5 or qtd_cascata >= 3:
        nivel = ("CRÍTICO", CRITICO)
    elif qtd_critico >= 2 or qtd_cascata >= 1:
        nivel = ("ALTO", ALTO)
    elif qtd_critico >= 1:
        nivel = ("ATENÇÃO", ATENCAO)
    else:
        nivel = ("CONFORME", CONFORME)

    story.append(risk_strip(
        f"{nivel[0]} — {qtd_critico} achado(s) crítico(s)",
        nivel[1],
        f"AN-17 cascata: {qtd_cascata}",
    ))
    story.append(sp(4))

    # Mapa de severidades — sev_card por bloco
    story.append(section_header("MAPA DE ACHADOS — TESTES + ANOMALIAS",
                                  accent_color=AZUL))
    story.append(sp(2))

    # Conta achados
    t01_at = len([a for a in fh.get("t01", []) if a["tipo"] == "ATENCAO"])
    an02_at = len([a for a in fan.get("an02", []) if a["tipo"] == "ATENCAO"])
    an03_at = len([a for a in fan.get("an03", []) if a["tipo"] == "ATENCAO"])
    an08_at = len([a for a in fan.get("an08", []) if a["tipo"] == "ATENCAO"])
    an11_at = len([a for a in fan.get("an11", []) if a["tipo"] == "ATENCAO"])
    qtd_atencao = t01_at + an02_at + an03_at + an08_at + an11_at + len(fan.get("an14", []))

    if qtd_critico:
        story.append(sev_card("CRÍTICO", qtd_critico,
            "Anomalias com impacto fiscal direto exigindo ação imediata.",
            Severidade.CRITICO))
        story.append(sp(1.5))
    if qtd_cascata:
        story.append(sev_card("ALTO", qtd_cascata,
            f"Cadeias AN-17 (cascata A→B→C) onde este cliente atua como origem.",
            Severidade.ALTO))
        story.append(sp(1.5))
    if qtd_atencao:
        story.append(sev_card("ATENÇÃO", qtd_atencao,
            "Sinais que demandam confirmação documental ou cruzamento externo.",
            Severidade.ATENCAO))
        story.append(sp(1.5))
    if not (qtd_critico or qtd_cascata or qtd_atencao):
        story.append(sev_card("CONFORME", 0,
            "Nenhum achado nas regras endurecidas — exposição forense baixa.",
            Severidade.CONFORME))

    return story


# ── KPIs por teste ───────────────────────────────────────────────────────

def construir_kpis(fh, fan):
    """Linha de 4 KPIs sintetizando T-01, T-02, T-03, AN-14."""
    t01_total = len(fh.get("t01") or [])
    t02_total = len(fh.get("t02") or [])
    t03_top1 = 0
    t03_pct = 0.0
    for a in (fh.get("t03") or {}).get("achados", []):
        if a.get("subtipo") == "TOP1":
            t03_top1 = 1
            t03_pct = a.get("pct", 0)
    t04 = fh.get("t04") or {}
    an14 = len(fan.get("an14", []))

    story = [
        sp(4),
        kpi_row([
            ("T-01 NOTA", str(t01_total), "concentração", AZUL),
            ("T-02 SMURF", str(t02_total), "fragmentação", CRITICO),
            ("T-03 TOP1", f"{t03_pct:.0f}%" if t03_top1 else "—",
                "contraparte", ALTO),
            ("AN-14 CICLO", str(an14), "compra<60d→venda", ATENCAO),
        ], accent_colors=[AZUL, CRITICO, ALTO, ATENCAO]),
        sp(4),
    ]
    return story


# ── Seções de detalhe ────────────────────────────────────────────────────

def secao_t01(fh):
    achados = fh.get("t01") or []
    if not achados: return []
    crits = [a for a in achados if a["tipo"] == "CRITICO"]
    ates = [a for a in achados if a["tipo"] == "ATENCAO"]

    story = [CondPageBreak(8 * mm)]
    story.append(achado_header("T-01",
        "Concentração de Nota Individual — Eixo IV (AN-13)",
        Severidade.CRITICO if crits else Severidade.ATENCAO))
    story.append(sp(2))
    story.append(info_box(
        "<b>Critério endurecido:</b> CRÍTICO se nota individual ≥ 7% da receita "
        "anual; ATENÇÃO se 3-7%. Concentração atípica em evento único é bandeira "
        "de AN-13 e indício de AN-18 (caixa dois) quando associada a contraparte "
        "recorrente.",
        label="Regra aplicada", border_color=AZUL_M))
    story.append(sp(2))

    if crits:
        story.append(Paragraph(
            f"<b>CRÍTICOS — {len(crits)} nota(s) ≥ 7% da receita</b>",
            ST["subsec"]))
        linhas = [[th("NFA"), th("Data"), th("% Rec.", align=TA_RIGHT),
                    th("Valor", align=TA_RIGHT), th("Destinatário")]]
        for a in crits[:18]:
            linhas.append([
                td(a["nfa"]), td(a["data"]),
                td(f"{a['pct']:.2f}%", align=TA_RIGHT, bold=True, color=CRITICO),
                td(fmt_brl(a["valor"]), align=TA_RIGHT),
                td(a["destinatario"][:38]),
            ])
        t = Table(linhas, colWidths=[20*mm, 20*mm, 18*mm, 30*mm, W-88*mm], repeatRows=1)
        t.setStyle(tsb())
        story.append(t)
        story.append(sp(2))
    if ates:
        story.append(info_box(
            f"<b>ATENÇÃO — {len(ates)} nota(s) entre 3% e 7%.</b> "
            "Anexar evidência documental para confirmar legitimidade comercial.",
            border_color=ATENCAO, bg=ATENCAO_BG))
    return story


def secao_t02(fh):
    achados = fh.get("t02") or []
    if not achados: return []
    story = [CondPageBreak(8 * mm)]
    story.append(achado_header("T-02",
        "Smurfing / Fragmentação Fiscal — Eixo I (AN-01)",
        Severidade.CRITICO))
    story.append(sp(2))
    cnt = _contar_tipos(achados)
    subs = ", ".join(f"<b>{k.replace('CRITICO_','')}</b>={v}" for k, v in cnt.items())
    story.append(info_box(
        f"<b>Critérios (4 subtipos):</b> "
        f"<b>A)</b> 3+ notas idênticas mesmo dia &nbsp;|&nbsp; "
        f"<b>B)</b> 4+ notas em 7d com 2+ valores iguais &nbsp;|&nbsp; "
        f"<b>C)</b> 2+ notas mesma data + mesma contraparte &nbsp;|&nbsp; "
        f"<b>D)</b> 3+ notas mesma contraparte em 30d, soma ≥ R$ 100k.<br/>"
        f"<b>Distribuição:</b> {subs}",
        label="Regra aplicada", border_color=CRITICO))
    story.append(sp(2))

    linhas = [[th("Sub"), th("Destinatário"), th("CPF"),
                th("Qtd", align=TA_RIGHT), th("Valor", align=TA_RIGHT)]]
    for a in achados[:25]:
        linhas.append([
            td(a["tipo"].replace("CRITICO_", ""), bold=True, color=CRITICO,
                align=TA_CENTER),
            td(a["destinatario"][:34]),
            td(a["cpf"]),
            td(str(a["qtd_notas"]), align=TA_RIGHT),
            td(fmt_brl(a["valor_total"]), align=TA_RIGHT, bold=True),
        ])
    t = Table(linhas, colWidths=[12*mm, W-90*mm, 30*mm, 14*mm, 34*mm], repeatRows=1)
    t.setStyle(tsb())
    story.append(t)
    if len(achados) > 25:
        story.append(Paragraph(
            f"<i>... e mais {len(achados)-25} achado(s). Ver JSON.</i>", ST["small"]))
    return story


def secao_t03(fh):
    t03 = fh.get("t03") or {}
    ach = t03.get("achados", [])
    if not ach: return []
    story = [CondPageBreak(8 * mm)]
    crit = any(a.get("tipo") == "CRITICO" for a in ach)
    story.append(achado_header("T-03",
        "Concentração de Contraparte — Pareto (AN-13)",
        Severidade.CRITICO if crit else Severidade.ATENCAO))
    story.append(sp(2))
    story.append(info_box(
        "<b>Critério:</b> 1 contraparte ≥ 30% da receita = CRÍTICO; ≥ 20% = "
        "ATENÇÃO; TOP-3 ≥ 70% = CRÍTICO. Detecta AN-13 (concentração atípica) "
        "e indicia AN-05 (laranja) ou AN-07 (intermediação não declarada).",
        label="Regra aplicada", border_color=AZUL_M))
    story.append(sp(2))

    for a in ach:
        if a["subtipo"] == "TOP1":
            txt = (f"<b>TOP-1 ({a['tipo']}):</b> {a['destinatario']} "
                    f"({a['cpf']}) concentra <b>{a['pct']:.1f}%</b> da receita "
                    f"— {fmt_brl(a['valor'])} em {a['qtd']} nota(s).")
            sev = CRITICO if a["tipo"] == "CRITICO" else ATENCAO
            bg = CRITICO_BG if a["tipo"] == "CRITICO" else ATENCAO_BG
            story.append(info_box(txt, border_color=sev, bg=bg))
        else:
            txt = (f"<b>TOP-3 ({a['tipo']}):</b> {a['pct']:.1f}% concentrado em 3 "
                    "contrapartes — " +
                    " &nbsp;·&nbsp; ".join(f"<b>{d['nome'][:25]}</b>: {d['pct']:.1f}%"
                                              for d in a["destinatarios"]))
            story.append(info_box(txt, border_color=CRITICO, bg=CRITICO_BG))
        story.append(sp(1))

    rank = t03.get("ranking_top5", [])
    if rank:
        story.append(Paragraph("<b>Ranking TOP-5 contrapartes</b>", ST["subsec"]))
        linhas = [[th("#"), th("Destinatário"), th("Qtd", align=TA_RIGHT),
                    th("Valor", align=TA_RIGHT), th("% Receita", align=TA_RIGHT)]]
        for i, r in enumerate(rank, 1):
            linhas.append([
                td(str(i), align=TA_CENTER),
                td(r["nome"][:42]),
                td(str(r["qtd"]), align=TA_RIGHT),
                td(fmt_brl(r["valor"]), align=TA_RIGHT),
                td(f"{r['pct']:.2f}%", align=TA_RIGHT, bold=True),
            ])
        t = Table(linhas, colWidths=[8*mm, W-86*mm, 16*mm, 36*mm, 26*mm], repeatRows=1)
        t.setStyle(tsb())
        story.append(t)
    return story


def secao_t04(fh):
    t04 = fh.get("t04") or {}
    if not t04: return []
    story = [CondPageBreak(8 * mm)]
    crit = t04.get("tipo") == "CRITICO"
    story.append(achado_header("T-04",
        "Concentração em Pessoa Física — Eixo II (AN-07, AN-05)",
        Severidade.CRITICO if crit else Severidade.ATENCAO))
    story.append(sp(2))
    story.append(info_box(
        f"<b>Critério endurecido:</b> ≥ 85% das vendas para PF + recorrência "
        "(3+ aquisições) = CRÍTICO; ≥ 70% = ATENÇÃO. Indica AN-07 (intermediação "
        "não declarada) e potencial AN-05 (uso de laranjas).",
        label="Regra aplicada",
        border_color=CRITICO if crit else ATENCAO,
        bg=CRITICO_BG if crit else ATENCAO_BG))
    story.append(sp(2))

    story.append(Paragraph(
        f"<b>{t04['tipo']}:</b> <b>{t04['pct_pf']:.1f}%</b> das vendas para PF "
        f"({t04['qtd_vendas_pf']}/{t04['qtd_vendas']}) — "
        f"<b>{len(t04['recorrentes'])} PF(s) recorrente(s)</b>.", ST["body"]))

    if t04.get("recorrentes"):
        linhas = [[th("PF Recorrente"), th("CPF"),
                    th("Qtd", align=TA_RIGHT), th("Valor", align=TA_RIGHT)]]
        for r in t04["recorrentes"][:12]:
            linhas.append([
                td(r["nome"][:42]),
                td(r["cpf"]),
                td(str(r["qtd"]), align=TA_RIGHT, bold=True),
                td(fmt_brl(r["valor"]), align=TA_RIGHT),
            ])
        t = Table(linhas, colWidths=[W-86*mm, 30*mm, 18*mm, 38*mm], repeatRows=1)
        t.setStyle(tsb())
        story.append(t)
    return story


def secao_an_eixo1(fan):
    an02 = fan.get("an02", [])
    an03 = fan.get("an03", [])
    if not (an02 or an03): return []
    story = [CondPageBreak(8 * mm)]
    crit = any(a["tipo"] == "CRITICO" for a in an02 + an03)
    story.append(achado_header("AN-02/03",
        "Eixo I — Manipulação de Valores (Subfat / Superfat)",
        Severidade.CRITICO if crit else Severidade.ATENCAO))
    story.append(sp(2))

    if an02:
        story.append(Paragraph(
            f"<b>AN-02 Subfaturamento — {len(an02)} nota(s)</b>", ST["subsec"]))
        story.append(info_box(
            "R$/cabeça < R$ 1.000 = CRÍTICO; R$ 1.000-1.500 = ATENÇÃO. "
            "Pauta SEFAZ-GO mínima: R$ 1.385 (bezerra fêmea ≤ 12m).",
            border_color=CRITICO, bg=CRITICO_BG))
        linhas = [[th("Sev"), th("NFA"), th("Data"),
                    th("R$/cab", align=TA_RIGHT), th("Cab", align=TA_RIGHT),
                    th("Valor", align=TA_RIGHT), th("Destinatário")]]
        for a in an02[:15]:
            cor = CRITICO if a["tipo"] == "CRITICO" else ATENCAO
            linhas.append([
                td(a["tipo"][:4], bold=True, color=cor, align=TA_CENTER),
                td(a["nfa"]), td(a["data"]),
                td(fmt_brl(a["rs_por_cabeca"]), align=TA_RIGHT, bold=True, color=cor),
                td(str(a["cabecas"]), align=TA_RIGHT),
                td(fmt_brl(a["valor"]), align=TA_RIGHT),
                td(a["destinatario"][:28]),
            ])
        t = Table(linhas,
                   colWidths=[12*mm, 18*mm, 18*mm, 24*mm, 12*mm, 26*mm, W-110*mm],
                   repeatRows=1)
        t.setStyle(tsb())
        story.append(t)
        story.append(sp(2))

    if an03:
        story.append(Paragraph(
            f"<b>AN-03 Superfaturamento — {len(an03)} compra(s)</b>", ST["subsec"]))
        story.append(info_box(
            "R$/cabeça > R$ 12.000 = ATENÇÃO; > R$ 20.000 = CRÍTICO. "
            "Pauta SEFAZ-GO máxima: R$ 8.500 (touro reprodutor).",
            border_color=ALTO, bg=ALTO_BG))
        linhas = [[th("Sev"), th("NFA"), th("Data"),
                    th("R$/cab", align=TA_RIGHT), th("Cab", align=TA_RIGHT),
                    th("Remetente")]]
        for a in an03[:15]:
            cor = CRITICO if a["tipo"] == "CRITICO" else ATENCAO
            linhas.append([
                td(a["tipo"][:4], bold=True, color=cor, align=TA_CENTER),
                td(a["nfa"]), td(a["data"]),
                td(fmt_brl(a["rs_por_cabeca"]), align=TA_RIGHT, bold=True, color=cor),
                td(str(a["cabecas"]), align=TA_RIGHT),
                td(a["remetente"][:36]),
            ])
        t = Table(linhas,
                   colWidths=[12*mm, 18*mm, 18*mm, 26*mm, 12*mm, W-86*mm],
                   repeatRows=1)
        t.setStyle(tsb())
        story.append(t)
    return story


def secao_an08(fan):
    an08 = fan.get("an08", [])
    if not an08: return []
    story = [CondPageBreak(8 * mm)]
    crit = any(a["tipo"] == "CRITICO" for a in an08)
    story.append(achado_header("AN-08",
        "Eixo II — Transferência Intrafamiliar (Sobrenome Raro)",
        Severidade.CRITICO if crit else Severidade.ATENCAO))
    story.append(sp(2))
    story.append(info_box(
        "Destinatário compartilha <b>sobrenome RARO</b> com o contribuinte "
        "(SILVA/SANTOS/etc. excluídos). Detecta venda disfarçada entre familiares "
        "— possível burla a ITCMD/ITBI.",
        label="Regra aplicada", border_color=ATENCAO))
    story.append(sp(2))

    linhas = [[th("Sev"), th("Destinatário"), th("CPF"),
                th("Sobrenomes"), th("Notas", align=TA_RIGHT),
                th("Valor", align=TA_RIGHT)]]
    for a in an08:
        cor = CRITICO if a["tipo"] == "CRITICO" else ATENCAO
        sobr = " + ".join(a.get("sobrenomes_raros") or a["sobrenomes_comuns"])
        linhas.append([
            td(a["tipo"][:4], bold=True, color=cor, align=TA_CENTER),
            td(a["destinatario"][:32]),
            td(a["cpf"]),
            td(sobr),
            td(str(a["qtd_notas"]), align=TA_RIGHT),
            td(fmt_brl(a["valor_total"]), align=TA_RIGHT, bold=True),
        ])
    t = Table(linhas, colWidths=[12*mm, W-114*mm, 30*mm, 30*mm, 14*mm, 28*mm],
               repeatRows=1)
    t.setStyle(tsb())
    story.append(t)
    return story


def secao_an11(fan):
    an11 = fan.get("an11", [])
    if not an11: return []
    story = [CondPageBreak(8 * mm)]
    crit = any(a["tipo"] == "CRITICO" for a in an11)
    story.append(achado_header("AN-11",
        "Eixo III — Sazonalidade Incompatível",
        Severidade.CRITICO if crit else Severidade.ATENCAO))
    story.append(sp(2))
    story.append(info_box(
        "Ciclo pecuário tipicamente distribui receita ao longo de 6-9 meses. "
        "Concentração ≥ 50% em 1 mês = CRÍTICO; ≥ 30% = ATENÇÃO. Pode indicar "
        "AN-10 (capacidade vs SiCAR) ou AN-11 (operação sazonal atípica).",
        label="Regra aplicada", border_color=ALTO, bg=ALTO_BG))
    story.append(sp(2))

    linhas = [[th("Sev"), th("Mês"), th("% Receita", align=TA_RIGHT),
                th("Valor", align=TA_RIGHT), th("Qtd Notas", align=TA_RIGHT)]]
    for a in an11:
        cor = CRITICO if a["tipo"] == "CRITICO" else ATENCAO
        linhas.append([
            td(a["tipo"][:4], bold=True, color=cor, align=TA_CENTER),
            td(a["mes"], bold=True),
            td(f"{a['pct']:.1f}%", align=TA_RIGHT, bold=True, color=cor),
            td(fmt_brl(a["valor"]), align=TA_RIGHT),
            td(str(a["qtd_notas"]), align=TA_RIGHT),
        ])
    t = Table(linhas, colWidths=[14*mm, 24*mm, 28*mm, 40*mm, 24*mm], repeatRows=1)
    t.setStyle(tsb())
    story.append(t)
    return story


def secao_an14(fan):
    an14 = fan.get("an14", [])
    if not an14: return []
    story = [CondPageBreak(8 * mm)]
    story.append(achado_header("AN-14",
        "Eixo IV — Ciclo Operacional Implausível (< 60 dias)",
        Severidade.ATENCAO))
    story.append(sp(2))
    story.append(info_box(
        "Compra (PDF DEST) e revenda (PDF REM) do mesmo lote em janela "
        "&lt; 60 dias — incompatível com ciclo de recria/engorda padrão. "
        "Indício de AN-17 (cascata) ou AN-16 (carrossel).",
        label="Regra aplicada", border_color=ATENCAO, bg=ATENCAO_BG))
    story.append(sp(2))

    linhas = [[th("Dias", align=TA_RIGHT), th("Compra (Remetente)"),
                th("Venda (Destinatário)"),
                th("Cab", align=TA_RIGHT), th("Valor venda", align=TA_RIGHT)]]
    for a in an14[:18]:
        linhas.append([
            td(str(a["dias_entre"]), align=TA_RIGHT, bold=True,
                color=CRITICO if a["dias_entre"] < 15 else ATENCAO),
            td(f"{a['compra_data']} · {a['compra_remetente'][:24]}"),
            td(f"{a['venda_data']} · {a['venda_destinatario'][:24]}"),
            td(str(a["venda_cabecas"]), align=TA_RIGHT),
            td(fmt_brl(a["venda_valor"]), align=TA_RIGHT),
        ])
    t = Table(linhas, colWidths=[12*mm, 70*mm, 70*mm, 12*mm, 28*mm], repeatRows=1)
    t.setStyle(tsb())
    story.append(t)
    if len(an14) > 18:
        story.append(Paragraph(
            f"<i>... e mais {len(an14)-18} ocorrência(s). Ver JSON.</i>",
            ST["small"]))
    return story


def secao_an17(cascatas):
    if not cascatas: return []
    story = [CondPageBreak(8 * mm)]
    story.append(achado_header("AN-17",
        "Eixo V — Emissão em Cascata (A → B → C)",
        Severidade.ALTO))
    story.append(sp(2))
    story.append(info_box(
        "Gado deste cliente (A) é vendido a outro cliente da carteira (B) "
        "e revendido a um terceiro (C) dentro de <b>60 dias</b>. Identifica B "
        "como possível <b>trader intermediário</b> (não produtor rural real).",
        label="Regra aplicada", border_color=ALTO, bg=ALTO_BG))
    story.append(sp(2))

    linhas = [[th("Cliente B (intermediário)"), th("C (final)"),
                th("Data A→B"), th("Data B→C"), th("Dias", align=TA_RIGHT)]]
    for c in cascatas[:15]:
        linhas.append([
            td(c["b_nome"][:30], bold=True, color=ALTO),
            td(c["c_nome"][:30]),
            td(c["a_para_b_data"]),
            td(c["b_para_c_data"]),
            td(str(c["dias_entre"]), align=TA_RIGHT, bold=True),
        ])
    t = Table(linhas, colWidths=[W-100*mm, 50*mm, 22*mm, 22*mm, 14*mm], repeatRows=1)
    t.setStyle(tsb())
    story.append(t)
    return story


def secao_rodape_metodologico(fh):
    story = [PageBreak()]
    story.append(section_header("NOTAS METODOLÓGICAS E LIMITAÇÕES",
                                  accent_color=AZUL_M))
    story.append(sp(3))

    story.append(info_box(
        "<b>Critérios endurecidos.</b> Esta versão aplica limiares mais "
        "agressivos que a bateria original do skill_rural v1.1.0, visando "
        "reduzir falsos negativos. Cada achado é determinístico, reproduzível "
        "e independente de LLM.<br/><br/>"
        "<b>Cobertura.</b> Bateria atual cobre 11 das 18 anomalias do "
        "catálogo: AN-01, AN-02, AN-03, AN-05 (indício), AN-06 (parcial), "
        "AN-07 (parcial), AN-08, AN-11, AN-13, AN-14, AN-17. AN-04, AN-09, "
        "AN-10, AN-12, AN-15, AN-16 e AN-18 exigem cruzamento com bases "
        "externas (AGRODEFESA, SiCAR, RFB) ou perícia documental.<br/><br/>"
        "<b>Fontes.</b> Dados extraídos dos PDFs GIEF SEFAZ-GO — relatórios "
        "REM (saídas) e DEST (entradas) do exercício 2025. Pauta SEFAZ-GO de "
        "referência embarcada no detector AN-02/AN-03.",
        label="ALCANCE E PROCEDIMENTO", border_color=AZUL_M))
    story.append(sp(3))

    story.append(info_box(
        "Este laudo é instrumento de <b>auditoria interna preventiva</b>. "
        "Achados aqui registrados não constituem acusação fiscal e devem ser "
        "confirmados pela administração do contribuinte antes de qualquer "
        "ação saneadora ou retificação. Em caso de retificação espontânea "
        "antes de procedimento de ofício, aplica-se a denúncia espontânea "
        "do art. 138 do CTN.",
        label="DECLARAÇÃO DE ALCANCE", border_color=AZUL))
    return story


# ── Builder principal ────────────────────────────────────────────────────

def gerar_pdf(slug, prefixo, fh, fan, cascatas):
    nome = fan.get("contribuinte_nome", slug)
    qtd_notas = fh.get("qtd_notas", 0)
    if qtd_notas == 0:
        print(f"[SKIP] {slug} - sem notas")
        return None

    arq = DEST / f"LAUDO_FORENSE_{slug}_{DATA}.pdf"

    story = []
    story += construir_capa(fh, fan, cascatas)
    story += construir_kpis(fh, fan)
    story.append(PageBreak())

    story += secao_t01(fh)
    story += secao_t02(fh)
    story += secao_t03(fh)
    story += secao_t04(fh)
    story += secao_an_eixo1(fan)
    story += secao_an08(fan)
    story += secao_an11(fan)
    story += secao_an14(fan)
    story += secao_an17(cascatas)
    story += secao_rodape_metodologico(fh)

    # Two-pass para total_paginas correto
    def _build(total_pag):
        doc = SimpleDocTemplate(
            str(arq), pagesize=A4,
            leftMargin=14 * mm, rightMargin=14 * mm,
            topMargin=24 * mm, bottomMargin=18 * mm,
            title=f"Laudo Forense — {nome}",
            author="ORGATEC — OrgAudi 1.1",
        )
        first, later = criar_handler_pagina(total_paginas=total_pag)
        # Build precisa de cópia da story (consumida no build)
        doc.build(list(story), onFirstPage=first, onLaterPages=later)
        return doc

    # Primeiro pass — chute inicial
    _build(10)
    # Segundo pass — usa contagem real do primeiro pass
    # (ReportLab não expõe contagem fácil — usamos PdfReader leve)
    try:
        from pypdf import PdfReader
        n = len(PdfReader(str(arq)).pages)
        _build(n)
    except Exception:
        pass

    return arq


def main() -> None:
    if not ARQ_HARD.exists() or not ARQ_AN18.exists():
        print(f"[ERRO] JSONs ausentes — esperados:\n  {ARQ_HARD}\n  {ARQ_AN18}")
        return

    hard = json.loads(ARQ_HARD.read_text(encoding="utf-8"))
    an18 = json.loads(ARQ_AN18.read_text(encoding="utf-8"))
    hard_por_slug = {h["slug"]: h for h in hard}
    an_por_slug = {a["slug"]: a for a in an18["por_cliente"]}

    cascatas_por_slug = {}
    cpf_para_slug = {a.get("contribuinte_cpf"): a["slug"]
                      for a in an18["por_cliente"] if a.get("contribuinte_cpf")}
    for c in an18.get("an17_cascata", []):
        slug_a = cpf_para_slug.get(c["a_cpf"])
        if slug_a:
            cascatas_por_slug.setdefault(slug_a, []).append(c)

    print(f"{'CLIENTE':45s} {'STATUS':>8s}  {'ARQUIVO'}")
    print("=" * 100)
    gerados = []
    for slug in hard_por_slug:
        fh = hard_por_slug[slug]
        fan = an_por_slug.get(slug, {})
        prefixo = fh.get("prefixo", slug)
        cascatas = cascatas_por_slug.get(slug, [])
        try:
            arq = gerar_pdf(slug, prefixo, fh, fan, cascatas)
            if arq:
                gerados.append(arq)
                print(f"{slug:45s} {'OK':>8s}  {arq.name}")
            else:
                print(f"{slug:45s} {'SKIP':>8s}  (0 notas)")
        except Exception as e:
            print(f"{slug:45s} {'ERRO':>8s}  {e}")

    print(f"\n[OK] {len(gerados)} PDFs gerados em {DEST}")


if __name__ == "__main__":
    main()
