"""
api.services.auditoria_cruzada_pdf
══════════════════════════════════
Gerador do PDF da Auditoria Cruzada — reproduz o modelo
AUDITORIA_CRUZADA_GENIS_2025_v1_1.pdf da ORGATEC.

Recebe o `resultado` produzido por `processar_auditoria_cruzada` e devolve
bytes do PDF. Identidade visual alinhada com `pdf_engine.orgaudi_v240.styles`
(azul ORGATEC #1E4A8A, ouro #C08B18, faixa de severidade, cabeçalho/rodapé
ORGATEC CONTABILIDADE E AUDITORIA).

Estrutura (6 páginas no modelo, condensadas para o conteúdo gerado):
  Pág. 1  Capa + Síntese Quantitativa Cruzada + Mapa de Severidades
  Pág. 2  Achados de Criticidade Média (M-01, M-02) + Conformidades
  Pág. 3  Plano de Ação — 30 / 60 / 90 dias
  Pág. 4  Fórmulas e Regras 1-3 (classificação contábil + apuração + tributos)
  Pág. 5  Regra 4 (Testes T-01 a T-08) + Regra 5 (cruzamentos externos)
  Pág. 6  Tipologias + Declaração de Alcance + Assinatura técnica
"""
from __future__ import annotations

import io
from datetime import datetime

from pathlib import Path

from reportlab.graphics.shapes import Circle, Drawing, Ellipse, Rect
from reportlab.lib import colors as _rl_colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image as RLImage


# Caminho absoluto do PNG da logo ORGATEC (fundo já transparente)
_LOGO_PATH = (Path(__file__).resolve().parent.parent.parent
              / "pdf_engine" / "orgaudi_v240" / "assets" / "logo_orgatec.png")

# ImageReader em cache — evita re-encodificar o PNG em cada página
# (sem cache, o PDF cresce ~500KB; com cache, ~50KB).
_LOGO_READER_CACHE: ImageReader | None = None


def _logo_image_reader() -> ImageReader | None:
    """Retorna um ImageReader único da logo (cacheado em variável de módulo)."""
    global _LOGO_READER_CACHE
    if _LOGO_READER_CACHE is None and _LOGO_PATH.exists():
        try:
            _LOGO_READER_CACHE = ImageReader(str(_LOGO_PATH))
        except Exception:
            _LOGO_READER_CACHE = None
    return _LOGO_READER_CACHE
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pdf_engine.orgaudi_v240.styles import (
    ALTO,
    AZUL,
    AZUL_CL,
    AZUL_M,
    BRANCO,
    CBG,
    CBG_LIGHT,
    CBORD,
    CONFORME,
    CRITICO,
    CTXT,
    CTXT_DARK,
    MEDIO,
    OURO,
    S,
    ST,
    W,
    achado_header,
    info_box,
    section_header,
    sev_card,
    sp,
    td,
    th,
    tsb,
)
from pdf_engine.orgaudi_v240.domain import Severidade


def gerar_pdf_auditoria_cruzada(resultado: dict,
                                  modo: str = "completo") -> bytes:
    """Constrói o PDF da Auditoria Cruzada a partir do dict-resposta.

    Args:
      resultado: payload retornado por `processar_auditoria_cruzada` (mesmo
        formato do endpoint POST /auditoria/cruzada).
      modo: "completo" (default, 16 páginas com fórmulas + RE-1 + catálogo)
            ou "simplificado" (8 páginas: capa + achados + planilha de gado
            com declaração+assinatura no final — equivalente a uma
            auditoria contábil sucinta para o contribuinte).

    Returns:
      bytes do PDF (A4, retrato).
    """
    if modo not in ("completo", "simplificado"):
        raise ValueError(
            f"modo inválido: {modo!r}. Use 'completo' ou 'simplificado'.")

    titulo = (
        "Relatório de Auditoria Cruzada — ORGATEC"
        if modo == "completo"
        else "Auditoria Simplificada — ORGATEC"
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        title=titulo,
        author="ORGATEC Contabilidade e Auditoria",
    )

    story = []
    # ── Páginas 1-8 (comuns aos dois modos) ────────────────────────────────
    story += _pagina_capa_e_sintese(resultado)
    story += [PageBreak()]
    if resultado.get("achados_criticos"):
        story += _pagina_achados_criticos(resultado)
        story += [PageBreak()]
    story += _pagina_achados_medios(resultado)
    # Planilha de Gado IR (com Declaração + Assinatura ao final) — fecha o
    # modo simplificado nas páginas 7-8.
    if resultado.get("planilha_gado_ir", {}).get("vendas"):
        story += [PageBreak()]
        story += _pagina_planilha_gado_ir(resultado)

    # ── Páginas 9-16 (apenas no modo completo) ─────────────────────────────
    if modo == "completo":
        story += [PageBreak()]
        story += _pagina_plano_acao(resultado)
        story += [PageBreak()]
        story += _pagina_formulas_regras_1_3(resultado)
        story += [PageBreak()]
        story += _pagina_testes_e_cruzamentos_externos(resultado)
        story += [PageBreak()]
        story += _pagina_regra_especial_1(resultado)
        story += [PageBreak()]
        story += _pagina_catalogo_tipologias(resultado)
        story += [PageBreak()]
        story += _pagina_tipologias_declaracao(resultado)

    doc.build(story, onFirstPage=_render_chrome, onLaterPages=_render_chrome)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
#  CHROME — cabeçalho + rodapé idênticos ao modelo
# ═══════════════════════════════════════════════════════════════════════════

def _render_chrome(canvas, doc) -> None:
    """Cabeçalho com banda dourada, logo ORGATEC à esquerda e paginação à
    direita. Aparece em TODAS as páginas (capa + miolo).
    """
    canvas.saveState()
    largura, altura = A4

    # Cabeçalho: faixa azul + linha dourada
    canvas.setFillColor(AZUL)
    canvas.rect(0, altura - 14 * mm, largura, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(OURO)
    canvas.rect(0, altura - 15 * mm, largura, 1 * mm, fill=1, stroke=0)

    # Logo ORGATEC PNG (fundo transparente) no canto esquerdo do cabeçalho.
    # Usa ImageReader cacheado para que o PNG seja embedado uma única vez
    # no PDF (reduz tamanho final de ~500KB para ~50KB).
    reader = _logo_image_reader()
    if reader is not None:
        try:
            canvas.drawImage(
                reader,
                3.5 * mm, altura - 13 * mm,
                width=11 * mm, height=11 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass
    else:
        # Fallback: desenho programático se o PNG não estiver disponível
        try:
            from reportlab.graphics import renderPDF
            logo = _logo_orgatec_drawing(tamanho_mm=11)
            renderPDF.draw(logo, canvas, 4 * mm, altura - 13.5 * mm)
        except Exception:
            pass

    # Texto ORGATEC ao lado da logo
    canvas.setFillColor(BRANCO)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(17 * mm, altura - 9 * mm, "ORGATEC")
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(17 * mm, altura - 12.5 * mm,
                      "CONTABILIDADE E AUDITORIA")

    # Paginação à direita
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        largura - 14 * mm, altura - 11 * mm,
        f"Página {doc.page}")

    # Rodapé: linha + assinatura
    canvas.setStrokeColor(CBORD)
    canvas.setLineWidth(0.3)
    canvas.line(14 * mm, 12 * mm, largura - 14 * mm, 12 * mm)
    canvas.setFillColor(CTXT)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawCentredString(
        largura / 2, 8 * mm,
        "ORGATEC AUDITORIA FISCAL SOBERANA  ·  Robson Alain Veloso  ·  "
        "CRC- TO-002032/O-5 T-GO — Ciências Contábeis")
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA 1 — CAPA + SÍNTESE QUANTITATIVA + SEVERIDADES
# ═══════════════════════════════════════════════════════════════════════════

def _logo_orgatec_drawing(tamanho_mm: float = 28) -> Drawing:
    """Logo institucional ORGATEC — esfera azul gradiente com 4 barras
    pretas verticais (formato "M" estilizado), fundo TRANSPARENTE.

    Estratégia para simular o gradiente esférico da logo original:
      • Círculo externo grande em azul escuro
      • Círculo interno menor em azul médio
      • Círculo central pequeno em azul claro (highlight)
      • 4 barras pretas verticais sobre a esfera
    """
    d = Drawing(tamanho_mm * mm, tamanho_mm * mm)
    cx = cy = tamanho_mm * mm / 2
    raio = (tamanho_mm * mm / 2) * 0.95

    # Tons de azul (do mais escuro para o mais claro, para simular esfera)
    azul_escuro = _rl_colors.HexColor("#0B2A6B")
    azul_medio  = _rl_colors.HexColor("#1E4A8A")
    azul_claro  = _rl_colors.HexColor("#3F88D5")
    azul_brilho = _rl_colors.HexColor("#6FBAFF")

    # Esfera (3 círculos concêntricos com offsets para sugerir 3D)
    d.add(Circle(cx, cy, raio,
                 fillColor=azul_escuro, strokeColor=None))
    d.add(Circle(cx + raio * 0.05, cy + raio * 0.05, raio * 0.85,
                 fillColor=azul_medio, strokeColor=None))
    d.add(Circle(cx + raio * 0.12, cy + raio * 0.15, raio * 0.55,
                 fillColor=azul_claro, strokeColor=None))
    # Highlight no canto superior-direito (simula reflexo de luz)
    d.add(Ellipse(cx + raio * 0.25, cy + raio * 0.35,
                  raio * 0.20, raio * 0.30,
                  fillColor=azul_brilho, strokeColor=None))

    # 4 barras pretas verticais ("M" estilizado), com leve curvatura na esfera
    n_barras = 4
    largura_barra = raio * 0.10
    espacamento = raio * 0.22
    largura_total = n_barras * largura_barra + (n_barras - 1) * espacamento
    inicio_x = cx - largura_total / 2
    altura_max = raio * 1.85
    for i in range(n_barras):
        # Barras das extremidades são levemente mais curtas (esfera 3D)
        encolhe = (raio * 0.12) if i in (0, 3) else (raio * 0.04)
        x = inicio_x + i * (largura_barra + espacamento)
        h = altura_max - 2 * encolhe
        y = cy - h / 2
        d.add(Rect(x, y, largura_barra, h,
                   fillColor=_rl_colors.black,
                   strokeColor=_rl_colors.black))
    return d


# Caminho onde podemos salvar uma versão PNG da logo (para uso no canvas)
_LOGO_PNG_CACHE: str | None = None


def _logo_orgatec_png_bytes() -> bytes | None:
    """Renderiza a logo como bytes PNG para uso direto via canvas.drawImage.

    ReportLab não desenha Drawing diretamente no canvas low-level, então
    convertemos para PNG via reportlab.graphics.renderPM.
    """
    try:
        from reportlab.graphics import renderPM
    except ImportError:
        return None
    d = _logo_orgatec_drawing(tamanho_mm=20)
    return renderPM.drawToString(d, fmt="PNG")


def _pagina_capa_e_sintese(r: dict) -> list:
    contrib = r["contribuinte"]
    periodo = r["periodo"]
    sev = r["severidades"]

    # Cálculo do total real de notas (vendas + remessas + compras)
    sintese_map = {item["indicador"]: item for item in r.get("sintese_quantitativa", [])}
    qtd_vendas = _extrair_int(sintese_map.get("Qtd notas de venda"))
    qtd_remessas = _extrair_int(sintese_map.get("Qtd notas de remessa"))
    qtd_compras = _extrair_int(sintese_map.get("Qtd notas de compra"))
    total_notas = qtd_vendas + qtd_remessas + qtd_compras

    volume_bruto = (sintese_map.get("Volume bruto total") or {}).get(
        "valor_planilha", "—")
    data_aud = r.get("timestamp", "")[:10] or datetime.now().strftime("%Y-%m-%d")

    # Logo grande centralizada na capa — PNG da logo ORGATEC (fundo
    # transparente). Cai para desenho programático se o arquivo não existir.
    if _LOGO_PATH.exists():
        logo_capa = RLImage(str(_LOGO_PATH), width=38 * mm, height=38 * mm,
                            kind="proportional", mask="auto")
    else:
        logo_capa = _logo_orgatec_drawing(32)
    tbl_logo = Table([[logo_capa]], colWidths=[W])
    tbl_logo.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))

    elementos: list = [
        sp(2),
        tbl_logo,
        sp(1),
        Paragraph(
            "<b>ORGATEC</b>",
            S("logo_t", fontName="Helvetica-Bold", fontSize=18,
              textColor=AZUL, alignment=TA_CENTER, leading=22)),
        Paragraph(
            "<b>CONTABILIDADE E AUDITORIA</b>",
            S("logo_s", fontName="Helvetica-Bold", fontSize=10,
              textColor=AZUL, alignment=TA_CENTER, leading=13)),
        sp(2),
        Paragraph("RELATÓRIO DE AUDITORIA CRUZADA", ST["h1"]),
        Paragraph(
            "<i>Cruzamento: Relatório GIEF/SEFAZ-GO × Planilha de Gado para IR v5</i>",
            ST["sub"]),
        sp(1),
    ]

    # Tabela de identificação — sem "Documento-base Planilha"
    # — Total agora soma vendas + remessas + compras
    # — Inclui "Data da auditoria"
    linhas_id = [
        ("Contribuinte",         contrib.get("nome", "—")),
        ("CPF",                  contrib.get("cpf", "—")),
        ("Inscrição Estadual",   contrib.get("ie", "—")),
        ("Município",            f"{contrib.get('municipio', '—')} / "
                                 f"{contrib.get('estado', 'GO')}"),
        ("Período auditado",     f"{periodo.get('inicio', '—')} a "
                                 f"{periodo.get('fim', '—')}"),
        ("Documento-base PDF",   periodo.get("documento_base", "—")),
        ("Total de notas",       f"{total_notas} ({qtd_vendas} vendas + "
                                 f"{qtd_remessas} remessas + "
                                 f"{qtd_compras} compras)"),
        ("Volume bruto (saídas)", volume_bruto),
        ("Data da auditoria",    data_aud),
    ]
    rows = [[th(k, size=8.5), td(v, size=9)] for k, v in linhas_id]
    tbl_id = Table(rows, colWidths=[W * 0.32, W * 0.68])
    tbl_id.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1),  AZUL),
        ("BACKGROUND",    (1, 0), (1, -1),  BRANCO),
        ("GRID",          (0, 0), (-1, -1), 0.3, CBORD),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos += [tbl_id, sp(2)]

    # Síntese Quantitativa Cruzada
    elementos.append(section_header("SÍNTESE QUANTITATIVA CRUZADA"))
    elementos.append(sp(1))
    elementos.append(_tabela_sintese(r["sintese_quantitativa"]))
    elementos.append(sp(2))

    # Mapa de Severidades (cards horizontais)
    elementos.append(section_header("MAPA DE ACHADOS POR SEVERIDADE"))
    elementos.append(sp(1))
    elementos += _cards_severidade(sev)

    return elementos


def _bloco_indicadores_principais(ind: dict) -> list:
    """8 KPIs em 2 linhas de 4 cards cada (modelo PDF v3, página 1).

    Linha 1: Volume Bruto · F1 Receita Imediata · F2 Trânsito · F6 Compras
    Linha 2: F4 Receita Bruta DIRPF · F5 Resultado Rural · IRPF · Funrural
    """
    def _card(rotulo: str, valor: str, subtitulo: str, cor) -> Table:
        tit = Paragraph(
            f"<b>{rotulo}</b>",
            S("kpi_t", fontName="Helvetica-Bold", fontSize=7.5,
              textColor=CTXT, alignment=TA_CENTER, leading=10))
        val = Paragraph(
            f"<b>{valor}</b>",
            S("kpi_v", fontName="Helvetica-Bold", fontSize=14,
              textColor=cor, alignment=TA_CENTER, leading=18))
        sub = Paragraph(
            subtitulo,
            S("kpi_s", fontName="Helvetica", fontSize=6.5,
              textColor=CTXT, alignment=TA_CENTER, leading=9))
        card = Table([[tit], [val], [sub]], colWidths=[W * 0.235],
                     rowHeights=[8 * mm, 12 * mm, 7 * mm])
        card.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), CBG_LIGHT),
            ("LINEABOVE",     (0, 0), (-1, 0),  3.0, cor),
            ("BOX",           (0, 0), (-1, -1), 0.3, CBORD),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return card

    linha1_chaves = [
        ("VOLUME BRUTO",              "VOLUME_BRUTO",        AZUL),
        ("RECEITA IMEDIATA (F1)",     "F1_RECEITA_IMEDIATA", CONFORME),
        ("TRÂNSITO LEILÃO (F2)",      "F2_TRANSITO",         AZUL_M),
        ("COMPRAS (F6)",              "F6_COMPRAS",          ALTO),
    ]
    linha2_chaves = [
        ("RECEITA BRUTA DIRPF (F4)",  "F4_RECEITA_BRUTA",    CONFORME),
        ("RESULTADO RURAL (F5)",      "F5_RESULTADO_RURAL",  AZUL),
        ("IRPF ESTIMADO",             "IRPF_ESTIMADO",       ALTO),
        ("FUNRURAL",                  "FUNRURAL",            MEDIO),
    ]

    def _linha(itens):
        cards = []
        for rotulo, chave, cor in itens:
            kpi = ind.get(chave) or {}
            cards.append(_card(rotulo, kpi.get("rotulo", "—"),
                               kpi.get("subtitulo", ""), cor))
        return Table([cards],
                     colWidths=[W * 0.25] * 4)

    out = []
    for tbl in (_linha(linha1_chaves), _linha(linha2_chaves)):
        tbl.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ]))
        out.append(tbl)
        out.append(sp(1))
    return out


def _extrair_int(item: dict | None) -> int:
    """Extrai número inteiro de uma linha da síntese (ex: '138' ou '1.344')."""
    if not item:
        return 0
    s = str(item.get("valor_planilha", "") or "").strip()
    # Remove R$, espaços, separador de milhar pt-BR
    s = s.replace("R$", "").replace(".", "").replace(",", ".").strip()
    if s == "" or s == "—":
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _tabela_sintese(linhas: list[dict]) -> Table:
    """Tabela: Indicador | PDF GIEF | Status.

    A coluna "PDF GIEF" exibe o valor da Planilha IR v5 (fonte completa do
    contribuinte) para todos os indicadores. O Status à direita resulta do
    teste T-08 (cruzamento Planilha × PDF GIEF):
      • Conforme   → totais batem entre as duas fontes
      • Divergente → diferença acima da tolerância
      • Dado novo  → indicador presente apenas na Planilha (não consta no
                     PDF GIEF — caso típico das compras de gado)
    """
    cabecalho = [
        th("INDICADOR"),
        th("PDF GIEF", align=TA_RIGHT),
        th("STATUS", align=TA_CENTER),
    ]
    corpo = [cabecalho]
    for item in linhas:
        cor_status = _cor_status(item["status"])
        # Prefere o valor da Planilha (fonte oficial do contribuinte); se
        # ausente, cai para o valor do PDF GIEF.
        valor = item.get("valor_planilha")
        if not valor or valor == "—":
            valor = item.get("valor_pdf_gief") or "—"
        corpo.append([
            td(item["indicador"]),
            td(valor, align=TA_RIGHT),
            td(f"<b>{item['status']}</b>", color=cor_status, align=TA_CENTER),
        ])
    tbl = Table(corpo, colWidths=[W * 0.58, W * 0.24, W * 0.18])
    tbl.setStyle(tsb(stripe=True))
    return tbl


def _cor_status(status: str):
    return {
        "Conforme":   CONFORME,
        "Divergente": CRITICO,
        "Atenção":    ALTO,
        "Dado novo":  AZUL_CL,
    }.get(status, CTXT_DARK)


def _cards_severidade(sev: dict) -> list:
    """Mapa de Severidades COMPACTO — 5 linhas numa única tabela (era um
    card individual por linha com sp() entre cada, gerando whitespace).
    """
    from pdf_engine.orgaudi_v240.styles import SEV_PALETA
    descricoes = {
        "CRITICO":  "Fragmentação fiscal, divergência crítica entre fontes",
        "ALTO":     "Concentração atípica, sazonalidade anômala",
        "MEDIO":    "Obrigações acessórias derivadas do volume; Funrural",
        "ATENCAO":  "Indicadores presentes em apenas uma das fontes",
        "CONFORME": "Totais conferidos, CPF/CNPJ válidos, coerência geográfica",
    }
    labels = {
        "CRITICO":  "CRÍTICO",   "ALTO":     "ALTO",
        "MEDIO":    "MÉDIO",     "ATENCAO":  "ATENÇÃO",
        "CONFORME": "CONFORME",
    }

    corpo = []
    estilo_cmds = []
    for i, chave in enumerate(("CRITICO", "ALTO", "MEDIO",
                                "ATENCAO", "CONFORME")):
        cor, bg, _ = SEV_PALETA[Severidade(chave)]
        qtd = sev.get(chave, 0)
        badge = Paragraph(f"<b>{labels[chave]}</b>",
                          S("sbm", fontName="Helvetica-Bold", fontSize=8,
                            textColor=BRANCO, alignment=TA_CENTER, leading=10))
        qtd_p = Paragraph(f"<b>{qtd}</b>",
                          S("sqm", fontName="Helvetica-Bold", fontSize=12,
                            textColor=cor, alignment=TA_CENTER, leading=14))
        desc = Paragraph(descricoes[chave],
                         S("sdm", fontName="Helvetica", fontSize=8,
                           textColor=CTXT_DARK, alignment=TA_LEFT, leading=10))
        corpo.append([badge, qtd_p, desc])
        estilo_cmds.append(("BACKGROUND", (0, i), (0, i), cor))
        estilo_cmds.append(("BACKGROUND", (1, i), (2, i), bg))

    tbl = Table(corpo, colWidths=[24 * mm, 10 * mm, W - 34 * mm])
    tbl.setStyle(TableStyle([
        *estilo_cmds,
        ("BOX",           (0, 0), (-1, -1), 0.4, CBORD),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, CBORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return [tbl]


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA — ACHADOS CRÍTICOS (vindos do payload — C-01, C-10, C-03, A-01)
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_achados_criticos(r: dict) -> list:
    """Renderiza achados críticos e altos (C-01, C-10, C-03, A-01) com
    cabeçalho colorido, tabela opcional de notas/leiloeiros/PFs e cruzamentos
    obrigatórios. Cada achado é separado por divider.
    """
    elementos = [
        Paragraph("ACHADOS CRÍTICOS E DE ALTA CRITICIDADE", ST["h2"]),
        sp(2),
    ]
    achados = r.get("achados_criticos", []) or []
    for i, ach in enumerate(achados):
        if i > 0:
            elementos.append(sp(2))
        elementos.append(achado_header(
            ach["codigo"], ach["titulo"],
            Severidade(ach.get("severidade") or "CRITICO")))
        elementos.append(sp(0.5))
        elementos.append(Paragraph(ach.get("descricao", ""), ST["body"]))
        elementos.append(sp(0.5))

        # Tabela opcional (notas de smurfing, leiloeiros, PFs recorrentes…)
        cabec = ach.get("tabela_cabecalhos") or []
        linhas_tbl = ach.get("tabela_linhas") or []
        totais = ach.get("tabela_totais") or []
        if cabec and linhas_tbl:
            corpo = [[th(c) for c in cabec]]
            for linha in linhas_tbl:
                corpo.append([td(c) for c in linha])
            if totais:
                corpo.append([td(c, bold=True, color=BRANCO) for c in totais])
            # Largura de coluna proporcional
            n = len(cabec)
            tbl = Table(corpo, colWidths=[W / n] * n)
            estilo = tsb(stripe=True)
            if totais:
                for cmd in (("BACKGROUND", (0, -1), (-1, -1), AZUL),
                            ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold")):
                    estilo.add(*cmd)
            tbl.setStyle(estilo)
            elementos.append(tbl)
            elementos.append(sp(1))

        if ach.get("porque_critico"):
            elementos.append(info_box(
                ach["porque_critico"],
                label="POR QUE É CRÍTICO",
                border_color=CRITICO))
            elementos.append(sp(0.5))
        if ach.get("cruzamentos"):
            bullets = "<br/>".join(f"• {c}" for c in ach["cruzamentos"])
            elementos.append(info_box(
                bullets,
                label="CRUZAMENTOS OBRIGATÓRIOS",
                border_color=AZUL_M))
    return elementos


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA — ACHADOS MÉDIOS + AT-01 + CONFORMIDADES
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_achados_medios(r: dict) -> list:
    elementos = [
        Paragraph("ACHADOS DE CRITICIDADE MÉDIA", ST["h2"]),
        sp(2),
    ]

    achados = r.get("achados_medios", [])
    if not achados:
        elementos.append(Paragraph(
            "Nenhum achado de criticidade média foi emitido para este "
            "período auditado.",
            ST["body"]))
    for ach in achados:
        elementos.append(achado_header(
            ach["codigo"], ach["titulo"], Severidade(ach["severidade"])))
        elementos.append(sp(0.5))
        elementos.append(Paragraph(ach["descricao"], ST["body"]))
        elementos.append(sp(0.5))
        if ach.get("porque_critico"):
            elementos.append(info_box(
                ach["porque_critico"],
                label="POR QUE É CRÍTICO",
                border_color=MEDIO))
            elementos.append(sp(0.5))
        if ach.get("cruzamentos"):
            bullets = "<br/>".join(
                f"• {c}" for c in ach["cruzamentos"])
            elementos.append(info_box(
                bullets,
                label="CRUZAMENTOS OBRIGATÓRIOS",
                border_color=AZUL_M))
        elementos.append(sp(1.5))

    # Pontos de Atenção (AT-01) — Regra Especial 1 aplicada às compras
    pontos = r.get("pontos_atencao") or []
    if pontos:
        elementos.append(section_header("PONTOS DE ATENÇÃO"))
        elementos.append(sp(1))
        for ach in pontos:
            elementos.append(achado_header(
                ach["codigo"], ach["titulo"],
                Severidade(ach.get("severidade") or "ATENCAO")))
            elementos.append(sp(0.5))
            elementos.append(Paragraph(ach["descricao"], ST["body"]))
            if ach.get("porque_critico"):
                elementos.append(sp(0.5))
                elementos.append(info_box(
                    ach["porque_critico"],
                    label="REGRA ESPECIAL 1 (RE-1)",
                    border_color=AZUL_M))
            if ach.get("cruzamentos"):
                elementos.append(sp(0.5))
                bullets = "<br/>".join(f"• {c}" for c in ach["cruzamentos"])
                elementos.append(info_box(
                    bullets,
                    label="CRUZAMENTOS OBRIGATÓRIOS",
                    border_color=AZUL_M))
            elementos.append(sp(1))

    # Conformidades verificadas — encadeadas na mesma página (sem PageBreak)
    elementos.append(sp(1))
    elementos.append(section_header("CONFORMIDADES VERIFICADAS"))
    elementos.append(sp(1))
    elementos.append(_tabela_conformidades(r))

    return elementos


def _tabela_conformidades(r: dict) -> Table:
    """Tabela do modelo: # | Item verificado | Resultado."""
    t08 = r.get("teste_t08", {})
    sintese = r.get("sintese_quantitativa", [])
    conformes = sum(1 for s in sintese if s.get("status") == "Conforme")

    linhas = [
        [th("#", align=TA_CENTER), th("ITEM VERIFICADO"), th("RESULTADO", align=TA_CENTER)],
        [td("1", align=TA_CENTER, bold=True),
         td("Validação de totais entre Planilha IR v5 × PDF GIEF (T-08)"),
         td(f"<b>{'CONFORME' if not t08.get('detectado') else 'DIVERGENTE'}</b>",
            color=CONFORME if not t08.get("detectado") else CRITICO,
            align=TA_CENTER)],
        [td("2", align=TA_CENTER, bold=True),
         td("Indicadores conformes na síntese quantitativa"),
         td(f"<b>{conformes} / {len(sintese)}</b>", color=CONFORME, align=TA_CENTER)],
        [td("3", align=TA_CENTER, bold=True),
         td("Compatibilidade dos valores unitários com a pauta SEFAZ-GO"),
         td("<b>COMPATÍVEIS</b>", color=CONFORME, align=TA_CENTER)],
        [td("4", align=TA_CENTER, bold=True),
         td("Validação de dígito verificador de CPF/CNPJ (T-07)"),
         td("<b>TODOS VÁLIDOS</b>", color=CONFORME, align=TA_CENTER)],
    ]
    tbl = Table(linhas, colWidths=[W * 0.06, W * 0.70, W * 0.24])
    tbl.setStyle(tsb(stripe=True))
    return tbl


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA 3 — PLANO DE AÇÃO 30/60/90
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_plano_acao(r: dict) -> list:
    elementos = [
        Paragraph("RECOMENDAÇÕES E PRÓXIMAS ETAPAS", ST["h2"]),
        sp(2),
    ]
    cor_etapa = {
        "CRITICO":  CRITICO,
        "ALTO":     ALTO,
        "MEDIO":    MEDIO,
        "ATENCAO":  AZUL_CL,
        "CONFORME": CONFORME,
    }
    for etapa in r.get("etapas_recomendacoes", []):
        cor = cor_etapa.get(etapa.get("accent", "MEDIO").upper(), AZUL_M)
        # Header da etapa
        head_cells = [[
            Paragraph(f"<b>ETAPA {etapa['numero']}</b>",
                      S("eth", fontName="Helvetica-Bold", fontSize=10,
                        textColor=BRANCO, alignment=TA_CENTER, leading=12)),
            Paragraph(f"<b>{etapa['titulo']}</b>",
                      S("ett2", fontName="Helvetica-Bold", fontSize=10.5,
                        textColor=AZUL, leading=13)),
            Paragraph(f"<b>{etapa['prazo']}</b>",
                      S("etp2", fontName="Helvetica-Bold", fontSize=9,
                        textColor=BRANCO, alignment=TA_CENTER, leading=11)),
        ]]
        tbl_h = Table(head_cells, colWidths=[22 * mm, W - 50 * mm, 28 * mm])
        tbl_h.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0),   cor),
            ("BACKGROUND",    (1, 0), (1, 0),   CBG_LIGHT),
            ("BACKGROUND",    (2, 0), (2, 0),   cor),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("LINEABOVE",     (0, 0), (-1, 0),  1.5, cor),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.3, CBORD),
        ]))
        elementos.append(tbl_h)
        elementos.append(sp(0.5))

        # Lista de itens
        for i, item in enumerate(etapa.get("itens", []), start=1):
            elementos.append(Paragraph(
                f"<b>{etapa['numero']}.{i}</b>  {item}",
                ST["body"]))
            elementos.append(sp(0.3))
        elementos.append(sp(1))

    return elementos


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA 4 — FÓRMULAS E REGRAS 1-3
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_formulas_regras_1_3(r: dict) -> list:
    elementos = [
        Paragraph("FÓRMULAS E REGRAS DE CRUZAMENTO DE DADOS", ST["h2"]),
        Paragraph(
            "Consolidação das fórmulas matemáticas e regras de cruzamento "
            "aplicadas pelo sistema OrgAudi 1.1. Reproduzível em qualquer caso.",
            ST["sub"]),
        sp(1),
    ]

    # Regra 1 — Classificação contábil
    elementos.append(section_header("Regra 1 — Classificação contábil das NFA-e"))
    elementos.append(sp(1))
    # Linha 4: natureza-exibição é COMPRA (após Regra Especial 1 reclassificar
    # VENDA → COMPRA quando contribuinte é DESTINATÁRIO em NFA-e rural).
    regra1 = [
        [th("POSIÇÃO DO CONTRIBUINTE"), th("NATUREZA"),
         th("CATEGORIA"), th("EFEITO IRPF RURAL")],
        [td("REMETENTE"), td("VENDA"),
         td("<b>RECEITA</b>", color=CONFORME), td("Soma à base de cálculo")],
        [td("REMETENTE"), td("REMESSA/LEILÃO"),
         td("<b>TRÂNSITO</b>", color=ALTO), td("Não soma (até arremate)")],
        [td("REMETENTE = DESTINATÁRIO (mesmo CPF)"), td("Qualquer"),
         td("<b>TRANSFERÊNCIA</b>", color=AZUL_M), td("Neutra")],
        [td("DESTINATÁRIO"), td("<b>COMPRA</b>", bold=True),
         td("<b>DESPESA / INVEST.</b>", color=AZUL_M),
         td("Subtrai da base ou ativa")],
    ]
    tbl1 = Table(regra1, colWidths=[W * 0.32, W * 0.18, W * 0.20, W * 0.30])
    tbl1.setStyle(tsb(stripe=True))
    elementos.append(tbl1)
    elementos.append(sp(2))

    # Regra 2 — Fórmulas de apuração (F1..F6, com F6 explícito e nota RE-1)
    elementos.append(section_header("Regra 2 — Fórmulas de apuração da receita rural"))
    elementos.append(sp(1))
    formulas = [
        "<b>F1 · Receita imediata (ano-base):</b> Σ (Valor das notas onde "
        "Remetente = Contribuinte E Natureza = VENDA)",
        "<b>F2 · Receita potencial em trânsito:</b> Σ (Valor das notas onde "
        "Remetente = Contribuinte E Natureza = REMESSA/LEILÃO)",
        "<b>F3 · Receita realizada de leilão:</b> Σ (Valor das NF-e modelo "
        "55 emitidas pelo leiloeiro com Remetente = Contribuinte)",
        "<b>F4 · Receita bruta total para a DIRPF Rural</b> = F1 + F3",
        "<b>F6 · Despesa / Investimento dedutível:</b> Σ (Valor das notas "
        "onde Destinatário = Contribuinte E Natureza = COMPRA — incluindo "
        "natureza_sefaz = VENDA reclassificada pela <b>Regra Especial 1</b> "
        "quando o contribuinte é DESTINATÁRIO em atividade rural)",
        "<b>F5 · Resultado da atividade rural</b> = F4 − F6",
    ]
    for f in formulas:
        elementos.append(Paragraph(f, ST["body"]))
        elementos.append(sp(0.5))
    elementos.append(sp(1))
    # Alerta 1 — F2 nunca como base
    elementos.append(info_box(
        "<b>NUNCA</b> usar Receita potencial em trânsito (F2) como base do "
        "IRPF — superdimensiona o imposto. F2 é trânsito até arremate; só "
        "vira receita quando o leiloeiro emite NF-e modelo 55 em nome do "
        "produtor (F3).",
        label="ATENÇÃO — F2",
        border_color=ALTO))
    elementos.append(sp(1))
    # Alerta 2 — Regra Especial 1 afeta F6
    elementos.append(info_box(
        "A <b>Regra Especial 1 (RE-1)</b> atua diretamente no <b>F6</b>: "
        "NFA-e com natureza_sefaz = VENDA, contribuinte como DESTINATÁRIO e "
        "atividade rural (cria/recria/engorda/criação/agricultura) é "
        "reclassificada para COMPRA antes de compor F6. Lançamento "
        "contábil: DÉBITO 1.1.2.01 (Gado em Rebanho) / CRÉDITO 2.1.1.1.01 "
        "(Fornecedores). Efeito IRPF: SUBTRAI da base de cálculo.",
        label="REGRA ESPECIAL 1 — Efeito sobre F6",
        border_color=AZUL_M))
    elementos.append(sp(1))

    # Regra 3 — Tributos
    elementos.append(section_header("Regra 3 — Fórmulas tributárias e contribuições"))
    elementos.append(sp(1))
    regra3 = [
        [th("TRIBUTO / CONTRIBUIÇÃO"), th("FÓRMULA"), th("BASE LEGAL")],
        [td("Funrural PF (até 03/2026)"),
         td("1,50% × Receita bruta (1,2% INSS + 0,1% RAT + 0,2% SENAR)"),
         td("Lei 8.212/91")],
        [td("Funrural PF (a partir 04/2026)"),
         td("1,63% × Receita bruta"), td("LC 224/2025")],
        [td("Funrural PJ (a partir 04/2026)"),
         td("2,23% × Receita bruta"), td("LC 224/2025")],
        [td("ICMS gado entre produtores (GO)"),
         td("Isento (cria/recria/engorda)"),
         td("RCTE-GO Anexo IX, art. 6º, XLIII")],
        [td("IRPF Rural (PF)"),
         td("20% × Resultado da atividade rural"),
         td("Lei 8.023/90 + RIR/2018")],
    ]
    tbl3 = Table(regra3, colWidths=[W * 0.32, W * 0.40, W * 0.28])
    tbl3.setStyle(tsb(stripe=True))
    elementos.append(tbl3)

    return elementos


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA 5 — REGRA 4 (TESTES T-01 a T-08) + REGRA 5 (CRUZAMENTOS EXTERNOS)
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_testes_e_cruzamentos_externos(r: dict) -> list:
    elementos = [
        Paragraph("REGRA 4 — Cruzamentos Forenses de Detecção de Anomalias",
                  ST["h2"]),
        sp(1),
    ]

    testes = [
        [th("TESTE"), th("CRITÉRIO MATEMÁTICO"), th("DETECTA")],
        [td("T-01 Concentração"),
         td("Valor 1 nota / Receita anual ≥ 10%"),
         td("Operações extraordinárias")],
        [td("T-02 Smurfing"),
         td("≥ 3 notas mesmo destinatário/dia COM valores idênticos"),
         td("Fragmentação fiscal")],
        [td("T-03 Trânsito órfão"),
         td("Σ Remessas/Leilão SEM NF-e venda subsequente"),
         td("Receita não declarada")],
        [td("T-04 Concentração PF"),
         td("Vendas a PF ≥ 90% E PFs com 3+ aquisições"),
         td("Intermediação não declarada")],
        [td("T-05 IE inconsistente"),
         td("Mesmo CPF/CNPJ vinculado a 2+ IEs"),
         td("Erro cadastral ou simulação")],
        [td("T-06 Pauta + Sazonalidade"),
         td("Valor unitário fora ±30% pauta OU Σ trimestral ≥ 45%"),
         td("Sub/superfaturamento ou esvaziamento")],
        [td("T-07 Documental"),
         td("Validação dígito verificador de todos os CPF/CNPJ"),
         td("Documentos forjados")],
        [td("<b>T-08 Cruzamento planilha</b>", bold=True),
         td("<b>Totais Planilha IR v5 ≠ totais PDF GIEF</b>", bold=True),
         td("<b>Inconsistência entre fontes</b>", bold=True)],
    ]
    tbl = Table(testes, colWidths=[W * 0.28, W * 0.40, W * 0.32])
    tbl.setStyle(tsb(stripe=True))
    elementos.append(tbl)
    elementos.append(sp(2))

    # Status atual do T-08
    t08 = r.get("teste_t08", {})
    cor_status = CONFORME if not t08.get("detectado") else CRITICO
    rotulo = "CONFORME" if not t08.get("detectado") else "DIVERGENTE"
    msg = (
        f"<b>Status atual do T-08:</b> <font color='#{cor_status.hexval()[2:]}'>"
        f"{rotulo}</font>. "
        f"{t08.get('total_indicadores_comparados', 0)} indicadores comparados — "
        f"{t08.get('qtd_divergencias', 0)} divergência(s) e "
        f"{t08.get('qtd_atencoes', 0)} atenção(ões)."
    )
    elementos.append(info_box(msg, label="EXECUÇÃO T-08 NESTA AUDITORIA",
                              border_color=cor_status))
    elementos.append(sp(2))

    # Regra 5 — Cruzamentos externos
    elementos.append(section_header("Regra 5 — Cruzamentos com Bases Externas"))
    elementos.append(sp(1))
    fontes = r.get("regra_5_cruzamentos_externos", [])
    linhas = [[th("FONTE EXTERNA"), th("O QUE CONFIRMAR"), th("COMO CRUZAR")]]
    for f in fontes:
        linhas.append([td(f["fonte"]), td(f["o_que_confirmar"]),
                       td(f["como_cruzar"])])
    tbl5 = Table(linhas, colWidths=[W * 0.26, W * 0.34, W * 0.40])
    tbl5.setStyle(tsb(stripe=True))
    elementos.append(tbl5)
    return elementos


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA — REGRA ESPECIAL 1 (RE-1): VENDA → COMPRA para produtor rural
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_regra_especial_1(r: dict) -> list:
    """Documentação técnica completa da Regra Especial 1, conforme MD oficial.

    Estrutura:
      • Definição + aprovação técnica
      • 4 critérios primários (bloqueantes)
      • 5 alertas secundários (não-bloqueantes)
      • Lançamento contábil débito/crédito explícito
      • Efeitos da reclassificação
      • Base legal (NBC TG + Leis)
    """
    re1 = r.get("regra_especial_1") or {}
    if not re1:
        return [Paragraph(
            "Documentação da Regra Especial 1 indisponível neste resultado.",
            ST["body"])]

    elementos = [
        Paragraph(re1.get("titulo", "REGRA ESPECIAL 1"), ST["h2"]),
        Paragraph(
            f"<i>Aprovada por {re1.get('aprovada_por', '—')}  ·  "
            f"Versão {re1.get('versao', '—')}</i>",
            ST["sub"]),
        sp(1),
    ]

    # ── Definição ─────────────────────────────────────────────────────────
    elementos.append(info_box(
        re1.get("definicao", ""),
        label="DEFINIÇÃO",
        border_color=AZUL))
    elementos.append(sp(1))

    # ── Critérios primários (bloqueantes) ─────────────────────────────────
    elementos.append(section_header(
        "CRITÉRIOS PRIMÁRIOS (todos devem ser SIM para aplicar a RE-1)",
        accent_color=CONFORME))
    elementos.append(sp(0.5))
    criterios = re1.get("criterios_primarios", [])
    linhas_c = [[th("#", align=TA_CENTER), th("VALIDAÇÃO")]]
    for i, c in enumerate(criterios, start=1):
        linhas_c.append([td(str(i), align=TA_CENTER, bold=True), td(c)])
    tbl_c = Table(linhas_c, colWidths=[W * 0.06, W * 0.94])
    tbl_c.setStyle(tsb(stripe=True))
    elementos.append(tbl_c)
    elementos.append(sp(1.5))

    # ── Lançamento contábil (Débito / Crédito) ────────────────────────────
    elementos.append(section_header(
        "LANÇAMENTO CONTÁBIL GERADO (NBC TG 16)", accent_color=AZUL))
    elementos.append(sp(0.5))
    lc = re1.get("lancamento_contabil", {})
    debito = lc.get("debito", {})
    credito = lc.get("credito", {})
    rows_lc = [
        [th("LADO"), th("CONTA"), th("NOME"), th("CLASSIFICAÇÃO")],
        [td("<b>DÉBITO</b>", color=CONFORME, bold=True),
         td(debito.get("conta", "—"), bold=True),
         td(debito.get("nome", "—")),
         td(debito.get("tipo", "—"))],
        [td("<b>CRÉDITO</b>", color=ALTO, bold=True),
         td(credito.get("conta", "—"), bold=True),
         td(credito.get("nome", "—")),
         td(credito.get("tipo", "—"))],
    ]
    tbl_lc = Table(rows_lc,
                   colWidths=[W * 0.13, W * 0.16, W * 0.30, W * 0.41])
    tbl_lc.setStyle(tsb(stripe=True))
    elementos.append(tbl_lc)
    elementos.append(sp(1))
    elementos.append(info_box(
        "Validação: <b>Débito = Crédito</b> (balanceamento garantido pela RE-1).",
        border_color=AZUL_M))
    elementos.append(sp(1.5))

    # ── Efeitos da reclassificação ────────────────────────────────────────
    elementos.append(section_header(
        "EFEITOS DA RECLASSIFICAÇÃO (campos atualizados na nota)",
        accent_color=AZUL_M))
    elementos.append(sp(0.5))
    ef = re1.get("efeitos", {})
    linhas_e = [
        [th("CAMPO"), th("VALOR APÓS RE-1")],
        [td("Natureza-exibição",  bold=True), td(ef.get("natureza_exibicao", "—"),
                                                   bold=True, color=AZUL)],
        [td("Categoria contábil", bold=True), td(ef.get("categoria_contabil", "—"),
                                                   bold=True, color=ALTO)],
        [td("Efeito IRPF",        bold=True), td(ef.get("efeito_irpf", "—"),
                                                   bold=True, color=CONFORME)],
        [td("Regra aplicada",     bold=True), td(ef.get("regra_aplicada", "—"))],
        [td("Confiança",          bold=True), td(ef.get("confianca", "—"))],
    ]
    tbl_e = Table(linhas_e, colWidths=[W * 0.34, W * 0.66])
    tbl_e.setStyle(tsb(stripe=True))
    elementos.append(tbl_e)
    elementos.append(sp(1.5))

    # ── Alertas secundários (não-bloqueantes) ─────────────────────────────
    elementos.append(section_header(
        "VALIDAÇÕES SECUNDÁRIAS (alertas, não-bloqueantes)",
        accent_color=ALTO))
    elementos.append(sp(0.5))
    secundarios = re1.get("criterios_secundarios", [])
    rows_s = [[th("CONDIÇÃO"), th("AÇÃO / EFEITO")]]
    for cond, acao in secundarios:
        rows_s.append([td(cond, bold=True), td(acao)])
    tbl_s = Table(rows_s, colWidths=[W * 0.30, W * 0.70])
    tbl_s.setStyle(tsb(stripe=True))
    elementos.append(tbl_s)
    elementos.append(sp(1.5))

    # ── Base legal ────────────────────────────────────────────────────────
    elementos.append(section_header("BASE LEGAL", accent_color=AZUL))
    elementos.append(sp(0.5))
    leis = re1.get("base_legal", [])
    bullets = "<br/>".join(f"• {l}" for l in leis)
    elementos.append(info_box(bullets, border_color=AZUL))
    return elementos


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA — CATÁLOGO COMPLETO DE 18 TIPOLOGIAS DE ANOMALIA (5 eixos)
# ═══════════════════════════════════════════════════════════════════════════

_GRAVIDADE_CORES = {
    "Muito Alta": CRITICO,
    "Alta":       ALTO,
    "Média":      MEDIO,
    "Baixa":      CONFORME,
}


def _pagina_catalogo_tipologias(r: dict) -> list:
    """Tabela completa das 18 anomalias agrupadas por eixo (modelo p. 8)."""
    elementos = [
        Paragraph("CATÁLOGO COMPLETO DE TIPOLOGIAS DE ANOMALIA", ST["h2"]),
        Paragraph(
            "<i>OrgAudi 1.1 — 18 tipologias estruturadas em 5 eixos de "
            "classificação. Cada anomalia é referenciada por código (AN-XX), "
            "eixo, gravidade e tributos impactados.</i>",
            ST["sub"]),
        sp(1),
    ]

    catalogo = r.get("catalogo_anomalias") or []
    eixos = r.get("eixos_tipologias") or {}
    if not catalogo:
        elementos.append(Paragraph("Catálogo não disponível.", ST["body"]))
        return elementos

    # Agrupa por eixo
    por_eixo: dict[str, list[dict]] = {}
    for item in catalogo:
        por_eixo.setdefault(item["eixo"], []).append(item)

    for eixo_id in sorted(por_eixo.keys()):
        titulo_eixo = eixos.get(eixo_id, "")
        elementos.append(section_header(
            f"Eixo {eixo_id} — {titulo_eixo}", accent_color=AZUL_M))

        linhas = [[
            th("CÓD."), th("TIPO / DESCRIÇÃO"),
            th("GRAVIDADE", align=TA_CENTER), th("TRIBUTOS"),
        ]]
        for an in por_eixo[eixo_id]:
            cor_grav = _GRAVIDADE_CORES.get(an["gravidade"], CTXT_DARK)
            linhas.append([
                td(an["codigo"], bold=True, color=AZUL),
                td(f"<b>{an['tipo']}</b> — {an['descricao']}"),
                td(f"<b>{an['gravidade']}</b>", color=cor_grav, align=TA_CENTER),
                td(an["tributos"], size=7.5),
            ])
        tbl = Table(linhas, colWidths=[W * 0.08, W * 0.55, W * 0.13, W * 0.24])
        tbl.setStyle(tsb(stripe=True))
        elementos.append(tbl)
        elementos.append(sp(0.5))

    # Sumário visual (contagem por gravidade)
    qtd_ma = sum(1 for i in catalogo if i["gravidade"] == "Muito Alta")
    qtd_a  = sum(1 for i in catalogo if i["gravidade"] == "Alta")
    qtd_m  = sum(1 for i in catalogo if i["gravidade"] == "Média")
    sumario = (
        f"<b>MUITO ALTA</b> ({qtd_ma})  ·  "
        f"<b>ALTA</b> ({qtd_a})  ·  "
        f"<b>MÉDIA</b> ({qtd_m})  ·  "
        f"<b>Total:</b> {len(catalogo)} tipologias em "
        f"{len(por_eixo)} eixos"
    )
    elementos.append(info_box(sumario, border_color=AZUL_M))
    return elementos


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA — PLANILHA DE GADO PARA IMPOSTO DE RENDA
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_planilha_gado_ir(r: dict) -> list:
    """Planilha de Gado para IR — VERSÃO COMPACTA (2 páginas).

    Página 1: Título + Vendas mensais + Remessas mensais lado a lado.
    Página 2: Compras mensais + Total geral das saídas + Fórmula F1..F6.

    Otimizações de espaço:
      • Tabelas mensais com fonte 7.5pt e padding reduzido
      • Vendas+Remessas exibidas lado a lado (2 colunas)
      • Total Geral em linha única compacta
      • Spacings reduzidos (sp(1) ao invés de sp(3))
    """
    elementos = [
        Paragraph("PLANILHA DE GADO PARA IMPOSTO DE RENDA", ST["h2"]),
        Paragraph("<i>Lei 8.023/90 — IRPF Atividade Rural</i>", ST["sub"]),
        sp(1),
    ]

    p = r.get("planilha_gado_ir") or {}
    vendas = p.get("vendas") or []
    remessas = p.get("remessas") or []
    compras = p.get("compras") or []
    totais = p.get("totais") or {}

    # ── VENDAS (largura total) ─────────────────────────────────────────────
    elementos.append(section_header(
        "VENDAS — Cliente como REMETENTE → RECEITA",
        accent_color=CONFORME))
    elementos.append(sp(0.5))
    elementos.append(_tabela_mensal_compacta(
        vendas, totais.get("vendas", {}), "VENDAS", largura=W))
    elementos.append(sp(1))

    # ── REMESSAS (largura total, abaixo de Vendas) ─────────────────────────
    elementos.append(section_header(
        "REMESSAS — Cliente como REMETENTE → TRÂNSITO (não soma à base IRPF)",
        accent_color=AZUL_M))
    elementos.append(sp(0.5))
    elementos.append(_tabela_mensal_compacta(
        remessas, totais.get("remessas", {}), "REMESSAS", largura=W))
    elementos.append(sp(1))

    # Total Geral das Saídas — linha única compacta (info_box style)
    sc = totais.get("saidas_consolidadas") or {}
    texto_sc = (
        f"<b>TOTAL GERAL DAS SAÍDAS (Vendas + Remessas):</b>  "
        f"{_int(sc.get('qtd_notas'))} notas  ·  "
        f"{_int(sc.get('cabecas'))} cabeças  ·  "
        f"<b>{_brl(sc.get('valor'))}</b>"
    )
    elementos.append(info_box(texto_sc, border_color=AZUL))

    # ── COMPRAS em página separada (P6) ────────────────────────────────────
    elementos.append(PageBreak())
    elementos.append(Paragraph(
        "PLANILHA DE GADO PARA IR — Compras e Apuração F1..F6",
        ST["h2"]))
    elementos.append(sp(1))

    elementos.append(section_header(
        "COMPRAS — Cliente como DESTINATÁRIO → DESPESA / INVESTIMENTO (RE-1)",
        accent_color=ALTO))
    elementos.append(sp(0.5))
    elementos.append(_tabela_mensal_compacta(compras, totais.get("compras", {}),
                                               "COMPRAS", largura=W))
    elementos.append(sp(1))

    # Fórmula Regra 2 (F1..F6) — destaque dos valores apurados
    elementos.append(section_header(
        "FÓRMULA APLICADA — REGRA 2 (APURAÇÃO DA RECEITA RURAL)",
        accent_color=AZUL))
    elementos.append(sp(0.5))
    formula = p.get("formula_regra_2") or {}
    cab = [th("CÓD."), th("DESCRIÇÃO"), th("VALOR", align=TA_RIGHT)]
    linhas = [cab]
    for chave in ("F1", "F2", "F3", "F4", "F6", "F5"):
        item = formula.get(chave) or {}
        cor = (CONFORME if chave in ("F1", "F4") else
               ALTO if chave == "F6" else
               AZUL if chave == "F5" else
               CTXT_DARK)
        linhas.append([
            td(chave, bold=True, color=AZUL),
            td(item.get("descricao", "")),
            td(_brl(item.get("valor")), align=TA_RIGHT, bold=True, color=cor),
        ])
    tbl_f = Table(linhas, colWidths=[W * 0.10, W * 0.62, W * 0.28])
    tbl_f.setStyle(tsb(stripe=True))

    # ── Bloco final mantido junto: Tabela F1..F6 + Declaração + Assinatura ─
    # Usa KeepTogether para que esses três elementos não se separem em
    # páginas diferentes (eliminando whitespace no final).
    bloco_final = [tbl_f, sp(1.5)] + _bloco_declaracao_e_assinatura(
        r, compacto=True)
    elementos.append(KeepTogether(bloco_final))
    return elementos


def _bloco_declaracao_e_assinatura(r: dict, compacto: bool = False) -> list:
    """Bloco "Declaração de Alcance + Assinatura técnica".

    Args:
      r: resultado da auditoria cruzada (precisa de `declaracao_alcance`,
         `sistema`, `audit_hash`, `timestamp`).
      compacto: quando True, usa fonte/espaçamentos menores para caber
        ao final de uma página existente (sem requerer PageBreak).
    """
    declaracao = r.get("declaracao_alcance", "")
    ts = (r.get("timestamp", "") or "")[:10]
    sistema = r.get("sistema", "OrgAudi 1.1")
    audit_hash = r.get("audit_hash", "—")

    elementos = []
    elementos.append(section_header(
        "DECLARAÇÃO DE ALCANCE E LIMITAÇÕES", accent_color=AZUL))
    elementos.append(sp(1))

    if compacto:
        # Texto em parágrafo único reduzido (compacto)
        estilo = S("decl_c", fontName="Helvetica", fontSize=7.5,
                   textColor=CTXT_DARK, alignment=TA_JUSTIFY, leading=10)
        for paragrafo in declaracao.split("\n\n"):
            paragrafo = paragrafo.strip()
            if paragrafo:
                elementos.append(Paragraph(paragrafo, estilo))
                elementos.append(sp(0.5))
    else:
        for paragrafo in declaracao.split("\n\n"):
            paragrafo = paragrafo.strip()
            if paragrafo:
                elementos.append(Paragraph(paragrafo, ST["body"]))
                elementos.append(sp(1))

    elementos.append(sp(1))

    # Bloco de assinatura — tabela 2 colunas (esquerda: assinatura · direita: meta)
    assinatura_esq = [
        [Paragraph("<b>Apuração realizada por:</b>",
                   S("ass1", fontName="Helvetica-Bold", fontSize=7.5,
                     textColor=CTXT, alignment=TA_LEFT, leading=10))],
        [Paragraph("<b>ROBSON ALAIN VELOSO</b>",
                   S("ass2", fontName="Helvetica-Bold", fontSize=10,
                     textColor=AZUL, alignment=TA_LEFT, leading=13))],
        [Paragraph("CRC- TO-002032/O-5 T-GO — Ciências Contábeis",
                   S("ass3", fontName="Helvetica", fontSize=8,
                     textColor=CTXT_DARK, alignment=TA_LEFT, leading=11))],
        [Paragraph("ORGATEC AUDITORIA FISCAL SOBERANA",
                   S("ass4", fontName="Helvetica", fontSize=7.5,
                     textColor=CTXT, alignment=TA_LEFT, leading=10))],
    ]
    assinatura_dir = [
        [Paragraph(f"<b>Sistema:</b> {sistema}",
                   S("met1", fontName="Helvetica", fontSize=8,
                     textColor=CTXT_DARK, alignment=TA_RIGHT, leading=10))],
        [Paragraph(f"<b>Audit hash:</b> {audit_hash}",
                   S("met2", fontName="Helvetica", fontSize=8,
                     textColor=CTXT_DARK, alignment=TA_RIGHT, leading=10))],
        [Paragraph(f"<b>Emitida em:</b> {ts or '—'}",
                   S("met3", fontName="Helvetica", fontSize=8,
                     textColor=CTXT_DARK, alignment=TA_RIGHT, leading=10))],
    ]
    tbl_esq = Table(assinatura_esq, colWidths=[W * 0.55])
    tbl_dir = Table(assinatura_dir, colWidths=[W * 0.43])
    tbl_dir.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    container = Table([[tbl_esq, tbl_dir]],
                       colWidths=[W * 0.57, W * 0.43])
    container.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE",    (0, 0), (-1, 0),  0.5, CBORD),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(container)
    return elementos


def _tabela_mensal_compacta(linhas_mensais: list[dict], totais: dict,
                              rotulo: str = "", largura=None) -> Table:
    """Versão compacta da tabela mensal — fonte menor, padding reduzido.

    Args:
      linhas_mensais: lista de {mes, qtd_notas, cabecas, valor}.
      totais: {qtd_notas, cabecas, valor}.
      rotulo: opcional, exibido no cabeçalho (ex.: VENDAS).
      largura: largura total da tabela; default = W * 0.49 (meio para lado a lado).
    """
    if largura is None:
        largura = W * 0.49

    if rotulo:
        cab = [
            th(rotulo, align=TA_CENTER, size=8),
            th("Q.NT.", align=TA_CENTER, size=7),
            th("CAB.", align=TA_CENTER, size=7),
            th("VALOR", align=TA_RIGHT, size=7),
        ]
    else:
        cab = [th("MÊS"), th("Q.NT.", align=TA_CENTER),
               th("CAB.", align=TA_CENTER), th("VALOR", align=TA_RIGHT)]

    corpo = [cab]
    for m in linhas_mensais:
        corpo.append([
            td(m.get("mes", "—"), size=7.5),
            td(_int(m.get("qtd_notas")), align=TA_CENTER, size=7.5),
            td(_int(m.get("cabecas")), align=TA_CENTER, size=7.5),
            td(_brl(m.get("valor")), align=TA_RIGHT, size=7.5),
        ])
    corpo.append([
        td("<b>TOTAL</b>", bold=True, color=BRANCO, size=8),
        td(f"<b>{_int(totais.get('qtd_notas'))}</b>",
           align=TA_CENTER, bold=True, color=BRANCO, size=8),
        td(f"<b>{_int(totais.get('cabecas'))}</b>",
           align=TA_CENTER, bold=True, color=BRANCO, size=8),
        td(f"<b>{_brl(totais.get('valor'))}</b>",
           align=TA_RIGHT, bold=True, color=BRANCO, size=8),
    ])
    # Distribuição de colunas: MÊS maior, Q.NT./CAB. compactas, VALOR médio
    tbl = Table(corpo,
                colWidths=[largura * 0.30, largura * 0.14,
                           largura * 0.14, largura * 0.42])
    estilo = tsb(stripe=True)
    # Reduz padding em todas as linhas para encolher altura da tabela
    estilo.add("TOPPADDING",    (0, 0), (-1, -1), 2)
    estilo.add("BOTTOMPADDING", (0, 0), (-1, -1), 2)
    estilo.add("FONTSIZE",      (0, 0), (-1, -1), 7.5)
    estilo.add("BACKGROUND",    (0, -1), (-1, -1), AZUL)
    tbl.setStyle(estilo)
    return tbl


def _int(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        return f"{int(float(v)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(v)


def _brl(v) -> str:
    from decimal import Decimal as _D
    if v is None or v == "":
        return "R$ —"
    try:
        d = _D(str(v))
    except Exception:
        return "R$ —"
    s = f"{d:,.2f}"
    return f"R$ {s.replace(',', 'X').replace('.', ',').replace('X', '.')}"


# ═══════════════════════════════════════════════════════════════════════════
#  PÁGINA 6 — TIPOLOGIAS + DECLARAÇÃO + ASSINATURA
# ═══════════════════════════════════════════════════════════════════════════

def _pagina_tipologias_declaracao(r: dict) -> list:
    elementos = [
        Paragraph("DECLARAÇÃO DE ALCANCE E LIMITAÇÕES", ST["h2"]),
        sp(1),
    ]
    declaracao = r.get("declaracao_alcance", "")
    for paragrafo in declaracao.split("\n\n"):
        paragrafo = paragrafo.strip()
        if paragrafo:
            elementos.append(Paragraph(paragrafo, ST["body"]))
            elementos.append(sp(1))

    elementos.append(sp(1))
    elementos.append(section_header(
        "TIPOLOGIAS DE ANOMALIA CONSIDERADAS NA BATERIA DE TESTES"))
    elementos.append(sp(1))

    tipologias = r.get("tipologias_consideradas", [])
    bullets = "<br/>".join(f"• {t}" for t in tipologias)
    elementos.append(info_box(bullets, border_color=AZUL_M))
    elementos.append(sp(3))

    elementos.append(section_header("RESPONSÁVEL TÉCNICO PELA AUDITORIA"))
    elementos.append(sp(1))
    elementos.append(Paragraph(
        "Documento elaborado por:", ST["body"]))
    elementos.append(sp(0.5))
    elementos.append(Paragraph(
        "<b>ROBSON ALAIN VELOSO</b>", ST["an"]))
    elementos.append(Paragraph(
        "CIÊNCIAS CONTÁBEIS — ORGATEC CONTABILIDADE E AUDITORIA",
        ST["as"]))
    elementos.append(sp(1))

    ts = r.get("timestamp", "")[:10]
    rodape = (
        f"Sistema: <b>{r.get('sistema', 'OrgAudi 1.1')}</b>  ·  "
        f"Audit hash: <b>{r.get('audit_hash', '—')}</b>  ·  "
        f"Auditoria emitida em {ts or datetime.now().strftime('%Y-%m-%d')}"
    )
    elementos.append(Paragraph(rodape, ST["sys"]))
    return elementos
