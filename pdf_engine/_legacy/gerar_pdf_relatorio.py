#!/usr/bin/env python3
"""
Gera PDF do relatório de auditoria a partir do JSON.
Usa reportlab para criar documento simples e legível.
"""

import json
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


def gerar_pdf(json_path: str, pdf_path: str):
    """Gera PDF do relatório de auditoria."""

    # Carregar JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    # Criar PDF
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()

    # Estilos customizados
    titulo_style = ParagraphStyle(
        'Titulo',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#003366'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    subtitulo_style = ParagraphStyle(
        'Subtitulo',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#003366'),
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )

    # Título
    story.append(Paragraph(dados['titulo'], titulo_style))
    story.append(Spacer(1, 0.2*inch))

    # Dados do contribuinte
    contrib_data = dados['contribuinte']
    story.append(Paragraph("Contribuinte", subtitulo_style))
    story.append(Paragraph(f"<b>Nome:</b> {contrib_data['nome']}", styles['Normal']))
    story.append(Paragraph(f"<b>CPF/CNPJ:</b> {contrib_data['cpf_cnpj']}", styles['Normal']))
    story.append(Spacer(1, 0.15*inch))

    # Período
    periodo = dados['periodo']
    story.append(Paragraph("Período", subtitulo_style))
    story.append(Paragraph(f"<b>De:</b> {periodo['inicio']} <b>até</b> {periodo['fim']}", styles['Normal']))
    story.append(Spacer(1, 0.15*inch))

    # Resumo
    resumo = dados['resumo']
    story.append(Paragraph("Resumo da Auditoria", subtitulo_style))

    resumo_data = [
        ['Metrica', 'Valor'],
        ['Total de Notas', str(resumo['total_notas'])],
        ['Quantidade Total', f"{resumo['quantidade_total']:.0f}"],
        ['Valor Total', f"R$ {resumo['valor_total']:,.2f}"],
    ]

    resumo_table = Table(resumo_data, colWidths=[3*inch, 2*inch])
    resumo_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
    ]))
    story.append(resumo_table)
    story.append(Spacer(1, 0.2*inch))

    # Notas principais
    story.append(Paragraph("Primeiras 20 Notas Fiscais", subtitulo_style))

    notas = dados.get('notas', [])[:20]
    notas_data = [
        ['Nº', 'Data', 'Remetente', 'Produto', 'Qtd', 'Valor']
    ]

    for nota in notas:
        notas_data.append([
            nota['numero'],
            nota['data'],
            nota['remetente'][:20],
            nota['produto'][:15],
            f"{nota['quantidade']:.0f}",
            f"R$ {nota['valor_total']:,.0f}"
        ])

    notas_table = Table(notas_data, colWidths=[0.7*inch, 0.9*inch, 1.4*inch, 1.3*inch, 0.6*inch, 1.1*inch])
    notas_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
    ]))
    story.append(notas_table)
    story.append(Spacer(1, 0.2*inch))

    # Rodapé
    story.append(Paragraph(
        f"<i>Relatório gerado em {dados['data']}</i>",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, textColor=colors.grey)
    ))

    # Gerar PDF
    doc.build(story)
    print(f"PDF gerado com sucesso: {pdf_path}")


if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Encontrar JSON mais recente
    output_dir = Path("./output_relatorios")
    jsons = list(output_dir.glob("*.json"))

    if not jsons:
        logger.error("Nenhum JSON encontrado")
        sys.exit(1)

    json_path = sorted(jsons)[-1]  # Mais recente
    pdf_path = json_path.with_suffix(".pdf")

    logger.info(f"Convertendo {json_path.name} para PDF...")
    gerar_pdf(str(json_path), str(pdf_path))
    logger.info(f"PDF salvo em: {pdf_path}")
