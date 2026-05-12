"""Geração de PDF da Planilha de Gado para IR — fiel ao modelo SEFAZ-GO.

Layout idêntico ao documento de referência:
  VENDAS / REMESSAS / TRANSFERÊNCIAS / OUTRAS / TOTAL GERAL
  Colunas: MÊS · Q NOTAS · CABEÇAS · VALOR (R$)
  Linha TOTAL ao final de cada seção.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:
    from nfa_extractor.domain.extractor import NFA

# ── Paleta ────────────────────────────────────────────────────────────────────
AZUL_ESC   = colors.HexColor('#041A2E')
AZUL_MED   = colors.HexColor('#0D2137')
AZUL_CLAR  = colors.HexColor('#D6EAF8')
VERDE      = colors.HexColor('#00CC70')
AMARELO    = colors.HexColor('#EAB308')
CIANO      = colors.HexColor('#00D4FF')
ROXO       = colors.HexColor('#A78BFA')
CINZA      = colors.HexColor('#9CA3AF')
CINZA_CLAR = colors.HexColor('#F2F3F4')
BRANCO     = colors.white
PRETO      = colors.black

# Cores de cada seção — correspondem ao modelo .docx / aba IR do app
SECAO_CORES: dict[str, colors.Color] = {
    'VENDAS':        VERDE,
    'REMESSAS':      AMARELO,
    'TRANSFERÊNCIAS': CIANO,
    'OUTRAS':        ROXO,
    'TOTAL GERAL':   CINZA,
}

W, H = A4
LOGO_PATH = str(Path(__file__).parent / 'assets' / 'logo.png')

# Meses fixos em ordem (igual ao modelo — 12 linhas sempre)
MESES_ORDEM = [
    '01', '02', '03', '04', '05', '06',
    '07', '08', '09', '10', '11', '12',
]
NOMES_MESES = {
    '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março',
    '04': 'Abril',   '05': 'Maio',      '06': 'Junho',
    '07': 'Julho',   '08': 'Agosto',    '09': 'Setembro',
    '10': 'Outubro', '11': 'Novembro',  '12': 'Dezembro',
}


# ── Header/Footer ─────────────────────────────────────────────────────────────

def _header_footer(canvas, doc):
    canvas.saveState()

    # Barra de cabeçalho
    canvas.setFillColor(AZUL_ESC)
    canvas.rect(0, H - 1.8 * cm, W, 1.8 * cm, fill=1, stroke=0)

    # Logo
    if os.path.exists(LOGO_PATH):
        canvas.drawImage(LOGO_PATH, 0.3 * cm, H - 1.65 * cm,
                         width=1.35 * cm, height=1.35 * cm,
                         preserveAspectRatio=True, mask='auto')

    # Título
    canvas.setFillColor(BRANCO)
    canvas.setFont('Helvetica-Bold', 11)
    canvas.drawString(1.9 * cm, H - 1.1 * cm, 'OrgAudi — Planilha de Gado para IR')
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.HexColor('#A9CCE3'))
    canvas.drawString(1.9 * cm, H - 1.55 * cm,
                      f'OrgAudi · Exercício {doc.ano_referencia}')
    canvas.setFillColor(BRANCO)
    canvas.drawRightString(W - 1.5 * cm, H - 1.1 * cm,
                           f'Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}')

    # Barra de rodapé
    canvas.setFillColor(AZUL_ESC)
    canvas.rect(0, 0, W, 1.0 * cm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor('#A9CCE3'))
    canvas.setFont('Helvetica', 7)
    canvas.drawString(1.5 * cm, 0.35 * cm, 'Planilha de Gado — IRPF Atividade Rural · Lei 8.023/90')
    canvas.drawRightString(W - 1.5 * cm, 0.35 * cm, f'Página {doc.page}')

    canvas.restoreState()


# ── Estilos de parágrafo ──────────────────────────────────────────────────────

def _estilos():
    return {
        'titulo_secao': ParagraphStyle(
            'TituloSecao',
            fontName='Helvetica-Bold', fontSize=10,
            alignment=TA_LEFT, textColor=BRANCO,
            leftIndent=8, spaceBefore=0, spaceAfter=0,
        ),
        'cab': ParagraphStyle(
            'Cab',
            fontName='Helvetica-Bold', fontSize=8,
            alignment=TA_CENTER, textColor=BRANCO,
        ),
        'cab_esq': ParagraphStyle(
            'CabEsq',
            fontName='Helvetica-Bold', fontSize=8,
            alignment=TA_LEFT, textColor=BRANCO,
        ),
        'dado': ParagraphStyle(
            'Dado',
            fontName='Helvetica', fontSize=8,
            alignment=TA_LEFT, textColor=PRETO,
        ),
        'dado_dir': ParagraphStyle(
            'DadoDir',
            fontName='Helvetica', fontSize=8,
            alignment=TA_RIGHT, textColor=PRETO,
        ),
        'total': ParagraphStyle(
            'Total',
            fontName='Helvetica-Bold', fontSize=8,
            alignment=TA_LEFT, textColor=BRANCO,
        ),
        'total_dir': ParagraphStyle(
            'TotalDir',
            fontName='Helvetica-Bold', fontSize=8,
            alignment=TA_RIGHT, textColor=BRANCO,
        ),
        'nome_produtor': ParagraphStyle(
            'NomeProdutor',
            fontName='Helvetica-Bold', fontSize=13,
            alignment=TA_CENTER, textColor=AZUL_ESC,
            spaceBefore=4, spaceAfter=4,
        ),
        'subtitulo': ParagraphStyle(
            'Subtitulo',
            fontName='Helvetica', fontSize=9,
            alignment=TA_CENTER, textColor=CINZA,
            spaceBefore=0, spaceAfter=6,
        ),
    }


# ── Tabela de dados de uma seção ──────────────────────────────────────────────

def _tabela_secao(
    titulo: str,
    cor_secao: colors.Color,
    linhas_dados: list[tuple[str, int, float, float]],
    tot_notas: int,
    tot_cab: float,
    tot_val: float,
    estilos: dict,
    ano: str,
) -> list:
    """Constrói o bloco (título + tabela) de uma seção da planilha IR.

    Args:
        titulo: Nome da seção (ex: 'VENDAS')
        cor_secao: Cor de destaque da seção
        linhas_dados: lista de (mes_mm, q_notas, cabecas, valor) para os 12 meses
        tot_notas / tot_cab / tot_val: totais já calculados
        estilos: dicionário de ParagraphStyle
        ano: ano de referência (ex: '2025')
    """
    # ── Larguras das colunas (soma = área útil da página) ──────────────────
    # A4 com margem 1.5cm cada lado → útil = 21 - 3 = 18cm
    COL_W = [5.5 * cm, 2.8 * cm, 3.0 * cm, 6.7 * cm]

    # ── Cabeçalho da tabela ────────────────────────────────────────────────
    cab_row = [
        Paragraph('MÊS',      estilos['cab_esq']),
        Paragraph('Q NOTAS',  estilos['cab']),
        Paragraph('CABEÇAS',  estilos['cab']),
        Paragraph('VALOR (R$)', estilos['cab']),
    ]

    # ── Linhas dos 12 meses ────────────────────────────────────────────────
    dados_map: dict[str, tuple[int, float, float]] = {
        row[0]: (row[1], row[2], row[3]) for row in linhas_dados
    }

    linhas_tabela = [cab_row]
    for mm in MESES_ORDEM:
        chave = f'{mm}/{ano}'
        q, cab, val = dados_map.get(chave, (0, 0.0, 0.0))
        nome_mes = NOMES_MESES[mm]

        linhas_tabela.append([
            Paragraph(nome_mes,             estilos['dado']),
            Paragraph(str(q) if q else '',  estilos['dado_dir'] if q else estilos['dado']),
            Paragraph(f'{cab:.0f}' if cab else '', estilos['dado_dir']),
            Paragraph(f'R$ {val:,.2f}' if val else '', estilos['dado_dir']),
        ])

    # ── Linha TOTAL ────────────────────────────────────────────────────────
    linhas_tabela.append([
        Paragraph('TOTAL',                    estilos['total']),
        Paragraph(str(tot_notas),             estilos['total_dir']),
        Paragraph(f'{tot_cab:.0f}',           estilos['total_dir']),
        Paragraph(f'R$ {tot_val:,.2f}',       estilos['total_dir']),
    ])

    n_rows = len(linhas_tabela)
    n_dados = n_rows - 2  # sem cabeçalho e sem total

    # ── Estilos da tabela ──────────────────────────────────────────────────
    ts = [
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), AZUL_MED),
        ('ROWHEIGHT',  (0, 0), (-1, 0), 20),

        # Linhas alternadas nos dados
        *[('BACKGROUND', (0, i + 1), (-1, i + 1),
           AZUL_CLAR if i % 2 == 0 else BRANCO)
          for i in range(n_dados)],

        # Linha TOTAL
        ('BACKGROUND', (0, n_rows - 1), (-1, n_rows - 1), cor_secao),
        ('ROWHEIGHT',  (0, n_rows - 1), (-1, n_rows - 1), 20),

        # Alinhamento
        ('ALIGN',     (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN',     (0, 0), (0, -1),  'LEFT'),
        ('VALIGN',    (0, 0), (-1, -1), 'MIDDLE'),

        # Padding interno
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (0, -1),  8),
        ('RIGHTPADDING',  (-1, 0), (-1, -1), 8),

        # Grade
        ('GRID',      (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('LINEABOVE', (0, n_rows - 1), (-1, n_rows - 1), 1.5, cor_secao),
        ('ROWHEIGHT', (0, 1), (-1, n_rows - 2), 16),
    ]

    tabela = Table(linhas_tabela, colWidths=COL_W,
                   repeatRows=1, hAlign='LEFT')
    tabela.setStyle(TableStyle(ts))

    # ── Título colorido da seção ───────────────────────────────────────────
    titulo_tbl = Table(
        [[Paragraph(f'  {titulo}', estilos['titulo_secao'])]],
        colWidths=[sum(COL_W)],
        hAlign='LEFT',
    )
    titulo_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_secao),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    return [KeepTogether([titulo_tbl, tabela])]


# ── Capa / cabeçalho informativo ──────────────────────────────────────────────

def _bloco_cabecalho(notas: list[NFA], ano: str, estilos: dict) -> list:
    """Gera bloco de identificação acima das tabelas."""
    from nfa_extractor.domain.extractor import resumo_geral
    res = resumo_geral(notas)

    total_notas  = res['total_notas']
    total_cab    = res['total_cabecas']
    total_val    = res['total_valor']
    periodo      = f'{min(n.emissao for n in notas if n.emissao) if notas else "–"}  →  ' \
                   f'{max(n.emissao for n in notas if n.emissao) if notas else "–"}'

    # Nome do remetente (produtor) da primeira nota
    produtor = next((n.remetente.nome for n in notas if n.remetente.nome), '–')

    titulo_tbl = Table(
        [[Paragraph('PLANILHA DE GADO PARA IMPOSTO DE RENDA', ParagraphStyle(
            'Titulo', fontName='Helvetica-Bold', fontSize=14,
            alignment=TA_CENTER, textColor=BRANCO,
        ))]],
        colWidths=[18 * cm], hAlign='LEFT',
    )
    titulo_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), AZUL_ESC),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))

    info_data = [
        ['Produtor / Remetente:', produtor,   'Exercício:', ano],
        ['Período:',             periodo,     'Total de Notas:', str(total_notas)],
        ['Total de Cabeças:',    f'{total_cab:.0f}', 'Faturamento Total:', f'R$ {total_val:,.2f}'],
    ]
    est_label = ParagraphStyle('IL', fontName='Helvetica-Bold', fontSize=8,
                               textColor=AZUL_ESC, alignment=TA_LEFT)
    est_valor = ParagraphStyle('IV', fontName='Helvetica', fontSize=8,
                               textColor=PRETO, alignment=TA_LEFT)

    info_rows = []
    for row in info_data:
        info_rows.append([
            Paragraph(row[0], est_label), Paragraph(row[1], est_valor),
            Paragraph(row[2], est_label), Paragraph(row[3], est_valor),
        ])

    info_tbl = Table(info_rows, colWidths=[3.8 * cm, 6.7 * cm, 3.2 * cm, 4.3 * cm], hAlign='LEFT')
    info_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), AZUL_CLAR),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.HexColor('#A8C7D8')),
        ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]))

    return [titulo_tbl, Spacer(1, 0.3 * cm), info_tbl, Spacer(1, 0.5 * cm)]


# ── Função principal ──────────────────────────────────────────────────────────

def gerar_pdf_ir(notas: list[NFA], saida: str) -> None:
    """Gera o PDF da Planilha de Gado para IR a partir das NFAs extraídas.

    Estrutura:
      Cabeçalho identificador
      → VENDAS (12 meses + TOTAL)
      → REMESSAS (12 meses + TOTAL)
      → TRANSFERÊNCIAS (12 meses + TOTAL)
      → OUTRAS (12 meses + TOTAL)
      → TOTAL GERAL (12 meses + TOTAL)

    Args:
        notas: Lista de NFAs extraídas do PDF.
        saida: Caminho do arquivo PDF de destino.
    """
    from nfa_extractor.domain.extractor import resumo_geral

    if not notas:
        raise ValueError('Nenhuma nota fiscal para gerar a Planilha IR.')

    # Determina o ano de referência pela maioria das notas
    anos = [n.emissao[6:] for n in notas if n.emissao and len(n.emissao) == 10]
    ano = max(set(anos), key=anos.count) if anos else str(datetime.now().year)

    res = resumo_geral(notas)
    estilos = _estilos()

    # ── Monta dados de cada seção ──────────────────────────────────────────
    meses_disponiveis = res['por_mes']  # chave: "MM/AAAA"

    def _linhas(v_key: str, c_key: str, n_key: str):
        return [
            (f'{mm}/{ano}',
             meses_disponiveis.get(f'{mm}/{ano}', {}).get(n_key, 0),
             meses_disponiveis.get(f'{mm}/{ano}', {}).get(c_key, 0.0),
             meses_disponiveis.get(f'{mm}/{ano}', {}).get(v_key, 0.0))
            for mm in MESES_ORDEM
        ]

    cat = res['por_categoria']

    secoes = [
        {
            'titulo': 'VENDAS',
            'cor':    VERDE,
            'linhas': _linhas('vendas_valor', 'vendas_cabecas', 'vnd_notas'),
            'tot_n':  res['vendas_notas'],
            'tot_c':  res['vendas_cabecas'],
            'tot_v':  res['vendas_valor'],
        },
        {
            'titulo': 'REMESSAS',
            'cor':    AMARELO,
            'linhas': _linhas('rem_valor', 'rem_cabecas', 'rem_notas'),
            'tot_n':  cat.get('REMESSA', {}).get('notas', 0),
            'tot_c':  cat.get('REMESSA', {}).get('cabecas', 0.0),
            'tot_v':  cat.get('REMESSA', {}).get('valor', 0.0),
        },
        {
            'titulo': 'TRANSFERÊNCIAS',
            'cor':    CIANO,
            'linhas': _linhas('trf_valor', 'trf_cabecas', 'trf_notas'),
            'tot_n':  cat.get('TRANSFERENCIA', {}).get('notas', 0),
            'tot_c':  cat.get('TRANSFERENCIA', {}).get('cabecas', 0.0),
            'tot_v':  cat.get('TRANSFERENCIA', {}).get('valor', 0.0),
        },
        {
            'titulo': 'OUTRAS',
            'cor':    ROXO,
            'linhas': _linhas('out_valor', 'out_cabecas', 'out_notas'),
            'tot_n':  cat.get('OUTRAS', {}).get('notas', 0),
            'tot_c':  cat.get('OUTRAS', {}).get('cabecas', 0.0),
            'tot_v':  cat.get('OUTRAS', {}).get('valor', 0.0),
        },
        {
            'titulo': 'TOTAL GERAL',
            'cor':    AZUL_MED,
            'linhas': _linhas('valor', 'cabecas', 'notas'),
            'tot_n':  res['total_notas'],
            'tot_c':  res['total_cabecas'],
            'tot_v':  res['total_valor'],
        },
    ]

    # ── Story (conteúdo do PDF) ────────────────────────────────────────────
    story = _bloco_cabecalho(notas, ano, estilos)

    for s in secoes:
        story += _tabela_secao(
            titulo=s['titulo'],
            cor_secao=s['cor'],
            linhas_dados=s['linhas'],
            tot_notas=s['tot_n'],
            tot_cab=s['tot_c'],
            tot_val=s['tot_v'],
            estilos=estilos,
            ano=ano,
        )
        story.append(Spacer(1, 0.4 * cm))

    # ── Geração do documento ───────────────────────────────────────────────
    margem = 1.5 * cm
    doc = BaseDocTemplate(
        saida,
        pagesize=A4,
        leftMargin=margem, rightMargin=margem,
        topMargin=2.2 * cm, bottomMargin=1.5 * cm,
    )
    doc.ano_referencia = ano  # disponível no header_footer

    frame = Frame(
        margem, 1.5 * cm,
        W - 2 * margem, H - 2.2 * cm - 1.5 * cm,
        id='normal',
    )
    template = PageTemplate(id='main', frames=[frame], onPage=_header_footer)
    doc.addPageTemplates([template])
    doc.build(story)
