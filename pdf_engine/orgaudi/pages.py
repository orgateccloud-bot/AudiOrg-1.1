"""
orgaudi.pdf.pages
═════════════════
Builders das 8 páginas do laudo OrgAudi 1.0:

  1) Capa: identificação + síntese cruzada + mapa de severidade + KPIs
  2-3) Achados: detalhados por severidade (CRITICO → CONFORME)
  3) Fórmulas: Regras 1 (classificação), 2 (apuração), 3 (tributos)
  4) Testes: Regras 4 (cruzamentos forenses) e 5 (bases externas) +
              legenda de severidade
  5) Catálogo: 18 tipologias × 5 eixos
  6) Planilhas: vendas + remessas + indicadores de distribuição mensal
  7) Compras + Fórmula F1-F6
  8) Assinatura: declaração + responsável técnico + carimbo de hash

Cada construtor retorna uma lista de Flowables que entra no story do
SimpleDocTemplate. NÃO desenham diretamente no canvas — isso é
responsabilidade dos handlers (orgaudi.pdf.handlers).

Dependências internas: orgaudi.domain, orgaudi.data_processing,
                       orgaudi.styles, orgaudi.catalog, orgaudi.validators
Dependências externas: reportlab
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    Table,
    TableStyle,
)

from .catalog import (
    CATALOGO_ANOMALIAS,
    EixoAnomalia,
    Gravidade,
    buscar_por_eixo,
    buscar_por_gravidade,
)
from .data_processing import (
    MESES_PT,
    PlanilhaMensal,
    ResumoFiscal,
)
from .domain import (
    Achado,
    Contribuinte,
    Etapa,
    NaturezaNota,
    Periodo,
    Severidade,
)
from .styles import (
    ALTO, ALTO_BG, ALTO_BORD,
    ATENCAO, ATENCAO_BG, ATENCAO_BORD,
    AZUL, AZUL_CL, AZUL_M, AZUL_DEEP,
    BRANCO,
    CBG, CBG_LIGHT, CBORD, CBORD_LIGHT,
    CONFORME, CONFORME_BG, CONFORME_BORD,
    CRITICO, CRITICO_BG, CRITICO_BORD,
    CTXT, CTXT_DARK,
    MEDIO, MEDIO_BG, MEDIO_BORD,
    OURO, OURO_BG,
    PH, PW, S, SEV_PALETA, ST, W,
    _get_logo_t,
    achado_header,
    divider_section,
    etapa_card,
    hr,
    info_box,
    kpi_card,
    kpi_row,
    risk_strip,
    section_header,
    sev_card,
    sp,
    td,
    tfoot,
    th,
    tsb,
)
from .validators import (
    fmt_brl,
    fmt_brl_compact,
    fmt_data,
    fmt_pct,
)


logger = logging.getLogger("orgaudi")


# ═══════════════════════════════════════════════════════════════════════════════
#  BUILDERS DE PÁGINAS — corpo extraído do monolito v1.6.1
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════

def construir_pagina_1_capa(
    contribuinte: Contribuinte,
    periodo: Periodo,
    resumo: ResumoFiscal,
    achados: list[Achado],
    n_pf_recorrentes: int = 0,
) -> list:
    """
    Página 1 — Capa com 3 seções:
      1) Tabela de identificação completa do contribuinte (10 linhas)
      2) Síntese quantitativa cruzada (Planilha IR v5 × PDF GIEF)
      3) Mapa de achados por severidade (tabela compacta)
    """
    I = []
    # Espaço para a logo grande desenhada pelo handler da primeira página
    # (a logo é renderizada diretamente no canvas, não no flowable story)
    I.append(sp(28))

    # [Removido: AUDITORIA FORENSE]
    I.append(sp(1))  # Reduzido de sp(4) para liberar espaço
    I.append(Paragraph("Relatório de Análise Fiscal", ST["h1"]))
    # [Removido: Bateria T-01 a T-08 × NFA-e × OrgAudi 1.0]
    I.append(hr(AZUL, 1.5))
    I.append(sp(1))  # Reduzido de sp(2)

    # ──────────────────────────────────────────────────────────
    #  SEÇÃO 1 — TABELA DE IDENTIFICAÇÃO (2 colunas, 10 linhas)
    # ──────────────────────────────────────────────────────────

    # Campos descritivos derivados do resumo
    # Total geral = saídas + compras (exibido como número principal)
    total_geral_notas = resumo.qtd_total_saidas + resumo.qtd_compras
    total_notas_txt = (
        f"{total_geral_notas} "
        f"({resumo.qtd_total_saidas} saídas: {resumo.qtd_vendas} vendas"
        f" + {resumo.qtd_remessas} remessas"
    )
    if resumo.qtd_compras > 0:
        total_notas_txt += f" + {resumo.qtd_compras} compras"
    total_notas_txt += ")"

    # Larguras: label 32mm, valor restante
    LBL_W = 32 * mm
    VAL_W = W - LBL_W

    def _id_row(label: str, valor: str, bold_val: bool = False, big: bool = False):
        """Linha de identificação: label azul + valor.

        big=True torna o valor com fonte maior (10.5 vs 8.5) — usado nas linhas
        principais de identificação (Contribuinte, CPF) para criar âncora visual.
        """
        valor_size = 10.5 if big else 8.5
        return [
            td(label, bold=True, color=AZUL_M, size=7),
            td(valor, bold=bold_val, size=valor_size),
        ]

    # Nível de risco derivado dos achados
    n_criticos = sum(1 for a in achados if a.severidade == Severidade.CRITICO)
    n_altos    = sum(1 for a in achados if a.severidade == Severidade.ALTO)
    if n_criticos >= 2:
        risco_txt   = f"CRÍTICO — {n_criticos} achado(s) crítico(s)"
        risco_color = CRITICO
    elif n_criticos == 1:
        risco_txt   = f"ALTO — {n_criticos} achado crítico + {n_altos} alto(s)"
        risco_color = ALTO
    elif n_altos >= 1:
        risco_txt   = f"MODERADO — {n_altos} achado(s) de alta criticidade"
        risco_color = ATENCAO
    else:
        risco_txt   = "BAIXO — sem achados críticos ou altos"
        risco_color = CONFORME

    id_rows = [
        _id_row("Contribuinte",      contribuinte.nome, bold_val=True, big=True),
        _id_row("CPF",               contribuinte.cpf,  bold_val=True, big=True),
        _id_row("Inscrição Estadual",contribuinte.ie or "—"),
        _id_row("Município",         f"{contribuinte.municipio} / {contribuinte.estado}"
                                      if contribuinte.municipio else contribuinte.estado),
        _id_row("Período auditado",  f"{fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}"),
        _id_row("Documento-base",    "NFA-e · GIEF / SEFAZ-GO"),
        _id_row("Total de notas",    total_notas_txt),
        _id_row("Data da auditoria", fmt_data(periodo.data_auditoria)),
        # Nível de risco — última linha em destaque
        [
            td("Nível de Risco", bold=True, color=risco_color, size=7),
            Paragraph(f"<b>{risco_txt}</b>",
                      S("risco", fontName="Helvetica-Bold", fontSize=8.5,
                        textColor=risco_color, leading=11)),
        ],
    ]

    t_ident = Table(id_rows, colWidths=[LBL_W, VAL_W])
    t_ident.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1),  CBG),
        ("BACKGROUND",    (1, 0), (1, -1),  CBG_LIGHT),
        # Destaque nas 2 primeiras linhas (Contribuinte + CPF)
        ("BACKGROUND",    (1, 0), (1, 1),   colors.HexColor("#E0EDFB")),
        # Última linha — Nível de Risco — fundo branco
        ("BACKGROUND",    (0, -1), (-1, -1), colors.HexColor("#FFFBF0")),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.25, CBORD_LIGHT),
        ("LINEBELOW",     (0, 1), (-1, 1),  0.6, AZUL_CL),
        ("LINEBELOW",     (0, -1), (-1, -1), 1.0, CBORD),
        ("LINEABOVE",     (0, -1), (-1, -1), 0.5, CBORD),
        ("BOX",           (0, 0), (-1, -1), 0.5, CBORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING",    (0, 0), (-1, 1),  4),
        ("BOTTOMPADDING", (0, 0), (-1, 1),  4),
        # Linha de risco: padding generoso
        ("TOPPADDING",    (0, -1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    I.append(t_ident)
    I.append(sp(1.5))

    # ──────────────────────────────────────────────────────────
    #  RISCO GLOBAL — FAIXA DE DESTAQUE CROMÁTICO  [v2.4.1]
    # ──────────────────────────────────────────────────────────
    I.append(risk_strip(risco_txt, risco_color,
                        subtexto=f"Auditoria em {fmt_data(periodo.data_auditoria)}  ·  OrgAudi 1.0"))
    I.append(sp(1.5))

    # ──────────────────────────────────────────────────────────
    #  SEÇÃO 2 — SÍNTESE QUANTITATIVA (modelo GENIS: 3 colunas)
    # ──────────────────────────────────────────────────────────
    I.append(section_header("SÍNTESE QUANTITATIVA", AZUL_M))
    I.append(sp(1))

    # Volume total para cálculo de %
    vol_total = resumo.volume_total
    if vol_total == 0:
        vol_total = Decimal("1")  # Evitar divisão por zero

    def _pct(valor: Decimal) -> str:
        pct = (valor / vol_total * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return f"{pct:.1f}%".replace(".", ",")

    def _dash():
        return td("—", align=TA_CENTER, size=8, color=CTXT)

    # Cabeçalho — 3 colunas: Indicador / Valor / %
    sq_header = [
        th("Indicador"),
        th("Valor", align=TA_RIGHT),
        th("%", align=TA_CENTER),
    ]

    # Linhas alinhadas com o modelo GENIS
    sq_rows = [sq_header]

    # Volume bruto movimentado (total: saídas + compras + outras remessas)
    sq_rows.append([
        td("Volume bruto movimentado"),
        td(fmt_brl(resumo.volume_total), align=TA_RIGHT, size=8, bold=True),
        td("100,0%", align=TA_CENTER, size=8, bold=True),
    ])

    # F1 — Receita imediata
    sq_rows.append([
        td(f"F1 — Receita imediata (vendas diretas)"),
        td(fmt_brl(resumo.F1_receita_imediata), align=TA_RIGHT, size=8),
        td(_pct(resumo.F1_receita_imediata), align=TA_CENTER, size=8),
    ])

    # F2 — Trânsito (remessas de saída)
    sq_rows.append([
        td(f"F2 — Trânsito (remessa/leilão)"),
        td(fmt_brl(resumo.F2_transito), align=TA_RIGHT, size=8),
        td(_pct(resumo.F2_transito), align=TA_CENTER, size=8),
    ])

    # F6 — Despesa (compras de gado)
    if resumo.F6_despesa > 0:
        sq_rows.append([
            td("F6 — Despesa (compra de gado)"),
            td(fmt_brl(resumo.F6_despesa), align=TA_RIGHT, size=8),
            td(_pct(resumo.F6_despesa), align=TA_CENTER, size=8),
        ])

    # Outras remessas recebidas (trânsito de entrada)
    if resumo.outras_remessas_recebidas > 0:
        sq_rows.append([
            td("Outras remessas recebidas"),
            td(fmt_brl(resumo.outras_remessas_recebidas), align=TA_RIGHT, size=8),
            td(_pct(resumo.outras_remessas_recebidas), align=TA_CENTER, size=8),
        ])

    # F5 — Resultado rural
    sq_rows.append([
        td("F5 — Resultado rural (F4−F6)"),
        td(fmt_brl(resumo.F5_resultado_rural), align=TA_RIGHT, size=8),
        _dash(),
    ])

    # Cabeças entradas / saídas
    cab_ent = resumo.cabecas_entradas
    cab_sai = resumo.cabecas_saidas
    if cab_ent > 0 or cab_sai > 0:
        sq_rows.append([
            td("Cabeças entradas / saídas"),
            td(f"{cab_ent:,} / {cab_sai:,}".replace(",", "."), align=TA_RIGHT, size=8),
            _dash(),
        ])

    # Destinatários PF com ≥3 aquisições
    if n_pf_recorrentes > 0:
        sq_rows.append([
            td("Destinatários PF com ≥3 aquisições"),
            td(str(n_pf_recorrentes), align=TA_RIGHT, size=8),
            _dash(),
        ])

    # Funrural estimado
    sq_rows.append([
        td(f"Funrural estimado ({resumo.aliquota_funrural_pct} × F1)"),
        td(fmt_brl(resumo.funrural), align=TA_RIGHT, size=8),
        _dash(),
    ])

    # IRPF Rural estimado
    sq_rows.append([
        td(f"IRPF Rural estimado (20% × F5)"),
        td(fmt_brl(resumo.irpf_estimado), align=TA_RIGHT, size=8),
        _dash(),
    ])

    # Col widths: indicador ocupa ~60%, valor 25%, % 15%
    SQ_C1 = W * 0.60
    SQ_C2 = W * 0.25
    SQ_C3 = W * 0.15
    t_sq = Table(sq_rows, colWidths=[SQ_C1, SQ_C2, SQ_C3])
    t_sq.setStyle(TableStyle([
        # Header
        ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        # Zebra
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CBG_LIGHT]),
        # Linha de volume bruto em destaque
        ("BACKGROUND",     (0, 1), (-1, 1),  colors.HexColor("#E0EDFB")),
        ("FONTNAME",       (0, 1), (-1, 1),  "Helvetica-Bold"),
        # Grid
        ("GRID",           (0, 0), (-1, -1), 0.25, CBORD),
        ("BOX",            (0, 0), (-1, -1), 0.5, AZUL_CL),
        # Alinhamento
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ]))
    I.append(t_sq)
    I.append(sp(1.5))

    # ──────────────────────────────────────────────────────────
    #  SEÇÃO 3 — MAPA DE ACHADOS POR SEVERIDADE (tabela compacta)
    # ──────────────────────────────────────────────────────────
    I.append(section_header("MAPA DE ACHADOS POR SEVERIDADE", AZUL_M))
    I.append(sp(0.5))

    # Agrupar achados por severidade
    bucket: dict[Severidade, list[Achado]] = defaultdict(list)
    for a in achados:
        bucket[a.severidade].append(a)

    sev_ordem = [
        (Severidade.CRITICO,  "CRÍTICO"),
        (Severidade.ALTO,     "ALTO"),
        (Severidade.MEDIO,    "MÉDIO"),
        (Severidade.ATENCAO,  "ATENÇÃO"),
        (Severidade.CONFORME, "CONFORME"),
    ]

    # Tabela com header + 1 linha por severidade
    sev_header = [
        th("Severidade"),
        th("Qtd", align=TA_CENTER),
        th("Conclusão sintética"),
    ]
    sev_rows = [sev_header]

    for sev, label in sev_ordem:
        lista = bucket.get(sev, [])
        if not lista:
            continue
        # Cor
        color, bg, bord = SEV_PALETA[sev]
        # Badge de severidade com cor
        badge = Paragraph(
            f"<b>{label}</b>",
            S(f"sv_{sev.value}", fontName="Helvetica-Bold", fontSize=8,
              textColor=BRANCO, alignment=TA_CENTER, leading=10))
        qtd_p = td(str(len(lista)), bold=True, color=color, align=TA_CENTER, size=10)
        # Concatenar títulos dos achados
        titulos = [a.titulo for a in lista]
        if len(titulos) > 2:
            conclusao_txt = "; ".join(titulos[:2]) + f"; +{len(titulos) - 2} achado(s)"
        else:
            conclusao_txt = "; ".join(titulos)
        conclusao_p = td(conclusao_txt, size=7.5)

        sev_rows.append([badge, qtd_p, conclusao_p])

    # Larguras: severidade 22mm, qtd 10mm, conclusão restante
    SEV_C1 = 22 * mm
    SEV_C2 = 12 * mm
    SEV_C3 = W - SEV_C1 - SEV_C2

    t_sev = Table(sev_rows, colWidths=[SEV_C1, SEV_C2, SEV_C3])

    # Estilo base
    sev_style_cmds = [
        # Header
        ("BACKGROUND",     (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        # Grid
        ("GRID",           (0, 0), (-1, -1), 0.25, CBORD),
        ("BOX",            (0, 0), (-1, -1), 0.5, AZUL_CL),
        # Alinhamento
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
    ]

    # Aplicar cores de fundo por severidade em cada linha
    row_idx = 1  # começa após header
    for sev, label in sev_ordem:
        lista = bucket.get(sev, [])
        if not lista:
            continue
        color, bg, bord = SEV_PALETA[sev]
        # Badge col (col 0) → fundo da cor da severidade
        sev_style_cmds.append(("BACKGROUND", (0, row_idx), (0, row_idx), color))
        sev_style_cmds.append(("TEXTCOLOR",  (0, row_idx), (0, row_idx), BRANCO))
        # Fundo claro na linha de dados (cols 1-2)
        sev_style_cmds.append(("BACKGROUND", (1, row_idx), (-1, row_idx), bg))
        row_idx += 1

    t_sev.setStyle(TableStyle(sev_style_cmds))
    I.append(t_sev)
    I.append(sp(2))

    # ── Bloco de KPIs financeiros derivados ──
    I.append(section_header("INDICADORES FINANCEIROS DERIVADOS", OURO))
    # kpi_row recebe tuplas (label, value, sub, color)
    kpis_data = [
        ("RECEITA BRUTA (F4)",
         fmt_brl_compact(resumo.F4_receita_bruta),
         "Vendas + Leilão realizado",
         AZUL),
        ("RESULTADO RURAL (F5)",
         fmt_brl_compact(resumo.F5_resultado_rural),
         "Base IRPF Rural (F4 − F6)",
         AZUL_M),
        (f"FUNRURAL ({resumo.aliquota_funrural_pct})",
         fmt_brl_compact(resumo.funrural),
         resumo.categoria_previdenciaria,
         ALTO),
        ("IRPF RURAL (estimado)",
         fmt_brl_compact(resumo.irpf_estimado),
         "20% × Resultado rural",
         CRITICO),
    ]
    accent = [AZUL, AZUL_M, ALTO, CRITICO]
    I.append(kpi_row(kpis_data, accent_colors=accent))

    return I


# ─── Mapeamento de fraude por prefixo de código ──────────────────────────────
_FRAUD_MAP: dict[str, tuple[str, str]] = {
    "TR":  ("Operação Circular / Triangulação",
            "Fluxo bidirecional com mesma contraparte em curto intervalo — padrão "
            "clássico de simulação de venda para ocultar origem de ativos ou inflar "
            "receita fictícia. Pode configurar crime contra a ordem tributária "
            "(Lei 8.137/90, art. 1º, I) e lavagem de capitais (Lei 9.613/98, art. 1º)."),
    "C-0": ("Concentração Atípica (T-01)",
            "Operação singular representa parcela desproporcional da receita anual. "
            "Indica possível simulação de venda de alto valor a destinatário único "
            "sem histórico — padrão de uso de 'laranja' ou desvio de ativo rural."),
    "C-1": ("Fragmentação Fiscal — Smurfing (T-02)",
            "Múltiplas notas de baixo valor ao mesmo destinatário no mesmo dia. "
            "Técnica de fracionamento deliberado para escapar de rastreio automático "
            "e controles do CARF. Tipicamente associada à ocultação do volume real "
            "de operações e subdeclaração de receita rural."),
    "C-2": ("Trânsito de Leilão Órfão (T-03)",
            "Remessa para leilão sem nota de venda subsequente do leiloeiro. "
            "Receita da venda não declarada — possível conluio com leiloeiro para "
            "receber valor fora de nota e subtrair da base de Funrural e IRPF."),
    "C-3": ("Intermediação Informal — Perfil de Revenda (T-04)",
            "Concentração excessiva de vendas a PFs sem CAEPF ativo. Padrão de "
            "uso de intermediários informais ('atravessadores') para dissimular "
            "receitas e reduzir rastreabilidade das operações junto à Receita Federal."),
    "A-0": ("Padrão de Alto Risco",
            "Operação com características que indicam possível irregularidade "
            "fiscal. Recomenda-se cruzamento prioritário com GTAs AGRODEFESA-GO, "
            "extratos bancários e cadastro CAEPF da Receita Federal."),
    "IA":  ("Parecer Multiagente — Análise Interpretativa",
            "Resultado da análise por squad de IA forense especializada. "
            "Os indicadores de risco identificados devem ser verificados "
            "com fontes externas antes de qualquer autuação."),
    "TR-": ("Operação Circular / Triangulação",
            "Fluxo bidirecional com mesma contraparte em curto intervalo."),
}

def _tipologia_fraude(achado: "Achado") -> tuple[str, str] | None:
    """Retorna (titulo_fraude, descricao_fraude) ou None se não for crítico."""
    cod = (achado.codigo or "").upper()
    for prefixo, (titulo, descricao) in _FRAUD_MAP.items():
        if cod.startswith(prefixo):
            return titulo, descricao
    return None


def _bloco_risco_fraude(achado: "Achado") -> list:
    """Gera o bloco visual de risco/fraude para achados CRÍTICOS."""
    tipo = _tipologia_fraude(achado)
    if not tipo:
        return []

    titulo_fraude, desc_fraude = tipo
    elementos: list = []

    # Banner de alerta: fundo vermelho escuro, texto branco
    banner = Table([[
        Paragraph("<b>!</b>", S("ico", fontName="Helvetica-Bold", fontSize=18,
                          textColor=BRANCO, alignment=TA_CENTER, leading=20)),
        Paragraph(
            f"<b>POSSÍVEL FRAUDE IDENTIFICADA</b><br/>"
            f"<font size='8'>{titulo_fraude}</font>",
            S("frd", fontName="Helvetica-Bold", fontSize=9.5,
              textColor=BRANCO, leading=13)),
    ]], colWidths=[12*mm, W - 12*mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CRITICO),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("LINEBELOW",     (0, 0), (-1, -1), 2, colors.HexColor("#7F1D1D")),
    ]))
    elementos.append(banner)

    # Corpo: descrição da tipologia + base legal
    corpo = Table([[
        Paragraph(
            f"{desc_fraude}<br/><br/>"
            f"<b>Ação recomendada:</b> "
            "Protocolar pedido de informações fiscais complementares junto à SEFAZ-GO, "
            "cruzar com GTAs AGRODEFESA-GO e extratos bancários do período. "
            "Considerar Denúncia Espontânea (CTN art. 138) se apurado passivo tributário.",
            S("fd", fontName="Helvetica", fontSize=8,
              textColor=colors.HexColor("#450A0A"),
              alignment=TA_JUSTIFY, leading=12)),
    ]])
    corpo.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, CRITICO),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, CRITICO_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    elementos.append(corpo)
    return elementos


def construir_pagina_achados(achados: list[Achado]) -> list:
    """Páginas 2-N — Achados detalhados, agrupados por severidade."""
    I = []

    # Agrupar por severidade
    bucket: dict[Severidade, list[Achado]] = defaultdict(list)
    for a in achados:
        bucket[a.severidade].append(a)

    criticos = bucket.get(Severidade.CRITICO, [])

    secoes = [
        (Severidade.CRITICO,  "ACHADOS CRÍTICOS",             CRITICO),
        (Severidade.ALTO,     "ACHADOS DE ALTA CRITICIDADE",  ALTO),
        (Severidade.MEDIO,    "ACHADOS DE CRITICIDADE MÉDIA", MEDIO),
        (Severidade.ATENCAO,  "PONTOS DE ATENÇÃO",            ATENCAO),
        (Severidade.CONFORME, "CONFORMIDADES VERIFICADAS",    CONFORME),
    ]

    primeira_secao = True
    for sev, titulo_secao, cor_hr in secoes:
        lista = bucket.get(sev, [])
        if not lista:
            continue

        if primeira_secao:
            I.append(PageBreak())

            # ── RELATÓRIO TÉCNICO RESUMIDO ────────────────────────────────────
            I.append(Paragraph("RELATÓRIO TÉCNICO — ACHADOS DE AUDITORIA", ST["sec"]))
            I.append(hr(AZUL, 1.5))
            I.append(sp(1))

            # Resumo dos achados por severidade
            resumo_sev = []
            for s, label in [(Severidade.CRITICO, "Crítico"), (Severidade.ALTO, "Alto"),
                            (Severidade.MEDIO, "Médio"), (Severidade.ATENCAO, "Atenção"),
                            (Severidade.CONFORME, "Conforme")]:
                qtd = len(bucket.get(s, []))
                if qtd > 0:
                    resumo_sev.append(f"<b>{label}</b>: {qtd}")

            I.append(Paragraph(
                f"<b>Distribuição de achados:</b> {' | '.join(resumo_sev)}",
                ST["small"]))
            I.append(sp(1))

            I.append(Paragraph(
                "<b>Metodologia:</b> Auditoria forense de NFA-e mediante análise de padrões anômalos "
                "(concentração, fragmentação, smurfing), validação documental (CPF/CNPJ), "
                "compatibilidade com pauta SEFAZ-GO e cruzamento lógico interno.",
                ST["small"]))
            I.append(sp(1))

            if criticos:
                I.append(Paragraph(
                    f"<b>Achados críticos:</b> {len(criticos)} irregularidade(s) grave(s) "
                    f"que apresenta(m) risco fiscal elevado e requerem coleta de evidências externas "
                    f"(extratos bancários, GTAs, contratos, ACTs) para confirmação.",
                    ST["small"]))
                I.append(sp(2))
            else:
                I.append(sp(1))

            primeira_secao = False
        else:
            I.append(sp(3))

        # ── Cabeçalho da seção com section_header aprimorado ────────────────
        I.append(section_header(titulo_secao, cor_hr))
        I.append(sp(1))

        # ── Banner de alerta geral para seção CRÍTICA — v2.4.1 ───────────────
        if sev == Severidade.CRITICO and criticos:
            n = len(criticos)
            # Linha superior: fundo vermelho escuro (#7F1D1D) + badge de alerta
            banner_topo = Table([[
                Paragraph(
                    "<b>!</b>",
                    S("bi", fontName="Helvetica-Bold", fontSize=22,
                      textColor=colors.HexColor("#FCA5A5"),
                      alignment=TA_CENTER, leading=24)),
                Paragraph(
                    f"<b>ACHADOS CRÍTICOS — {n} IRREGULARIDADE(S) FORMAL(IS) DETECTADA(S)</b>",
                    S("bt", fontName="Helvetica-Bold", fontSize=11,
                      textColor=BRANCO, leading=14)),
            ]], colWidths=[14 * mm, W - 14 * mm])
            banner_topo.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#7F1D1D")),
                ("LINEABOVE",     (0, 0), (-1, 0),  2.5, OURO),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ]))
            # Corpo do banner: descrição técnica + base legal
            banner_corpo = Table([[
                Paragraph(
                    "<b>Descrição técnica:</b> Os achados abaixo são derivados de cruzamento lógico "
                    "interno de NFA-e, validados por regras determinísticas (T-01 a T-08). Cada achado "
                    "exige coleta de evidências primárias (extratos bancários, GTAs AGRODEFESA-GO, "
                    "contratos, ACTs de leiloeiro) antes de integração em parecer técnico formal. "
                    "<b>Base legal:</b> CTN art. 150 §4º · art. 138 (denúncia espontânea).",
                    S("bc", fontName="Helvetica", fontSize=8,
                      textColor=colors.HexColor("#450A0A"),
                      alignment=TA_JUSTIFY, leading=12)),
            ]])
            banner_corpo.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                ("LINEBEFORE",    (0, 0), (0, -1),  4, CRITICO),
                ("LINEBELOW",     (0, 0), (-1, -1), 1.5, colors.HexColor("#450A0A")),
                ("TOPPADDING",    (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ]))
            I.append(banner_topo)
            I.append(banner_corpo)
            I.append(sp(3))

        # ── Achados individuais ───────────────────────────────────────────────
        for a in lista:
            if sev == Severidade.CONFORME:
                # Linha compacta com checkmark
                row = Table([[
                    Paragraph("<b>OK</b>", S("ok",
                        fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=CONFORME, alignment=TA_CENTER, leading=10)),
                    Paragraph(f"<b>{a.codigo}.</b> {a.titulo}", S("ci",
                        fontName="Helvetica", fontSize=8.5,
                        textColor=CTXT_DARK, leading=11)),
                    Paragraph(f"<b>{a.descricao or 'CONFORME'}</b>", S("cr",
                        fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=CONFORME, alignment=TA_RIGHT, leading=10)),
                ]], colWidths=[10*mm, W-50*mm, 40*mm])
                row.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), CONFORME_BG),
                    ("LINEBEFORE",    (0, 0), (0, -1),  3, CONFORME),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING",    (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ]))
                I.append(row)
                I.append(sp(2))
                continue

            # ── Header do achado ──────────────────────────────────────────────
            I.append(achado_header(a.codigo, a.titulo, sev))
            I.append(sp(1))

            # ── Descrição ─────────────────────────────────────────────────────
            if a.descricao:
                I.append(Paragraph(a.descricao, ST["body"]))

            # ── Tabela de evidências ──────────────────────────────────────────
            if a.tabela_cabecalhos and a.tabela_linhas:
                cab = [th(c, align=TA_RIGHT if i > 1 else TA_LEFT)
                       for i, c in enumerate(a.tabela_cabecalhos)]
                rows = [cab]
                for linha in a.tabela_linhas:
                    rows.append([
                        td(v, align=TA_RIGHT if i > 1 else TA_LEFT, size=7.5)
                        for i, v in enumerate(linha)])
                if a.tabela_totais:
                    rows.append([
                        td(v, bold=True, color=BRANCO,
                           align=TA_RIGHT if i > 1 else TA_LEFT, size=7.5)
                        for i, v in enumerate(a.tabela_totais)])
                ncols = len(a.tabela_cabecalhos)
                t = Table(rows, colWidths=[W / ncols] * ncols)
                style = tsb()
                if a.tabela_totais:
                    for s in tfoot():
                        style.add(*s)
                t.setStyle(style)
                I.append(sp(1))
                I.append(t)

            # ── Bloco de risco/fraude (apenas CRÍTICO) ────────────────────────
            if sev == Severidade.CRITICO:
                blocos_fraude = _bloco_risco_fraude(a)
                if blocos_fraude:
                    I.append(sp(1))
                    for bf in blocos_fraude:
                        I.append(bf)

            # ── Cruzamentos obrigatórios ──────────────────────────────────────
            if a.cruzamentos:
                cor_sev = SEV_PALETA[sev][0]
                bg_sev  = SEV_PALETA[sev][1]
                texto = "  ·  ".join(a.cruzamentos)
                if a.porque_critico:
                    texto = f"{a.porque_critico}<br/><br/><b>Cruzamentos:</b> {texto}"
                    label = "POR QUE É CRÍTICO" if sev == Severidade.CRITICO else "VERIFICAÇÃO NECESSÁRIA"
                else:
                    label = "CRUZAMENTOS OBRIGATÓRIOS" if sev == Severidade.CRITICO else "VERIFICAÇÃO NECESSÁRIA"
                I.append(sp(1))
                I.append(info_box(texto, label=label, border_color=cor_sev, bg=bg_sev))

            I.append(sp(2))

    return I


def construir_pagina_5_recomendacoes(etapas: list[Etapa]) -> list:
    """Página 5 — Timeline de recomendações."""
    I = [PageBreak()]
    I.append(Paragraph("RECOMENDAÇÕES E PRÓXIMAS ETAPAS", ST["sec"]))
    I.append(hr(AZUL_M, 1.2))
    I.append(sp(1))

    for i, etapa in enumerate(etapas):
        accent = SEV_PALETA[etapa.accent][0]
        I.append(etapa_card(
            str(etapa.numero),
            etapa.titulo,
            etapa.prazo,
            etapa.itens,
            accent=accent,
        ))
        if i < len(etapas) - 1:
            I.append(sp(1))
    return I
# ═══════════════════════════════════════════════════════════════════════════════
#  BUILDER — Páginas 6 a 11
# ═══════════════════════════════════════════════════════════════════════════════

def construir_pagina_6_formulas() -> list:
    """Página 6 — Regras 1, 2, 3 (classificação, apuração, tributos)."""
    I = [PageBreak()]
    I.append(Paragraph("FÓRMULAS E REGRAS DE CRUZAMENTO DE DADOS", ST["sec"]))
    I.append(hr(AZUL_M, 1.2))
    I.append(Paragraph(
        "Esta página consolida as fórmulas matemáticas e as regras de cruzamento aplicadas pelo "
        "OrgAudi 1.0. Cada regra foi executada nesta auditoria e pode ser reproduzida em qualquer "
        "outro caso.", ST["small"]))
    I.append(sp(1))

    I.append(Paragraph("Regra 1 — Classificação contábil das NFA-e (fundamento)", ST["subsec"]))
    r1 = [
        [th("Posição do contribuinte"), th("Natureza"), th("Categoria"), th("Efeito IRPF Rural")],
        [td("REMETENTE"),                            td("VENDA"),          td("RECEITA",          bold=True, color=CONFORME), td("Soma à base de cálculo")],
        [td("REMETENTE"),                            td("REMESSA/LEILÃO"), td("TRÂNSITO",         bold=True, color=ALTO),     td("Não soma (até arremate)")],
        [td("REMETENTE = DESTINATÁRIO (mesmo CPF)"), td("Qualquer"),       td("TRANSFERÊNCIA",    bold=True, color=CTXT),     td("Neutra")],
        [td("DESTINATÁRIO"),                         td("COMPRA"),         td("DESPESA / INVEST.", bold=True, color=MEDIO),    td("Subtrai da base ou ativa")],
    ]
    tr1 = Table(r1, colWidths=[48*mm, 30*mm, 36*mm, W-114*mm])
    tr1.setStyle(tsb())
    I.append(tr1)
    I.append(sp(1))

    I.append(Paragraph("Regra 2 — Fórmulas de apuração da receita rural", ST["subsec"]))
    I.append(info_box(
        "<b>Receita imediata (F1):</b> Σ Valor | Remetente = Contribuinte AND Natureza = VENDA<br/>"
        "<b>Receita potencial em trânsito (F2):</b> Σ Valor | Remetente = Contribuinte AND Natureza = REMESSA/LEILÃO<br/>"
        "<b>Receita realizada de leilão (F3):</b> Σ Valor das NF-e modelo 55 emitidas pelo leiloeiro<br/>"
        "<b>Receita bruta total DIRPF Rural (F4) = F1 + F3</b><br/>"
        "<b>Resultado da atividade rural (F5) = F4 − F6</b><br/>"
        "<b>Despesas / Compras (F6):</b> Σ Valor | Destinatário = Contribuinte AND Natureza = COMPRA<br/><br/>"
        "<i>NUNCA usar F2 (Receita potencial em trânsito) como base — superdimensiona o IRPF.<br/>"
        "F6 representa o custo de aquisição de gado (investimento agropecuário) e é deduzido da receita bruta "
        "para apuração do resultado rural. Inclui compras de gado para cria, recria, engorda e reprodução.</i>",
        border_color=AZUL_M))
    I.append(sp(1))

    I.append(Paragraph("Regra 3 — Fórmulas tributárias e contribuições acessórias", ST["subsec"]))
    r3 = [
        [th("Tributo / Contribuição"), th("Fórmula"), th("Base legal")],
        # ── Funrural — todas as 3 categorias × 2 períodos ──
        [td("Funrural PF Patronal (até 03/2026)"),
         td("1,50% × RB (1,20% Prev. + 0,10% RAT + 0,20% SENAR)"),
         td("Lei 8.212/91")],
        [td("Funrural PF Patronal (≥ 04/2026)"),
         td("1,63% × RB (1,32% Prev. + 0,11% RAT + 0,20% SENAR)"),
         td("LC 224/2025")],
        [td("Funrural PF Segurado Especial"),
         td("1,50% × RB — alíquota MANTIDA (não majorada pela LC 224/2025)"),
         td("Lei 8.212/91 + RFB 03/2026")],
        [td("Funrural PJ (até 03/2026)"),
         td("2,05% × RB (1,70% Prev. + 0,10% RAT + 0,25% SENAR)"),
         td("Lei 8.870/94")],
        [td("Funrural PJ (≥ 04/2026)"),
         td("2,23% × RB (1,87% Prev. + 0,11% RAT + 0,25% SENAR)"),
         td("LC 224/2025")],
        # ── ICMS GO ──
        [td("ICMS gado entre produtores (GO)"),
         td("Isento (cria/recria/engorda)"),
         td("RCTE-GO Anx. IX, art. 6º, XLIII")],
        [td("ICMS gado para abate (GO)"),
         td("Isento, com Fundeinfra"),
         td("RCTE-GO Anx. IX, art. 6º, CXVI")],
        [td("Fundeinfra (facultativo)"),
         td("% × Valor operação (varia por mercadoria)"),
         td("Lei 21.670/2022 (GO)")],
        # ── IRPF Rural ──
        [td("IRPF Rural (PF) — resultado real"),
         td("Tabela progressiva × Resultado da atividade rural"),
         td("Lei 8.023/90 + RIR/2018")],
        [td("IRPF Rural (PF) — arbitrado"),
         td("20% × Receita bruta (forma presumida)"),
         td("Lei 8.023/90, art. 5º")],
    ]
    tr3 = Table(r3, colWidths=[48*mm, W-96*mm, 48*mm])
    tr3.setStyle(tsb())
    I.append(tr3)
    return I


def construir_pagina_7_testes() -> list:
    """Página 7 — Regras 4, 5 + lista resumida de tipos de anomalia."""
    I = [PageBreak()]
    I.append(Paragraph("Regra 4 — Cruzamentos forenses de detecção de anomalias", ST["subsec"]))
    r4 = [
        [th("Teste"), th("Critério matemático"), th("Detecta")],
        [td("T-01 Concentração",     bold=True), td("Valor 1 nota / Receita anual ≥ 10%"),                    td("Operações extraordinárias")],
        [td("T-02 Smurfing",         bold=True), td("≥ 3 notas mesmo destinatário/dia COM valores idênticos"), td("Fragmentação fiscal")],
        [td("T-03 Trânsito órfão",   bold=True), td("Σ Remessas/Leilão SEM NF-e venda subsequente"),          td("Receita não declarada")],
        [td("T-04 Concentração PF",  bold=True), td("Vendas a PF ≥ 90% E PFs com 3+ aquisições"),             td("Intermediação não declarada")],
        [td("T-05 IE inconsistente", bold=True), td("Mesmo CPF/CNPJ vinculado a 2+ IEs"),                     td("Erro cadastral ou simulação")],
        [td("T-06 Pauta+Sazon.",     bold=True), td("Σ trimestral ≥ 45%"),                                    td("Sub/superfat. ou esvaziamento")],
        [td("T-07 Documental",       bold=True), td("Validação dígito verificador de todos os CPF/CNPJ"),     td("Documentos forjados")],
        [td("T-08 Cruzamento",       bold=True), td("Cruzamento interno por categoria contábil"),              td("Inconsistência entre fontes")],
    ]
    tr4 = Table(r4, colWidths=[34*mm, W-82*mm, 48*mm])
    tr4.setStyle(tsb())
    I.append(tr4)
    I.append(sp(1))

    I.append(Paragraph("Regra 5 — Cruzamentos com bases externas", ST["subsec"]))
    r5 = [
        [th("Fonte externa"), th("O que confirmar"), th("Como cruzar")],
        [td("AGRODEFESA-GO",           bold=True), td("GTA correspondente a cada NFA-e"),  td("1 GTA para cada nota com gado em trânsito")],
        [td("Banco do contribuinte",   bold=True), td("Crédito do valor de cada venda"),   td("Σ depósitos/PIX = Σ receita imediata")],
        [td("Leiloeiros (ACTs)",       bold=True), td("NF-e modelo 55 do leiloeiro"),      td("Cada Remessa/Leilão deve gerar venda subsequente")],
        [td("Receita Federal (CAEPF)", bold=True), td("Status produtor rural dos PFs"),    td("PF sem CAEPF + 3+ compras = revenda informal")],
        [td("SEFAZ-GO+SiCAR+JUCEG",    bold=True), td("IEs ativas; capacidade do imóvel"), td("Cabeças/UA ≤ Área CAR; vínculo + venda atípica")],
    ]
    tr5 = Table(r5, colWidths=[42*mm, 55*mm, W-97*mm])
    tr5.setStyle(tsb())
    I.append(tr5)
    I.append(sp(1))

    I.append(Paragraph("TIPOS DE ANOMALIA CONSIDERADOS NA BATERIA DE TESTES", ST["subsec"]))
    I.append(info_box(
        "Fragmentação fiscal (smurfing) · Subfaturamento · Uso de 'laranjas' · Lavagem de gado de "
        "origem irregular · Conluio com leiloeiro para subdeclaração · Transferência intrafamiliar "
        "disfarçada de venda · Emissão a destinatários inexistentes · Intermediação não declarada por "
        "PFs · Inconsistência cadastral · Concentração atípica de operações · Sazonalidade "
        "incompatível com perfil de produção rotineira.",
        border_color=AZUL_M))
    I.append(sp(1))

    # ── Legenda de severidade dos achados ──
    I.append(Paragraph("LEGENDA DE SEVERIDADE DOS ACHADOS", ST["subsec"]))
    leg = [
        [th("Nível"), th("Cód."), th("Critério de classificação"),
         th("Ação esperada", align=TA_RIGHT)],
        [td("CRÍTICO",   bold=True, color=BRANCO),
         td("C-XX",      bold=True, color=BRANCO),
         td("Indício forte de irregularidade ativa (smurfing, "
            "concentração ≥ 10% em 1 nota)", color=BRANCO),
         td("Aprofundar em 30 dias", bold=True, color=BRANCO, align=TA_RIGHT)],
        [td("ALTO",      bold=True, color=BRANCO),
         td("A-XX",      bold=True, color=BRANCO),
         td("Padrão atípico que merece cruzamento com fontes externas "
            "(GTAs, CAEPF, extratos)", color=BRANCO),
         td("Cruzar em 60 dias", bold=True, color=BRANCO, align=TA_RIGHT)],
        [td("MÉDIO",     bold=True),
         td("M-XX",      bold=True),
         td("Obrigação acessória ou recolhimento derivado do volume auditado"),
         td("Conformidade fiscal", bold=True, align=TA_RIGHT)],
        [td("ATENÇÃO",   bold=True),
         td("AT-XX",     bold=True),
         td("Item de revisão técnica que pode mudar de severidade após análise"),
         td("Revisar manualmente", bold=True, align=TA_RIGHT)],
        [td("CONFORME",  bold=True, color=CONFORME),
         td("OK-XX",     bold=True, color=CONFORME),
         td("Cruzamento ou validação executada com sucesso "
            "(sem indício de irregularidade)", color=CONFORME),
         td("Sem ação", color=CONFORME, align=TA_RIGHT)],
    ]
    t_leg = Table(leg, colWidths=[24*mm, 16*mm, W-90*mm, 50*mm])
    style_leg = tsb()
    # Pintar fundos por severidade — linhas 1, 2 com vermelho/laranja
    style_leg.add("BACKGROUND", (0, 1), (-1, 1), CRITICO)
    style_leg.add("BACKGROUND", (0, 2), (-1, 2), ALTO)
    style_leg.add("BACKGROUND", (0, 3), (-1, 3), MEDIO_BG)
    style_leg.add("BACKGROUND", (0, 4), (-1, 4), ATENCAO_BG)
    style_leg.add("BACKGROUND", (0, 5), (-1, 5), CONFORME_BG)
    t_leg.setStyle(style_leg)
    I.append(t_leg)
    I.append(sp(1))

    I.append(Paragraph(
        "<i>Catálogo completo de 18 tipologias estruturadas em 5 eixos na próxima página.</i>",
        S("nx", fontName="Helvetica-Oblique", fontSize=7.5,
          textColor=CTXT, alignment=TA_RIGHT, leading=10)))
    return I


def construir_pagina_8_catalogo() -> list:
    """Página 8 — Catálogo de 18 tipologias × 5 eixos."""
    I = [PageBreak()]
    I.append(Paragraph("CATÁLOGO COMPLETO DE TIPOLOGIAS DE ANOMALIA", ST["sec"]))
    I.append(hr(AZUL_M, 1.2))

    # Tipologias agora estão sempre disponíveis (integradas no código)
    if not CATALOGO_ANOMALIAS:
        I.append(Paragraph(
            "OrgAudi 1.0 — Catálogo de tipologias estruturado em 5 eixos: "
            "<b>Eixo I</b> Manipulação de Valores · "
            "<b>Eixo II</b> Irregularidade de Partes · "
            "<b>Eixo III</b> Irregularidade de Mercadoria · "
            "<b>Eixo IV</b> Irregularidade Cadastral e Operacional · "
            "<b>Eixo V</b> Esquemas Estruturados.",
            ST["small"]))
        I.append(sp(1))
        I.append(info_box(
            "<b>Catálogo não disponível.</b><br/>"
            "O catálogo de 18 tipologias deveria estar acessível. "
            "Verifique se o arquivo foi carregado corretamente.",
            label="AVISO",
            border_color=ALTO, bg=ALTO_BG))
        return I

    I.append(Paragraph(
        "OrgAudi 1.0 — 18 tipologias estruturadas em 5 eixos de classificação. "
        "Cada anomalia é referenciada por código (AN-XX), eixo, gravidade e tributos impactados.",
        ST["small"]))
    I.append(sp(1))

    grav_color = {
        Gravidade.MUITO_ALTA: CRITICO,
        Gravidade.ALTA: ALTO,
        Gravidade.MEDIA: MEDIO,
    }
    eixo_nomes = {
        EixoAnomalia.MANIPULACAO_VALORES:       "Eixo I — Manipulação de Valores",
        EixoAnomalia.IRREGULARIDADE_PARTES:     "Eixo II — Irregularidade de Partes",
        EixoAnomalia.IRREGULARIDADE_MERCADORIA: "Eixo III — Irregularidade de Mercadoria",
        EixoAnomalia.IRREGULARIDADE_CADASTRAL:  "Eixo IV — Irregularidade Cadastral e Operacional",
        EixoAnomalia.ESQUEMAS_ESTRUTURADOS:     "Eixo V — Esquemas Estruturados",
    }

    rows = [[th("Cód.", size=6.5), th("Tipo / Descrição", size=6.5),
             th("Gravidade", size=6.5, align=TA_CENTER), th("Tributos", size=6.5)]]
    eixo_atual = None
    eixo_indices = []

    for a in CATALOGO_ANOMALIAS:
        if a.eixo != eixo_atual:
            eixo_atual = a.eixo
            rows.append([Paragraph(f"<b>{eixo_nomes[a.eixo]}</b>",
                S("ex", fontName="Helvetica-Bold", fontSize=7.5,
                  textColor=BRANCO, leading=9)), "", "", ""])
            eixo_indices.append(len(rows) - 1)
        rows.append([
            td(a.codigo.value, bold=True, color=grav_color[a.gravidade], size=6.5),
            Paragraph(
                f"<b>{a.tipo}</b> "
                f"<font size='6' color='#475569'>— {a.descricao}</font>",
                S("ad", fontName="Helvetica", fontSize=6.5,
                  textColor=CTXT_DARK, leading=8.5)),
            td(a.gravidade.value, bold=True, color=grav_color[a.gravidade],
               align=TA_CENTER, size=6.5),
            td(", ".join(a.tributos_impactados), size=6.5),
        ])

    tcat = Table(rows, colWidths=[14*mm, W-72*mm, 22*mm, 36*mm])
    style = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  AZUL),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  BRANCO),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 6.5),
        ("GRID",         (0, 0), (-1, -1), 0.2, CBORD),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ])
    for idx in eixo_indices:
        style.add("BACKGROUND",    (0, idx), (-1, idx), AZUL_M)
        style.add("SPAN",          (0, idx), (-1, idx))
        style.add("TOPPADDING",    (0, idx), (-1, idx), 3)
        style.add("BOTTOMPADDING", (0, idx), (-1, idx), 3)
    for i in range(1, len(rows)):
        if i not in eixo_indices:
            cor = BRANCO if (i - eixo_indices[0]) % 2 == 1 else CBG_LIGHT
            style.add("BACKGROUND", (0, i), (-1, i), cor)
    tcat.setStyle(style)
    I.append(tcat)
    I.append(sp(1))

    leg = Table([[
        Paragraph(f"<b>● MUITO ALTA</b> ({len(buscar_por_gravidade(Gravidade.MUITO_ALTA))})",
                  S("lg1", fontName="Helvetica", fontSize=7.5,
                    textColor=CRITICO, alignment=TA_CENTER, leading=10)),
        Paragraph(f"<b>● ALTA</b> ({len(buscar_por_gravidade(Gravidade.ALTA))})",
                  S("lg2", fontName="Helvetica", fontSize=7.5,
                    textColor=ALTO, alignment=TA_CENTER, leading=10)),
        Paragraph(f"<b>● MÉDIA</b> ({len(buscar_por_gravidade(Gravidade.MEDIA))})",
                  S("lg3", fontName="Helvetica", fontSize=7.5,
                    textColor=MEDIO, alignment=TA_CENTER, leading=10)),
        Paragraph(f"<b>Total: {len(CATALOGO_ANOMALIAS)} tipologias × 5 eixos</b>",
                  S("lg4", fontName="Helvetica-Bold", fontSize=7.5,
                    textColor=AZUL, alignment=TA_CENTER, leading=10)),
    ]], colWidths=[W/4]*4)
    leg.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, CBORD),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, CBORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    I.append(leg)
    return I


def _planilha_table(planilha: list[PlanilhaMensal], total_label: str = "TOTAL") -> Table:
    """Constrói tabela de planilha mensal (vendas/remessas/compras)."""
    rows = [[th("Mês"), th("Q. Notas", align=TA_RIGHT),
             th("Cabeças", align=TA_RIGHT), th("Valor", align=TA_RIGHT)]]
    tot_n = tot_c = 0
    tot_v = Decimal("0")
    for p in planilha:
        rows.append([
            td(p.mes, bold=True),
            td(str(p.qtd_notas), align=TA_RIGHT),
            td(str(p.cabecas), align=TA_RIGHT),
            td(fmt_brl(p.valor), align=TA_RIGHT),
        ])
        tot_n += p.qtd_notas
        tot_c += p.cabecas
        tot_v += p.valor
    # Linha TOTAL: fundo azul + texto BRANCO (cor explícita no Paragraph,
    # pois TEXTCOLOR da TableStyle não sobrescreve cor de Paragraph com cor própria)
    rows.append([
        td(total_label, bold=True, color=BRANCO),
        td(str(tot_n), bold=True, color=BRANCO, align=TA_RIGHT),
        td(str(tot_c), bold=True, color=BRANCO, align=TA_RIGHT),
        td(fmt_brl(tot_v), bold=True, color=BRANCO, align=TA_RIGHT),
    ])
    t = Table(rows, colWidths=[35*mm, 22*mm, 22*mm, W-79*mm])
    style = tsb()
    for s in tfoot():
        style.add(*s)
    t.setStyle(style)
    return t


def construir_pagina_9_planilhas(
    planilha_vendas: list[PlanilhaMensal],
    planilha_remessas: list[PlanilhaMensal],
) -> list:
    """Página de Planilhas de Vendas e Remessas + indicadores derivados."""
    I = [PageBreak()]

    # ── Logo institucional no topo da Planilha (movida da página de assinatura) ──
    logo_t = _get_logo_t()
    if logo_t:
        try:
            logo_img = RLImage(logo_t, width=22*mm, height=22*mm,
                               kind="proportional", mask="auto")
            logo_img.hAlign = "CENTER"
            I.append(logo_img)
            I.append(sp(1))
        except Exception as e:
            logger.debug("Logo da planilha não pôde ser desenhada: %s", e)

    I.append(Paragraph("PLANILHA DE GADO PARA IMPOSTO DE RENDA", ST["h2"]))
    I.append(Paragraph("Lei 8.023/90 — IRPF Atividade Rural", ST["sub"]))
    I.append(hr(AZUL, 1.2))
    I.append(sp(1))  # ↓ reduzido de sp(2)

    I.append(Paragraph("VENDAS — Cliente como REMETENTE → RECEITA", ST["sec"]))
    I.append(_planilha_table(planilha_vendas))
    I.append(sp(1))

    I.append(Paragraph(
        "REMESSAS — Cliente como REMETENTE → TRÂNSITO (não soma à base IRPF)", ST["sec"]))
    I.append(_planilha_table(planilha_remessas))
    I.append(sp(1))  # ↓ reduzido de sp(2)

    # ── Bloco de indicadores derivados de distribuição mensal ──
    I.append(Paragraph("INDICADORES DE DISTRIBUIÇÃO MENSAL", ST["sec"]))
    I.append(hr(AZUL_M, 0.8))
    I.append(sp(1))

    def _ind_vendas(planilha: list[PlanilhaMensal]) -> dict:
        """Calcula indicadores de distribuição (média, pico, concentração)."""
        if not planilha:
            return {"meses_ativos": 0, "media_valor": Decimal("0"),
                    "mes_pico": "—", "valor_pico": Decimal("0"),
                    "pct_pico": Decimal("0"), "trim_pico": "—",
                    "pct_trim_pico": Decimal("0")}
        total_v = sum((p.valor for p in planilha), Decimal("0"))
        meses_ativos = len(planilha)
        media_v = (total_v / Decimal(meses_ativos)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP) if meses_ativos > 0 else Decimal("0")
        # mês de pico
        pico = max(planilha, key=lambda p: p.valor)
        pct_pico = (pico.valor / total_v * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP) if total_v > 0 else Decimal("0")
        # trimestre de pico — agrupa meses por trimestre
        # MESES_PT é constante global ["JAN", "FEV", ...]
        trim_idx = {}
        for p in planilha:
            try:
                m_idx = MESES_PT.index(p.mes)  # 0..11
            except ValueError:
                continue
            trim = m_idx // 3 + 1  # 1..4
            trim_idx.setdefault(trim, Decimal("0"))
            trim_idx[trim] += p.valor
        if trim_idx and total_v > 0:
            t_pico = max(trim_idx.items(), key=lambda x: x[1])
            trim_pico = f"{t_pico[0]}º trim."
            pct_trim_pico = (t_pico[1] / total_v * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            trim_pico = "—"
            pct_trim_pico = Decimal("0")
        return {
            "meses_ativos": meses_ativos,
            "media_valor": media_v,
            "mes_pico": pico.mes,
            "valor_pico": pico.valor,
            "pct_pico": pct_pico,
            "trim_pico": trim_pico,
            "pct_trim_pico": pct_trim_pico,
        }

    ind_v = _ind_vendas(planilha_vendas)
    ind_r = _ind_vendas(planilha_remessas)

    rows_ind = [
        [th("Indicador"),
         th("Vendas (Receita)", align=TA_RIGHT),
         th("Remessas (Trânsito)", align=TA_RIGHT)],
        [td("Meses com movimento"),
         td(str(ind_v["meses_ativos"]), bold=True, align=TA_RIGHT),
         td(str(ind_r["meses_ativos"]), bold=True, align=TA_RIGHT)],
        [td("Média mensal (mês ativo)"),
         td(fmt_brl(ind_v["media_valor"]), align=TA_RIGHT),
         td(fmt_brl(ind_r["media_valor"]), align=TA_RIGHT)],
        [td("Mês de pico"),
         td(f'{ind_v["mes_pico"]} — {fmt_brl(ind_v["valor_pico"])} ({fmt_pct(float(ind_v["pct_pico"]))})',
            align=TA_RIGHT),
         td(f'{ind_r["mes_pico"]} — {fmt_brl(ind_r["valor_pico"])} ({fmt_pct(float(ind_r["pct_pico"]))})'
            if ind_r["meses_ativos"] > 0 else "—",
            align=TA_RIGHT)],
        [td("Trimestre de maior concentração"),
         td(f'{ind_v["trim_pico"]} ({fmt_pct(float(ind_v["pct_trim_pico"]))})',
            align=TA_RIGHT),
         td(f'{ind_r["trim_pico"]} ({fmt_pct(float(ind_r["pct_trim_pico"]))})'
            if ind_r["meses_ativos"] > 0 else "—",
            align=TA_RIGHT)],
    ]
    t_ind = Table(rows_ind, colWidths=[W*0.40, W*0.30, W*0.30])
    t_ind.setStyle(tsb())
    I.append(t_ind)
    I.append(sp(2))

    # ── Nota interpretativa ──
    I.append(info_box(
        "<b>Como ler estes indicadores:</b> uma concentração trimestral acima de "
        "<b>45%</b> dispara o teste forense T-06 (sazonalidade incompatível com "
        "produção rotineira). Picos em um único mês ≥ 30% da receita anual também "
        "merecem cruzamento com GTAs e extratos bancários. Valores equilibrados "
        "ao longo do ano são o padrão esperado para pecuária de cria/recria/engorda.",
        border_color=AZUL_M, bg=CBG_LIGHT))
    return I


def construir_pagina_10_compras_formula(
    planilha_compras: list[PlanilhaMensal],
    resumo: ResumoFiscal,
) -> list:
    """Página 10 — Total geral + Compras + Fórmula F1-F6."""
    I = [PageBreak()]

    # Total geral das saídas
    tg = [
        [th("TOTAL GERAL DAS SAÍDAS (Vendas + Remessas)", align=TA_LEFT),
         th("Notas", align=TA_RIGHT),
         th("Cabeças", align=TA_RIGHT),
         th("Valor", align=TA_RIGHT)],
        [td("Soma agregada das saídas (cliente como REMETENTE)", bold=True),
         td(str(resumo.qtd_total_saidas), bold=True, align=TA_RIGHT, color=AZUL),
         td(str(resumo.cabecas_vendas + resumo.cabecas_remessas),
            bold=True, align=TA_RIGHT, color=AZUL),
         td(fmt_brl(resumo.valor_bruto_saidas), bold=True, align=TA_RIGHT, color=AZUL)],
    ]
    ttg = Table(tg, colWidths=[W-79*mm, 22*mm, 22*mm, 35*mm])
    ttg.setStyle(tsb(stripe=False))
    I.append(ttg)
    I.append(sp(1))

    I.append(Paragraph(
        "COMPRAS — Cliente como DESTINATÁRIO → DESPESA / INVESTIMENTO", ST["sec"]))
    I.append(_planilha_table(planilha_compras))
    I.append(sp(1))

    I.append(Paragraph("FÓRMULA APLICADA — REGRA 2 (APURAÇÃO DA RECEITA RURAL)", ST["sec"]))
    fr = [
        [th("Cód."), th("Descrição"), th("Valor", align=TA_RIGHT)],
        [td("F1", bold=True, color=CONFORME),
         td("Receita imediata (vendas diretas)"),
         td(fmt_brl(resumo.F1_receita_imediata), align=TA_RIGHT)],
        [td("F2", bold=True, color=ALTO),
         td("Trânsito potencial (remessas — NÃO base IRPF)"),
         td(fmt_brl(resumo.F2_transito), align=TA_RIGHT)],
        [td("F3", bold=True, color=CONFORME),
         td("Receita realizada de leilão (NF-e mod. 55)"),
         td(fmt_brl(resumo.F3_receita_realizada_leilao), align=TA_RIGHT)],
        [td("F4", bold=True, color=AZUL_M),
         td("Receita bruta total DIRPF Rural (F1 + F3)"),
         td(fmt_brl(resumo.F4_receita_bruta), bold=True, align=TA_RIGHT)],
        [td("F6", bold=True, color=MEDIO),
         td("Despesa / Investimento dedutível (compras)"),
         td(fmt_brl(resumo.F6_despesa), align=TA_RIGHT)],
        [td("F5", bold=True, color=BRANCO),
         td("Resultado da atividade rural (F4 − F6)", bold=True, color=BRANCO),
         td(fmt_brl(resumo.F5_resultado_rural), bold=True, color=BRANCO, align=TA_RIGHT)],
    ]
    tf = Table(fr, colWidths=[14*mm, W-54*mm, 40*mm])
    style_tf = tsb()
    for s in tfoot():
        style_tf.add(*s)
    tf.setStyle(style_tf)
    I.append(tf)
    return I


def construir_pagina_2_resumo_executivo(
    resumo: "ResumoFiscal",
    periodo: "Periodo",
    achados_criticos: int = 1,
    achados_medio: int = 2,
    achados_conforme: int = 3,
) -> list:
    """
    Página 2 — Resumo Executivo Sincronizado com Logo ORGATEC.
    
    Estrutura em 4 "fitas" coloridas (inspirada nas 4 fitas do globo 3D):
    - Fita 1 (Azul Escuro): Achados Críticos
    - Fita 2 (Azul Médio): Obrigações Acessórias
    - Fita 3 (Azul Claro): Fórmula Aplicada (F1-F6)
    - Fita 4 (Branco): Status de Conformidade
    """
    I = [PageBreak()]
    
    # ── TÍTULO HERO ──
    I.append(Paragraph("02 · Intelligence Report", S("kicker")))
    I.append(Paragraph("Resumo Executivo", ST["h1"]))
    I.append(sp(1))
    I.append(Paragraph(
        "Quatro dimensões críticas sincronizadas — do mais profundo risco ao mais claro resultado. "
        "Uma página para captar a essência do laudo em 60 segundos.",
        ST["body"]))
    I.append(sp(2))
    
    # ── GRID 2×2 DE FITAS COLORIDAS ──
    # Vou usar uma abordagem mais simples: 4 Paragraph + HR para cada fita
    
    # Fita 1 — Azul Escuro
    fita_1 = Table(
        [[Paragraph(
            f"<b>01 · ACHADOS CRÍTICOS</b><br/>"
            f"Concentração em PFs — 100% das vendas para 4 destinatários<br/>"
            f"<font color='#5db3ff'><b>{achados_criticos} achado(s) crítico(s)</b></font>",
            S("f", fontSize=8.5, textColor=BRANCO, leading=12)
        )]],
        colWidths=[W/2 - 3*mm],
    )
    fita_1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#003365")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#3f88d5")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    
    # Fita 2 — Azul Médio
    fita_2 = Table(
        [[Paragraph(
            f"<b>02 · OBRIGAÇÕES ACESSÓRIAS</b><br/>"
            f"Funrural a recolher — 1,50% × F1<br/>"
            f"<font color='#7fc8ff'><b>{fmt_brl(resumo.F1_receita_imediata * Decimal('0.015'))}</b></font>",
            S("f", fontSize=8.5, textColor=BRANCO, leading=12)
        )]],
        colWidths=[W/2 - 3*mm],
    )
    fita_2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#185FA5")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#5db3ff")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    
    # Fita 3 — Azul Claro
    fita_3 = Table(
        [[Paragraph(
            f"<b>03 · FÓRMULA APLICADA (F1–F6)</b><br/>"
            f"Resultado Rural — F4 − F6 = F5<br/>"
            f"<font color='#d4e8ff'><b>{fmt_brl(resumo.F5_resultado_rural)}</b></font>",
            S("f", fontSize=8.5, textColor=BRANCO, leading=12)
        )]],
        colWidths=[W/2 - 3*mm],
    )
    fita_3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#3f88d5")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#a8d4ff")),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    
    # Fita 4 — Branco/Luz
    fita_4 = Table(
        [[Paragraph(
            f"<b>04 · STATUS DE CONFORMIDADE</b><br/>"
            f"Validações Executadas — {achados_conforme} de 5<br/>"
            f"<font color='#185FA5'><b>{achados_conforme + achados_criticos + achados_medio} achado(s) total(is)</b></font>",
            S("f", fontSize=8.5, textColor=AZUL, leading=12)
        )]],
        colWidths=[W/2 - 3*mm],
    )
    fita_4.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef3f9")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, AZUL_M),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    
    # Grid 2×2
    grid = Table(
        [[fita_1, fita_2],
         [fita_3, fita_4]],
        colWidths=[W/2 - 3*mm, W/2 - 3*mm],
        rowHeights=[60*mm, 60*mm],
    )
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("LINEABOVE", (0, 0), (-1, -1), 0.5, CBORD),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, CBORD),
        ("LINERIGHT", (0, 0), (-1, -1), 0.5, CBORD),
        ("LINELEFT", (0, 0), (-1, -1), 0.5, CBORD),
    ]))
    I.append(grid)
    I.append(sp(2))

    # ── ANÁLISE TÉCNICA RESUMIDA ──
    I.append(Paragraph("ANÁLISE TÉCNICA RESUMIDA", ST["sec"]))
    I.append(sp(0.5))

    analise_txt = (
        f"<b>Período auditado:</b> {fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}<br/>"
        f"<b>Metodologia:</b> Análise determinística via 8 testes forenses (T-01 a T-08) — "
        f"concentração, smurfing, trânsito órfão, subfaturamento, sazonalidade, validação documental.<br/>"
        f"<b>Base técnica:</b> Cruzamento lógico interno de NFA-e sem validação externa.<br/>"
        f"<b>Escopo:</b> NFA-e GIEF/SEFAZ-GO | Não inclui NF-e ou NFS-e.<br/>"
        f"<b>Confiabilidade:</b> Achados críticos requerem coleta de evidências (extratos, GTAs, contratos) "
        f"antes de integração em parecer formal."
    )
    I.append(Paragraph(analise_txt, ST["small"]))
    I.append(sp(2))

    # ── AÇÕES RECOMENDADAS ──
    I.append(Paragraph("AÇÕES RECOMENDADAS", ST["sec"]))
    I.append(sp(1))
    
    actions = [
        ["01", "Cruzar CAEPF dos PFs recorrentes", "60 dias"],
        ["02", "Conferir GTAs no AGRODEFESA-GO", "60 dias"],
        ["03", "Recolher Funrural (GPS mensal)", "Conformidade Mensal"],
        ["04", "Manter LCDPR atualizado", "DIRPF 2026"],
    ]
    
    action_rows = []
    for num, desc, prazo in actions:
        action_rows.append([
            td(num, bold=True, color=AZUL_M, size=9),
            td(desc, size=8),
            td(prazo, bold=True, color=AZUL, size=7, align=TA_RIGHT),
        ])
    
    t_actions = Table(action_rows, colWidths=[15*mm, W-65*mm, 50*mm])
    t_actions.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), CBG),
        ("BACKGROUND", (1, 0), (1, -1), BRANCO),
        ("BACKGROUND", (2, 0), (2, -1), CBG_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, CBORD_LIGHT),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, AZUL_CL),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    I.append(t_actions)
    
    return I


def construir_pagina_11_assinatura(
    contribuinte: Contribuinte,
    periodo: Periodo,
    hash_doc: str,
) -> list:
    """Página final — Declarações + assinatura + carimbo de hash.

    Usa CondPageBreak: se sobrarem ≥110mm na página anterior (compras+F1-F6),
    a assinatura se acomoda no rodapé sem quebrar página, eliminando uma
    página inteira de espaço em branco.
    """
    # CondPageBreak: só cria nova página se não couber 110mm de conteúdo
    I: list = [CondPageBreak(110 * mm)]
    I.append(sp(2))

    I.append(Paragraph("DECLARAÇÃO DE ALCANCE E LIMITAÇÕES", ST["sec"]))
    I.append(hr(AZUL_M, 1.0))  # ↓ thickness reduzido
    I.append(sp(1))

    I.append(info_box(
        "Este relatório foi produzido pelo sistema OrgAudi 1.0 / NFA Extractor com base nos arquivos "
        "PDF de NFA-e fornecidos. Os achados constituem <b>indícios objetivos</b> derivados de "
        "cruzamentos lógicos internos, não confirmados com documentação primária externa "
        "(extratos bancários, GTAs, ACTs, contratos). A confirmação depende de etapa subsequente "
        "de coleta de evidências.",
        label="ALCANCE", border_color=AZUL_M, bg=CBG_LIGHT))
    I.append(sp(1))

    I.append(info_box(
        "<b>O presente documento NÃO formula acusações, NÃO imputa dolo e NÃO substitui procedimento "
        "de fiscalização tributária formal.</b> Os elementos aqui mapeados constituem subsídios "
        "técnicos para tomada de decisão do contribuinte e de seus assessores, e para eventual "
        "regularização espontânea nos termos do art. 138 do CTN.",
        label="LIMITAÇÕES", border_color=ALTO, bg=ALTO_BG))
    I.append(sp(2))  # ↓ reduzido de sp(3)

    I.append(Paragraph("RESPONSÁVEL TÉCNICO PELA AUDITORIA", ST["sec"]))
    I.append(hr(AZUL, 1.0))  # ↓ thickness reduzido
    I.append(sp(2))  # ↓ reduzido de sp(4)

    # ── Bloco de assinatura (sem logo — logo foi movida para a Planilha) ──
    I.append(Paragraph("ROBSON ALAIN VELOSO", ST["an"]))
    I.append(Paragraph("Ciências Contábeis", ST["as"]))
    I.append(Paragraph("ORGATEC CONTABILIDADE E AUDITORIA", ST["ae"]))
    I.append(Paragraph(
        f"Auditoria emitida em {fmt_data(periodo.data_auditoria)}", ST["as"]))
    I.append(sp(1))
    I.append(HRFlowable(width="55%", thickness=0.4, color=CBORD, spaceAfter=2))
    I.append(Paragraph("Sistema de auditoria contábil-fiscal", ST["small"]))
    I.append(Paragraph(
        "OrgAudi 1.0 / NFA Extractor — ORGATEC Contabilidade e Auditoria", ST["sys"]))
    I.append(sp(2))  # ↓ reduzido de sp(3)

    # ── Carimbo de validação ──
    carimbo = Table(
        [[
            Paragraph(
                "<b>HASH DE VALIDAÇÃO</b>",
                S("ch1", fontName="Helvetica-Bold", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9)),
            Paragraph(
                f"<b>{hash_doc}</b>",
                S("ch2", fontName="Courier-Bold", fontSize=10,
                  textColor=AZUL, alignment=TA_LEFT, leading=12)),
        ], [
            Paragraph(
                "ALGORITMO",
                S("ch3", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9)),
            Paragraph(
                "SHA-256 (16 hex)",
                S("ch4", fontName="Helvetica", fontSize=8,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)),
        ], [
            Paragraph(
                "EMITIDO EM",
                S("ch5", fontName="Helvetica", fontSize=7,
                  textColor=CTXT, alignment=TA_LEFT, leading=9)),
            Paragraph(
                fmt_data(periodo.data_auditoria),
                S("ch6", fontName="Helvetica-Bold", fontSize=8,
                  textColor=CTXT_DARK, alignment=TA_LEFT, leading=10)),
        ]],
        colWidths=[35*mm, W - 35*mm],
    )
    carimbo.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, CBORD),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.4, CBORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),  # ↓ reduzido de 4
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),  # ↓ reduzido de 4
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    I.append(carimbo)
    I.append(sp(1))  # ↓ reduzido de sp(2)

    # ── Disclaimer final em itálico ──
    cl = Table([[Paragraph(
        "<i>Classificação contábil: Cliente=Remetente → Receita; Cliente=Destinatário → "
        "Despesa/Investimento; Remessa/Leilão → Trânsito (não-receita até arremate). "
        f"Processamento por OrgAudi 1.0 — Hash documento: <b>{hash_doc}</b></i>",
        S("cl", fontName="Helvetica-Oblique", fontSize=7.5,
          textColor=CTXT, alignment=TA_CENTER, leading=10))
    ]], colWidths=[W])
    cl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, AZUL_CL),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),  # ↓ reduzido de 6
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),  # ↓ reduzido de 6
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    I.append(cl)
    return I


# ═══════════════════════════════════════════════════════════════════════════════
#  PÁGINAS 12-15: RELATÓRIO TÉCNICO (4 páginas)
# ═══════════════════════════════════════════════════════════════════════════════

def construir_paginas_relatorio_tecnico_4p(resumo, achados: list) -> list:
    """4 páginas de relatório técnico detalhado: metodologia, risco, matriz, recomendações."""
    I = [PageBreak()]

    # ── PÁGINA 1: METODOLOGIA E ESCOPO ────────────────────────────────────────
    I.append(Paragraph("METODOLOGIA E ESCOPO DA AUDITORIA", ST["sec"]))
    I.append(hr(AZUL, 1.5))
    I.append(sp(1))

    I.append(Paragraph("<b>1. Objetivo</b>", ST["subsec"]))
    I.append(Paragraph(
        "Análise forense de Notas Fiscais Avulsas Eletrônicas (NFA-e) do GIEF/SEFAZ-GO "
        "para identificação de padrões anômalos indicativos de irregularidades fiscais. "
        "O escopo limita-se à extração de dados estruturados de PDFs e análise determinística "
        "via cruzamentos lógicos internos, SEM validação de documentação primária externa.",
        ST["body"]))
    I.append(sp(1))

    I.append(Paragraph("<b>2. Critérios de Seleção de Achados</b>", ST["subsec"]))
    I.append(Paragraph(
        "<b>Crítico:</b> Padrões que apresentam alto risco de descaracterização fiscal "
        "(concentração ≥10% da receita, smurfing, trânsito órfão).<br/>"
        "<b>Alto:</b> Indicadores de intermediação não declarada ou incompatibilidade com pauta "
        "(5–10% concentração, PF com perfil de revenda).<br/>"
        "<b>Médio:</b> Inconsistências documentais menores (IE não ativa, município desalinhado).<br/>"
        "<b>Atenção:</b> Conformidades parciais que requerem monitoramento (sazonalidade extrema).<br/>"
        "<b>Conforme:</b> Notas validadas por dígito verificador e pauta SEFAZ-GO.",
        ST["body"]))
    I.append(sp(2))

    # ── PÁGINA 2: ANÁLISE DE RISCO E TIPOLOGIAS ───────────────────────────────
    I.append(PageBreak())
    I.append(Paragraph("ANÁLISE DE RISCO E TIPOLOGIAS DE FRAUDE", ST["sec"]))
    I.append(hr(AZUL, 1.5))
    I.append(sp(1))

    I.append(Paragraph("<b>Fatores de Risco Mapeados</b>", ST["subsec"]))
    risco_rows = [
        [th("Fator"), th("Indicador"), th("Base Legal"), th("Severidade")],
        [td("Concentração (T-01)"),
         td("Nota > 10% da receita anual"),
         td("CTN 150 § 4º"),
         td("CRÍTICO", color=CRITICO, bold=True)],
        [td("Smurfing (T-02)"),
         td("≥3 notas mesmo destinatário/dia"),
         td("LC 105/2001"),
         td("CRÍTICO", color=CRITICO, bold=True)],
        [td("Trânsito órfão (T-03)"),
         td("Remessa sem NF-e de venda"),
         td("RCTE-GO"),
         td("CRÍTICO", color=CRITICO, bold=True)],
        [td("Concentração PF (T-04)"),
         td("≥90% compradores PF"),
         td("Lei 12.683/2012"),
         td("ALTO", color=ALTO, bold=True)],
        [td("Subfaturamento (T-06)"),
         td("Valor < 70% da pauta"),
         td("SEFAZ-GO"),
         td("ALTO", color=ALTO, bold=True)],
    ]
    t_risco = Table(risco_rows, colWidths=[30*mm, 45*mm, 30*mm, 35*mm])
    t_risco.setStyle(tsb())
    I.append(t_risco)
    I.append(sp(2))

    # ── PÁGINA 3: MATRIZ DE ACHADOS ───────────────────────────────────────────
    I.append(PageBreak())
    I.append(Paragraph("MATRIZ DE ACHADOS COM CRUZAMENTOS OBRIGATÓRIOS", ST["sec"]))
    I.append(hr(AZUL, 1.5))
    I.append(sp(1))

    criticos = [a for a in achados if a.severidade.value == "critico"]
    altos = [a for a in achados if a.severidade.value == "alto"]

    I.append(Paragraph(f"<b>Achados Críticos: {len(criticos)}</b>", ST["subsec"]))
    for a in criticos:
        cruzamentos_txt = " · ".join(a.cruzamentos) if a.cruzamentos else "Consultar AGRODEFESA-GO, extratos, contratos"
        I.append(Paragraph(
            f"<b>{a.codigo}.</b> {a.titulo}<br/>"
            f"<font size='8'><b>Cruzamentos:</b> {cruzamentos_txt}</font>",
            ST["body"]))
        I.append(sp(1))

    I.append(Paragraph(f"<b>Achados Alto: {len(altos)}</b>", ST["subsec"]))
    for a in altos:
        cruzamentos_txt = " · ".join(a.cruzamentos) if a.cruzamentos else "CAEPF Receita Federal, JUCEG"
        I.append(Paragraph(
            f"<b>{a.codigo}.</b> {a.titulo}<br/>"
            f"<font size='8'><b>Verificação:</b> {cruzamentos_txt}</font>",
            ST["body"]))
        I.append(sp(1))

    I.append(sp(2))

    # ── PÁGINA 4: RECOMENDAÇÕES TÉCNICAS ──────────────────────────────────────
    I.append(PageBreak())
    I.append(Paragraph("RECOMENDAÇÕES TÉCNICAS E PRÓXIMAS ETAPAS", ST["sec"]))
    I.append(hr(AZUL, 1.5))
    I.append(sp(1))

    I.append(Paragraph("<b>Etapa 1 — Coleta de Evidências (Semanas 1-2)</b>", ST["subsec"]))
    I.append(Paragraph(
        "☐ Solicitar extratos bancários (entrada e saída de caixa)<br/>"
        "☐ Coletar GTAs (Guias de Trânsito Animal) via AGRODEFESA-GO<br/>"
        "☐ Obter ACTs de leiloeiros (notas de venda correspondentes)<br/>"
        "☐ Compilar contratos de compra/venda com destinatários críticos",
        ST["body"]))
    I.append(sp(1))

    I.append(Paragraph("<b>Etapa 2 — Análise de Terceiros (Semanas 2-3)</b>", ST["subsec"]))
    I.append(Paragraph(
        "☐ Consultar CAEPF na Receita Federal para PFs compradores recorrentes<br/>"
        "☐ Verificar vínculos societários via JUCEG e RFB (Quadro Societário)<br/>"
        "☐ Confirmar IE dos fornecedores na SEFAZ-GO<br/>"
        "☐ Localizar CAR das propriedades envolvidas (capacidade de suporte)",
        ST["body"]))
    I.append(sp(1))

    I.append(Paragraph("<b>Etapa 3 — Parecer Final (Semana 4)</b>", ST["subsec"]))
    I.append(Paragraph(
        "☐ Consolidar evidências em matriz de confirmação<br/>"
        "☐ Reclassificar achados (crítico → comprovado/rejeitado)<br/>"
        "☐ Emitir parecer técnico fundamentado (CTN 150 § 4º)<br/>"
        "☐ Orientar sobre denúncia espontânea (CTN 138) se aplicável",
        ST["body"]))
    I.append(sp(2))

    I.append(info_box(
        "<b>Prazo estimado:</b> 30 dias de trabalho campo / análise.<br/>"
        "<b>Documentação obrigatória:</b> Toda etapa deve ser registrada com data, responsável e resultado.",
        label="TIMELINE", border_color=AZUL_M, bg=CBG_LIGHT))

    return I

