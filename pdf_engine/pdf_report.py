"""Geração de relatório PDF profissional com ReportLab."""

import io
import logging
from datetime import datetime
from pathlib import Path

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import Image as RLImage

matplotlib.use('Agg')  # Força backend sem GUI para estabilidade em threads
import matplotlib.pyplot as plt

from nfa_extractor.domain.constants import hex_cor
from nfa_extractor.domain.extractor import NFA, resumo_geral

logger = logging.getLogger(__name__)

LOGO_PATH = str(Path(__file__).parent / 'assets' / 'logo.png')

# ── Paleta de cores (Sincronizada com Design System) ──────────────────────────
AZUL_ESC  = colors.HexColor(hex_cor('BG2'))
AZUL_MED  = colors.HexColor(hex_cor('PRIMARY'))
AZUL_CLAR = colors.HexColor(hex_cor('BG4'))
VERDE     = colors.HexColor(hex_cor('GREEN'))
VERDE_CLAR= colors.HexColor('#D5F5E3')
LARANJA   = colors.HexColor(hex_cor('ORANGE'))
CYAN      = colors.HexColor(hex_cor('CYAN'))
CINZA     = colors.HexColor(hex_cor('GRAY'))
CINZA_ESC = colors.HexColor(hex_cor('BORDER'))
BRANCO    = colors.white
TEXTO     = colors.HexColor(hex_cor('TEXT')) if hex_cor('TEXT') != '#FFFFFF' else colors.black

W, H = A4


def _header_footer(canvas, doc):
    import os
    canvas.saveState()
    # Barra do cabeçalho
    canvas.setFillColor(AZUL_ESC)
    canvas.rect(0, H - 1.8*cm, W, 1.8*cm, fill=1, stroke=0)
    # Logo no canto esquerdo do cabeçalho
    logo_x = 0.3*cm
    logo_y = H - 1.65*cm
    logo_sz = 1.35*cm
    if os.path.exists(LOGO_PATH):
        canvas.drawImage(LOGO_PATH, logo_x, logo_y,
                         width=logo_sz, height=logo_sz,
                         preserveAspectRatio=True, mask='auto')
    # Título do cabeçalho
    canvas.setFillColor(BRANCO)
    canvas.setFont('Helvetica-Bold', 11)
    canvas.drawString(1.9*cm, H - 1.1*cm, 'OrgAudi — SEFAZ')
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#A9CCE3'))
    canvas.drawString(1.9*cm, H - 1.55*cm, 'OrgAudi · Análise de Notas Fiscais Avulsas')
    canvas.setFillColor(BRANCO)
    canvas.drawRightString(W - 1.5*cm, H - 1.1*cm,
        f'Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    # Rodapé
    canvas.setFillColor(AZUL_ESC)
    canvas.rect(0, 0, W, 0.9*cm, fill=1, stroke=0)
    canvas.setFillColor(BRANCO)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(1.5*cm, 0.3*cm, 'OrgAudi')
    canvas.drawCentredString(W/2, 0.3*cm, f'Página {doc.page}')
    canvas.setFillColor(colors.HexColor('#A9CCE3'))
    canvas.drawRightString(W - 1.5*cm, 0.3*cm, 'OrgAudi — Sistema de Auditoria Agronegócio')
    canvas.restoreState()


def gerar_pdf(notas: list[NFA], saida: str, analise_ia: str = '', nome_contribuinte: str = '',
              cpf_contribuinte: str = '', anomalias: list | None = None) -> None:
    """Gera um Laudo Técnico de Auditoria Forense profissional."""
    doc = SimpleDocTemplate(saida, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, 
                            topMargin=2.5*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    style_tit = ParagraphStyle('Tit', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=18, textColor=AZUL_ESC, spaceAfter=20)
    style_sec = ParagraphStyle('Sec', parent=styles['Heading2'], fontSize=12, textColor=AZUL_MED, spaceBefore=15, spaceAfter=10, borderPadding=5)
    style_txt = ParagraphStyle('Txt', parent=styles['Normal'], fontSize=10, leading=14, alignment=TA_LEFT)

    elements = []
    res = resumo_geral(notas, nome_contribuinte=nome_contribuinte)
    
    # 1. Cabeçalho de Identificação
    elements.append(Paragraph("LAUDO TÉCNICO DE AUDITORIA FISCAL E COMPLIANCE", style_tit))
    
    info_data = [
        ["CLIENTE AUDITADO:", nome_contribuinte.upper()],
        ["CPF/CNPJ:", cpf_contribuinte],
        ["PERÍODO DE ANÁLISE:", f"{min(n.emissao for n in notas)} a {max(n.emissao for n in notas)}" if notas else "N/A"],
        ["EMISSÃO DO LAUDO:", datetime.now().strftime("%d/%m/%Y %H:%M")]
    ]
    t_info = Table(info_data, colWidths=[4.5*cm, 11.5*cm])
    t_info.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), AZUL_CLAR),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_info)
    elements.append(Spacer(1, 0.5*cm))

    # Cards de Resumo (Executivo)
    def _card_val(label, value, bg):
        return _resumo_card(label, value, bg)

    cards_data = [
        [_resumo_card('Total de Notas', str(res['total_notas']), AZUL_CLAR),
         _resumo_card('Cabecas', f"{res['total_cabecas']:.0f}", VERDE_CLAR),
         _resumo_card('Valor Total', f"R$ {res['total_valor']:,.2f}", CINZA)]
    ]
    t_cards = Table(cards_data, colWidths=[(W-4.5*cm)/3]*3)
    t_cards.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER')]))
    elements.append(t_cards)
    elements.append(Spacer(1, 0.5*cm))

    # 2. Parecer Técnico da Squad (Análise Anti-Fraude)
    elements.append(Paragraph("1. PARECER TÉCNICO E VEREDITO DE RISCO", style_sec))
    if analise_ia:
        import re
        # Abordagem correta: escapar o texto ANTES de inserir tags HTML.
        # 1. Remover cabeçalhos markdown (# ## ###)
        texto = re.sub(r'^\s*#{1,6}\s*', '', analise_ia, flags=re.MULTILINE)

        # 2. Processar cada parágrafo individualmente
        for paragrafo in texto.split('\n\n'):
            linha = paragrafo.strip()
            if not linha:
                continue

            # 3. Escapar caracteres especiais HTML no texto puro
            linha_safe = linha.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # 4. Converter **negrito** em tags <b> (sobre texto já escapado — seguro)
            partes = re.split(r'(\*\*)', linha_safe)
            resultado = ""
            aberto    = False
            for parte in partes:
                if parte == '**':
                    resultado += '</b>' if aberto else '<b>'
                    aberto     = not aberto
                else:
                    resultado += parte
            if aberto:
                resultado += '</b>'  # fechar tag não encerrada

            elements.append(Paragraph(resultado, style_txt))
            elements.append(Spacer(1, 0.3 * cm))
    
    # 3. Relatório de Irregularidades
    if anomalias:
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph("2. EVIDÊNCIAS DE FRAUDE E INCONSISTÊNCIAS", style_sec))
        header = [["NFA", "DATA", "NATUREZA", "VALOR (R$)", "RISCO DETECTADO"]]
        data_anom = header + [[n['NFA'], n['Data'], n['Natureza'], f"{n['Valor']:,.2f}", n['Motivo']] for n in anomalias]
        t_anom = Table(data_anom, colWidths=[2.5*cm, 2.5*cm, 3.5*cm, 3*cm, 4.5*cm])
        t_anom.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), AZUL_ESC),
            ('TEXTCOLOR', (0,0), (-1,0), BRANCO),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
        ]))
        elements.append(t_anom)
    
    # Gráficos
    graficos = _gerar_graficos(res)
    if graficos:
        elements.append(PageBreak())
        elements.append(Paragraph("ANEXO I: VISUALIZAÇÃO DE DADOS", style_sec))
        for g in graficos:
            elements.append(g)
            elements.append(Spacer(1, 0.5*cm))

    # 4. Encerramento
    elements.append(Spacer(1, 2*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=AZUL_ESC))
    elements.append(Paragraph("OrgAudi — Sistema Soberano de Auditoria Fiscal", ParagraphStyle('End', parent=style_txt, alignment=TA_CENTER, fontSize=8, textColor=colors.grey)))

    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)


def _th(txt: str) -> Paragraph:
    return Paragraph(f'<b>{txt}</b>', ParagraphStyle(
        'TH', fontName='Helvetica-Bold', fontSize=8,
        textColor=BRANCO, alignment=TA_CENTER))


def _resumo_card(label: str, value: str, bg: colors.Color) -> Table:
    t = Table([
        [Paragraph(f'<font size=8 color="#566573">{label}</font>', ParagraphStyle('CL', parent=getSampleStyleSheet()['Normal'], alignment=TA_CENTER))],
        [Paragraph(f'<b><font size=13 color="#0D2137">{value}</font></b>', ParagraphStyle('CV', parent=getSampleStyleSheet()['Normal'], alignment=TA_CENTER))],
    ], colWidths=['100%'])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), bg),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('RIGHTPADDING',  (0,0), (-1,-1), 6),
        ('ROUNDEDCORNERS', (0,0), (-1,-1), [6,6,6,6]),
    ]))
    return t


def _estilo_tabela(t: Table, n_rows: int, total_row: bool = False):
    style = [
        ('BACKGROUND',    (0,0), (-1,0), AZUL_MED),
        ('TEXTCOLOR',     (0,0), (-1,0), BRANCO),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [CINZA, BRANCO]),
        ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,-1), 8),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 5),
        ('RIGHTPADDING',  (0,0), (-1,-1), 5),
        ('LINEBELOW',     (0,0), (-1,-1), 0.5, colors.HexColor('#BDC3C7')),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]
    if total_row and n_rows > 1:
        style += [
            ('BACKGROUND',  (0, n_rows-1), (-1, n_rows-1), AZUL_ESC),
            ('TEXTCOLOR',   (0, n_rows-1), (-1, n_rows-1), BRANCO),
            ('FONTNAME',    (0, n_rows-1), (-1, n_rows-1), 'Helvetica-Bold'),
        ]
    t.setStyle(TableStyle(style))

def _gerar_graficos(res: dict) -> list:
    graficos = []
    
    # Gráfico 1: Evolução Mensal (Executive Clean)
    meses_dict = res.get('por_mes', {})
    if len(meses_dict) > 0:
        fig_bar = None
        try:
            meses = list(meses_dict.keys())
            valores = [v['valor'] for v in meses_dict.values()]
            
            fig_bar, ax = plt.subplots(figsize=(6, 3))
            bars = ax.bar(meses, valores, color=hex_cor('PRIMARY'), width=0.6, alpha=0.9)
            
            # Adicionar etiquetas de valor no topo das barras
            for bar in bars:
                yval = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, yval + (max(valores)*0.01), 
                        f'{yval/1000:.1f}k', ha='center', va='bottom', fontsize=7, color=hex_cor('BG3'))

            ax.set_title('FATURAMENTO MENSAL (R$)', fontsize=9, fontweight='bold', color=hex_cor('BG2'), pad=15)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.tick_params(axis='x', rotation=30, labelsize=7)
            ax.tick_params(axis='y', labelsize=7)
            plt.grid(axis='y', linestyle='--', alpha=0.3)
            fig_bar.tight_layout()
            
            buf = io.BytesIO()
            fig_bar.savefig(buf, format='png', dpi=200, transparent=True)
            buf.seek(0)
            graficos.append(RLImage(buf, width=15*cm, height=7.5*cm))
        except Exception:
            logger.exception("Falha ao renderizar gráfico de barras")
        finally:
            if fig_bar:
                plt.close(fig_bar)

    # Gráfico 2: Market Share (Donut Premium)
    top_dest = res.get('top_dest', [])
    if len(top_dest) > 1:
        fig_pie = None
        try:
            labels = [d['nome'][:15] for d in top_dest[:5]]
            valores = [d['valor'] for d in top_dest[:5]]
            
            outros_val = sum(d['valor'] for d in top_dest[5:])
            if outros_val > 0:
                labels.append('OUTROS')
                valores.append(outros_val)
                
            fig_pie, ax = plt.subplots(figsize=(5, 5))
            cores = [hex_cor('PRIMARY'), hex_cor('CYAN'), hex_cor('ORANGE'), hex_cor('GREEN'), hex_cor('GRAY'), hex_cor('BORDER')]
            
            # Gráfico de Rosca (Donut)
            _wedges, _texts, _autotexts = ax.pie(valores, labels=labels, autopct='%1.1f%%',
                                            colors=cores, startangle=140, 
                                            pctdistance=0.75,
                                            textprops={'fontsize': 7, 'fontweight': 'bold'})
            
            # Adicionar círculo branco no meio para o efeito de rosca
            centre_circle = plt.Circle((0,0), 0.60, fc='white')
            fig_pie.gca().add_artist(centre_circle)
            
            ax.set_title('MARKET SHARE', fontsize=9, fontweight='bold', color=hex_cor('BG2'))
            fig_pie.tight_layout()
            
            buf = io.BytesIO()
            fig_pie.savefig(buf, format='png', dpi=200, transparent=True)
            buf.seek(0)
            graficos.append(RLImage(buf, width=10*cm, height=10*cm))
        except Exception:
            logger.exception("Falha ao renderizar gráfico donut")
        finally:
            if fig_pie:
                plt.close(fig_pie)

    return graficos
def gerar_pdf_auditoria(notas: list[NFA], saida: str, nome_contribuinte: str = "") -> None:
    """Gera um relatório técnico focado em Auditoria de Gado (Pecuária)."""
    doc = SimpleDocTemplate(
        saida, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2.4*cm, bottomMargin=1.5*cm,
        title='Auditoria Sovereign — Gado',
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('H1', parent=styles['Normal'], fontSize=18, fontName='Helvetica-Bold', textColor=AZUL_ESC, spaceAfter=8)
    normal = ParagraphStyle('N', parent=styles['Normal'], fontSize=9, leading=12)
    
    res = resumo_geral(notas, nome_contribuinte=nome_contribuinte)
    story = []

    story.append(Paragraph('RELATÓRIO TÉCNICO DE AUDITORIA — FLUXO DE GADO', h1))
    story.append(HRFlowable(width='100%', thickness=2, color=AZUL_MED))
    story.append(Spacer(1, 0.5*cm))

    if notas:
        exib_nome = nome_contribuinte if (nome_contribuinte and nome_contribuinte.strip()) else (notas[0].remetente.nome if notas else "Auditado N/I")
        exib_cpf = getattr(notas[0].remetente, 'cpf_cnpj', '-')
        story.append(Paragraph(f"<b>Auditado:</b> {exib_nome}", normal))
        story.append(Paragraph(f"<b>CPF/CNPJ:</b> {exib_cpf}", normal))
        story.append(Spacer(1, 0.5*cm))

    # Tabela de Resumo de Auditoria
    data = [
        ['Indicador', 'Valor Detectado'],
        ['Total de Notas Analisadas', str(res['total_notas'])],
        ['Volume Total (Cabeças)', f"{res['total_cabecas']:.0f}"],
        ['Faturamento Total', f"R$ {res['total_valor']:,.2f}"],
        ['Ticket Médio / Animal', f"R$ {res['ticket_medio']:,.2f}"],
    ]
    t = Table(data, colWidths=[6*cm, 6*cm])
    _estilo_tabela(t, len(data))
    story.append(t)
    
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("<b>Conclusão do Auditor:</b> Documento gerado via Protocolo Sovereign para fins de compliance fiscal.", normal))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
