"""
orgaudi.styles
══════════════
Paleta de cores institucional ORGATEC, dimensões de página, helpers de
Paragraph/Tabela e componentes visuais reutilizáveis (KPIs, achados,
caixas informativas, cards de severidade, cards de etapa).

Toda a aparência do PDF passa por aqui. Para alterar identidade visual
(cores, fontes, espaçamentos), edite este módulo.

Dependências internas: orgaudi.domain (apenas para SEV_PALETA → Severidade)
Dependências externas: reportlab
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .domain import Severidade


# ═══════════════════════════════════════════════════════════════════════════════
#  PALETA INSTITUCIONAL ORGATEC
# ═══════════════════════════════════════════════════════════════════════════════

# Azuis (identidade ORGATEC)
AZUL          = colors.HexColor("#003365")
AZUL_M        = colors.HexColor("#185FA5")
AZUL_CL       = colors.HexColor("#3F88D5")
BRANCO        = colors.white

# ── Facelift v2.4.1 — Acento dourado ORGATEC ─────────────────────────────────
OURO          = colors.HexColor("#C08B18")   # dourado institucional
OURO_CL       = colors.HexColor("#F5D67A")   # dourado claro (backgrounds)
OURO_BG       = colors.HexColor("#FFFBEF")   # fundo âmbar suave
AZUL_DEEP     = colors.HexColor("#001F3F")   # azul profundo para capa
# ─────────────────────────────────────────────────────────────────────────────

# Cinzas e fundos neutros
CBG_LIGHT     = colors.HexColor("#F8FAFC")
CBG           = colors.HexColor("#EEF3F9")
CBORD         = colors.HexColor("#D6E0EC")
CBORD_LIGHT   = colors.HexColor("#E8EEF5")
CTXT          = colors.HexColor("#475569")
CTXT_DARK     = colors.HexColor("#1E293B")

# Severidades — cor principal + fundo claro + borda média
CRITICO       = colors.HexColor("#B91C1C")
CRITICO_BG    = colors.HexColor("#FEF2F2")
CRITICO_BORD  = colors.HexColor("#FCA5A5")
ALTO          = colors.HexColor("#B45309")
ALTO_BG       = colors.HexColor("#FFFBEB")
ALTO_BORD     = colors.HexColor("#FCD34D")
MEDIO         = colors.HexColor("#1D4ED8")
MEDIO_BG      = colors.HexColor("#EFF6FF")
MEDIO_BORD    = colors.HexColor("#93C5FD")
ATENCAO       = colors.HexColor("#7C3AED")
ATENCAO_BG    = colors.HexColor("#F5F3FF")
ATENCAO_BORD  = colors.HexColor("#C4B5FD")
CONFORME      = colors.HexColor("#15803D")
CONFORME_BG   = colors.HexColor("#F0FDF4")
CONFORME_BORD = colors.HexColor("#86EFAC")

# Mapas severidade → (cor, bg, bord)
SEV_PALETA = {
    Severidade.CRITICO:  (CRITICO,  CRITICO_BG,  CRITICO_BORD),
    Severidade.ALTO:     (ALTO,     ALTO_BG,     ALTO_BORD),
    Severidade.MEDIO:    (MEDIO,    MEDIO_BG,    MEDIO_BORD),
    Severidade.ATENCAO:  (ATENCAO,  ATENCAO_BG,  ATENCAO_BORD),
    Severidade.CONFORME: (CONFORME, CONFORME_BG, CONFORME_BORD),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  DIMENSÕES DE PÁGINA
# ═══════════════════════════════════════════════════════════════════════════════

PW, PH = A4
W = PW - 28 * mm  # largura útil considerando margens 14mm de cada lado


# ═══════════════════════════════════════════════════════════════════════════════
#  RESOLUÇÃO DE LOGOS (assets locais)
# ═══════════════════════════════════════════════════════════════════════════════

# Caminhos onde o sistema procura as logos. Inclui o diretório `assets/` do
# pacote (ideal para distribuição) e os caminhos legados (compatibilidade
# com o monolito orgaudi_v4_unified.py).
_ASSETS_DIR = Path(__file__).parent / "assets"
_LOGO_SEARCH_PATHS = (
    str(_ASSETS_DIR),
    "/home/claude",
    "/mnt/user-data/uploads",
    ".",
)


def _logo_path(nome: str) -> str:
    """Procura o arquivo nos caminhos conhecidos. Retorna '' se não encontrar."""
    for base in _LOGO_SEARCH_PATHS:
        p = Path(base) / nome
        if p.exists():
            return str(p)
    return ""


def _get_logo_t() -> str:
    """Resolve logo transparente (fundo transparente) — lazy."""
    return _logo_path("logo_oficial_transp.png")


def _get_logo_h() -> str:
    """Resolve logo para header (fundo #003365) — lazy."""
    return _logo_path("logo_oficial_header.png")


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPER GENÉRICO DE ESTILO DE PARÁGRAFO
# ═══════════════════════════════════════════════════════════════════════════════

def S(n, **k):
    """Cria um ParagraphStyle nomeado com defaults sensatos."""
    d = dict(fontName="Helvetica", fontSize=8.5, textColor=CTXT_DARK, leading=12)
    d.update(k)
    return ParagraphStyle(n, **d)


# Dicionário de estilos nomeados — referenciado pelo nome em todo o pacote
ST = {
    "h1":      S("h1",  fontName="Helvetica-Bold", fontSize=22, textColor=AZUL,    alignment=TA_CENTER, spaceAfter=2,  leading=26),
    "h2":      S("h2",  fontName="Helvetica-Bold", fontSize=14, textColor=AZUL,    alignment=TA_CENTER, spaceAfter=4,  leading=17),
    "kicker":  S("k",   fontName="Helvetica-Bold", fontSize=8,  textColor=AZUL_CL, alignment=TA_CENTER, spaceAfter=4),
    "sub":     S("s",   fontName="Helvetica",      fontSize=9.5, textColor=CTXT,   alignment=TA_CENTER, spaceAfter=8,  leading=13),
    "sec":     S("sc",  fontName="Helvetica-Bold", fontSize=10, textColor=AZUL_M,  spaceBefore=4, spaceAfter=3, leading=13),
    "subsec":  S("ss",  fontName="Helvetica-Bold", fontSize=9,  textColor=AZUL_M,  spaceBefore=4, spaceAfter=2),
    "body":    S("b",   fontName="Helvetica",      fontSize=8.5, textColor=CTXT_DARK, leading=12.5, spaceAfter=4, alignment=TA_JUSTIFY),
    "small":   S("sm",  fontName="Helvetica",      fontSize=7.5, textColor=CTXT, leading=11),
    "kpi_lab": S("kl",  fontName="Helvetica",      fontSize=7,  textColor=CTXT, alignment=TA_CENTER, leading=9),
    "kpi_sub": S("ks",  fontName="Helvetica",      fontSize=6.5, textColor=CTXT, alignment=TA_CENTER, leading=8),
    "an":      S("an",  fontName="Helvetica-Bold", fontSize=11, textColor=AZUL,    alignment=TA_CENTER, spaceAfter=1),
    "as":      S("as",  fontName="Helvetica",      fontSize=9,  textColor=CTXT,    alignment=TA_CENTER, spaceAfter=1),
    "ae":      S("ae",  fontName="Helvetica-Bold", fontSize=9.5, textColor=AZUL,   alignment=TA_CENTER, spaceAfter=1),
    "sys":     S("sy",  fontName="Helvetica-Bold", fontSize=10, textColor=AZUL_M,  alignment=TA_CENTER, spaceAfter=1),
    # v2.3.0 — Visual hierarchy: header de seção com tag colorida lateral
    "sec_v2":  S("sc2", fontName="Helvetica-Bold", fontSize=10, textColor=AZUL,    spaceBefore=2, spaceAfter=2, leading=13),
}


def section_header(label: str, accent_color=None, icon: str = ""):
    """
    Header de seção v2.4.1 — barra espessa à esquerda + fundo suave.

    Melhorias v2.4.1:
    - Barra lateral 4px (era 3px)
    - Bordas finas superior/inferior para definição
    - Padding generoso (5 vs 4mm)
    - Suporte a ícone/prefixo opcional
    """
    if accent_color is None:
        accent_color = AZUL_M
    lbl = f"<b>{icon}{label}</b>" if icon else f"<b>{label}</b>"
    t = Table(
        [[Paragraph(lbl, ST["sec_v2"])]],
        colWidths=[None],
    )
    t.setStyle(TableStyle([
        ("LINEBEFORE",    (0, 0), (0, -1),  4,    accent_color),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.25, CBORD),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.25, CBORD),
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return t


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE PARAGRAPH E TABELA
# ═══════════════════════════════════════════════════════════════════════════════

def th(t, align=TA_LEFT, size=7.5):
    """Texto de cabeçalho de tabela (negrito, branco — usar com fundo azul)."""
    return Paragraph(f"<b>{t}</b>", S("th", fontName="Helvetica-Bold", fontSize=size,
                     textColor=BRANCO, alignment=align, leading=10))


def td(t, bold=False, color=None, align=TA_LEFT, size=8):
    """Texto de célula de tabela (cor própria — não substituível por TableStyle)."""
    if color is None:
        color = CTXT_DARK
    return Paragraph(str(t), S("td",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, textColor=color, alignment=align, leading=11))


def sp(h):
    """Spacer vertical em mm."""
    return Spacer(1, h * mm)


def hr(c=AZUL_M, t=0.8):
    """Linha horizontal divisória."""
    return HRFlowable(width="100%", thickness=t, color=c, spaceAfter=4)


def tsb(stripe=True):
    """Estilo base de tabela: cabeçalho azul + zebra opcional."""
    s = [
        ("BACKGROUND",     (0, 0), (-1, 0),    AZUL),
        ("TEXTCOLOR",      (0, 0), (-1, 0),    BRANCO),
        ("FONTNAME",       (0, 0), (-1, 0),    "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1),   8),
        ("GRID",           (0, 0), (-1, -1),   0.25, CBORD),
        ("VALIGN",         (0, 0), (-1, -1),   "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1),   4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1),   4),
        ("LEFTPADDING",    (0, 0), (-1, -1),   5),
        ("RIGHTPADDING",   (0, 0), (-1, -1),   5),
    ]
    if stripe:
        s.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [BRANCO, CBG]))
    return TableStyle(s)


def tfoot():
    """Comandos para destacar a última linha como total.

    ATENÇÃO: TEXTCOLOR aqui só afeta strings simples. Para Paragraph (que é
    o que `td()` cria), passe `color=BRANCO` explicitamente em cada célula da
    linha de TOTAL. Caso contrário o texto fica invisível (preto sobre azul).
    """
    return [
        ("BACKGROUND", (0, -1), (-1, -1), AZUL),
        ("TEXTCOLOR",  (0, -1), (-1, -1), BRANCO),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPONENTES VISUAIS REUTILIZÁVEIS
# ═══════════════════════════════════════════════════════════════════════════════

def kpi_card(label, value, sub="", color=AZUL, width=None):
    """Card KPI v2.4.1 — label + valor grande + sublabel.

    Facelift: valor aumentado para 12pt (era 10.5), padding mais generoso.
    """
    if width is None:
        width = 38 * mm
    inner = Table([
        [Paragraph(f"<b>{label}</b>", ST["kpi_lab"])],
        [Paragraph(f"<b>{value}</b>", S("kv3", fontName="Helvetica-Bold", fontSize=12,
                   textColor=color, alignment=TA_CENTER, leading=14))],
        [Paragraph(sub, ST["kpi_sub"])],
    ], colWidths=[width - 3 * mm])
    inner.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (0, 0),   6),
        ("BOTTOMPADDING", (0, 2), (0, 2),   6),
    ]))
    return inner


def kpi_row(cards_data, accent_colors=None):
    """Linha de 4 KPIs v2.4.1 — barra superior colorida + fundo ligeiramente elevado.

    Facelift: barra superior 5px (era 3px), separação lateral entre cards,
    padding vertical maior.
    """
    if accent_colors is None:
        accent_colors = [AZUL] * 4
    n = len(cards_data)
    cards = [[kpi_card(*c) for c in cards_data]]
    t = Table(cards, colWidths=[W / n] * n)
    style = [
        ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, CBORD),
    ]
    for i, color in enumerate(accent_colors):
        style.append(("LINEABOVE", (i, 0), (i, 0), 5, color))   # 5px (era 3px)
        style.append(("BOX",       (i, 0), (i, 0), 0.3, CBORD))
    t.setStyle(TableStyle(style))
    return t


def achado_header(code, label, severidade: Severidade):
    """Cabeçalho de achado v2.4.1 — badge mais largo + borda superior espessa.

    Facelift: badge de código ampliado (28mm), borda superior em cor de
    severidade com 1.5px, tornando o achado mais imponente.
    """
    sev_color, sev_bg, sev_bord = SEV_PALETA[severidade]
    t = Table([[
        Paragraph(f"<b>{code}</b>", S("ahc", fontName="Helvetica-Bold", fontSize=10.5,
                  textColor=BRANCO, alignment=TA_CENTER, leading=13)),
        Paragraph(f"<b>{label}</b>", S("ahl", fontName="Helvetica-Bold", fontSize=9.5,
                  textColor=AZUL, alignment=TA_LEFT, leading=12)),
    ]], colWidths=[28 * mm, None])                         # era 24mm → 28mm
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),   sev_color),
        ("BACKGROUND",    (1, 0), (1, 0),   sev_bg),
        ("LINEABOVE",     (0, 0), (-1, 0),  1.5, sev_color),   # espessa + cor sólida
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, sev_bord),
        ("LINEAFTER",     (1, 0), (1, 0),   0.5, sev_bord),
        ("LINEBEFORE",    (0, 0), (0, 0),   0.5, sev_bord),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),               # era 6 → 7
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return t


def info_box(txt, label="", border_color=AZUL_M, bg=CBG_LIGHT):
    """Caixa com borda lateral colorida + label opcional."""
    elementos = []
    if label:
        elementos.append([Paragraph(f"<b>{label}</b>", S("lab",
            fontName="Helvetica-Bold", fontSize=7.5,
            textColor=border_color, leading=9))])
    elementos.append([Paragraph(txt, S("bx",
        fontName="Helvetica", fontSize=8,
        textColor=CTXT_DARK, alignment=TA_JUSTIFY, leading=12))])
    t = Table(elementos, colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("LINEBEFORE",    (0, 0), (0, -1),  3, border_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return t


def sev_card(sev_label, qtd, conclusao, severidade: Severidade):
    """Card horizontal de severidade — usado no Mapa de Achados (capa)."""
    color, bg, bord = SEV_PALETA[severidade]
    badge = Paragraph(f"<b>{sev_label}</b>", S("sb",
        fontName="Helvetica-Bold", fontSize=8.5,
        textColor=BRANCO, alignment=TA_CENTER, leading=11))
    qtd_p = Paragraph(f"<b>{qtd}</b>", S("sq",
        fontName="Helvetica-Bold", fontSize=14,
        textColor=color, alignment=TA_CENTER, leading=16))
    desc = Paragraph(conclusao, S("sd",
        fontName="Helvetica", fontSize=8,
        textColor=CTXT_DARK, alignment=TA_LEFT, leading=11))
    t = Table([[badge, qtd_p, desc]], colWidths=[26 * mm, 12 * mm, W - 38 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0),   color),
        ("BACKGROUND",    (1, 0), (2, 0),   bg),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.4, bord),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, bord),
        ("LINEAFTER",     (2, 0), (2, 0),   0.4, bord),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    return t


def risk_strip(risco_label: str, risco_color, subtexto: str = ""):
    """
    Faixa full-width de nível de risco — v2.4.1 (novo componente).

    Exibe o nível global de risco da auditoria em destaque cromático.
    Usado na capa, imediatamente abaixo da tabela de identificação.

    Args:
        risco_label:  texto principal, ex. "CRÍTICO — 2 achado(s)"
        risco_color:  cor semântica (CRITICO / ALTO / ATENCAO / CONFORME)
        subtexto:     info secundária exibida à direita, ex. "OrgAudi 1.0"
    """
    _BG_MAP = {
        CRITICO:  colors.HexColor("#7F1D1D"),
        ALTO:     colors.HexColor("#78350F"),
        ATENCAO:  colors.HexColor("#4C1D95"),
        CONFORME: colors.HexColor("#14532D"),
    }
    bg_dark = _BG_MAP.get(risco_color, AZUL_DEEP)

    t = Table([[
        Paragraph(
            f"<b>NÍVEL DE RISCO  ·  {risco_label}</b>",
            S("rs_l", fontName="Helvetica-Bold", fontSize=9.5,
              textColor=BRANCO, alignment=TA_LEFT, leading=12)),
        Paragraph(
            subtexto or "OrgAudi 1.0  ·  ORGATEC",
            S("rs_r", fontName="Helvetica", fontSize=7.5,
              textColor=colors.HexColor("#CBD5E1"),
              alignment=TA_RIGHT, leading=10)),
    ]], colWidths=[W * 0.62, W * 0.38])

    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), risco_color),
        # Fundo mais escuro no lado direito
        ("BACKGROUND",    (1, 0), (1, 0),   bg_dark),
        # Borda dourada superior
        ("LINEABOVE",     (0, 0), (-1, 0),  2.0, OURO),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.5, bg_dark),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    return t


def divider_section(title: str, accent_color=None):
    """
    Separador de seção premium — v2.4.1 (novo componente).

    Linha dupla com título centralizado, para marcar transições entre
    grandes blocos de conteúdo (ex.: Análise Forense → Recomendações).
    """
    if accent_color is None:
        accent_color = AZUL_M
    t = Table([[
        Paragraph(
            f"<b>— {title} —</b>",
            S("ds", fontName="Helvetica-Bold", fontSize=8,
              textColor=accent_color, alignment=TA_CENTER, leading=10)),
    ]])
    t.setStyle(TableStyle([
        ("LINEABOVE",  (0, 0), (-1, 0), 1.0, accent_color),
        ("LINEBELOW",  (0, 0), (-1, 0), 0.3, CBORD),
        ("BACKGROUND", (0, 0), (-1, -1), BRANCO),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def etapa_card(num, titulo, prazo, lista, accent=AZUL_CL):
    """Card de etapa com badge numérico + prazo + lista (página 5 — opcional)."""
    badge = Table(
        [[Paragraph(f"<b>{num}</b>", S("etn", fontName="Helvetica-Bold",
                    fontSize=18, textColor=BRANCO, alignment=TA_CENTER, leading=20))]],
        colWidths=[14 * mm], rowHeights=[14 * mm])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
    ]))

    titulo_p = Paragraph(f"<b>{titulo}</b>", S("ett",
        fontName="Helvetica-Bold", fontSize=10, textColor=AZUL, leading=12))
    prazo_p = Paragraph(f"<b>{prazo}</b>", S("etp",
        fontName="Helvetica-Bold", fontSize=8, textColor=BRANCO,
        alignment=TA_CENTER, leading=10))
    prazo_t = Table([[prazo_p]], colWidths=[20 * mm])
    prazo_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), accent),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    head = Table([[titulo_p, prazo_t]], colWidths=[None, 20 * mm])
    head.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, 0),   0),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 0),
    ]))

    body_txt = "".join(
        f"<font color='#{accent.hexval()[2:]}'>•</font> {i}<br/><br/>"
        for i in lista)
    body = Paragraph(body_txt, S("etb",
        fontName="Helvetica", fontSize=8.5,
        textColor=CTXT_DARK, leading=12, alignment=TA_JUSTIFY))

    direita = Table([[head], [body]], colWidths=[W - 14 * mm - 3 * mm])
    direita.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))

    container = Table([[badge, direita]], colWidths=[14 * mm, W - 14 * mm])
    container.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    return container
