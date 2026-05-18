#!/usr/bin/env python3
"""
Script final de auditoria fiscal para NFAs do Tocantins.
Extrai, processa e gera relatório em PDF.
"""

import json
import re
import pdfplumber
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("auditoria_final")


class NFA:
    """Nota Fiscal extraída do Tocantins."""

    def __init__(self, **kwargs):
        self.numero = kwargs.get('numero', '')
        self.data = kwargs.get('data', '')
        self.remetente_cpf = kwargs.get('remetente_cpf', '')
        self.remetente_nome = kwargs.get('remetente_nome', '')
        self.cfop = kwargs.get('cfop', '')
        self.destinatario_cpf = kwargs.get('destinatario_cpf', '')
        self.destinatario_nome = kwargs.get('destinatario_nome', '')
        self.produto = kwargs.get('produto', '')
        self.quantidade = float(kwargs.get('quantidade', 0) or 0)
        self.valor_unitario = float(kwargs.get('valor_unitario', 0) or 0)
        self.valor_total = float(kwargs.get('valor_total', 0) or 0)


def limpar_valor(s: str) -> float:
    """Converte string com vírgula/ponto em float."""
    if not s:
        return 0
    s = str(s).strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0


def extrair_nfas_completo(pdf_path: str) -> tuple[List[NFA], str, str]:
    """Extrai todas as NFAs dos PDFs de entrada e saída."""

    nfas = []
    nome_contribuinte = "DEUSDETE"
    cpf_contribuinte = ""

    with pdfplumber.open(pdf_path) as pdf:
        texto_completo = "\n".join([
            p.extract_text() or "" for p in pdf.pages
        ])

    # Extrair CPF
    match_cpf = re.search(r"CNPJ/CPF:\s*([\d./-]+)", texto_completo)
    if match_cpf:
        cpf_contribuinte = match_cpf.group(1).strip()

    # Processar cada linha
    lines = texto_completo.split('\n')
    for line in lines:
        # Padrão: começa com 7-8 dígitos (número da NFA)
        if not re.match(r'^\d{7,8}\s', line):
            continue

        # Padrão simples: separa por espaços múltiplos
        # NÚMERO | DATA | CPF_REM | NOME_REM | CFOP | CPF_DEST | NOME_DEST | PRODUTO | QTD | V.UNIT | V.TOTAL

        # Usar regex mais flexível
        match = re.match(
            r'^(\d{7,8})\s+' +  # [0] número
            r'(\d{2}/\d{2}/\d{4})\s+' +  # [1] data
            r'([\d./-]{14})\s+' +  # [2] CPF remetente
            r'([A-Z\s]{10,50}?)\s+' +  # [3] Nome remetente (10-50 chars)
            r'(\d\.?\d{3})\s+' +  # [4] CFOP
            r'([\d./-]{14})\s+' +  # [5] CPF destinatário
            r'([A-Z\s]{10,50}?)\s+' +  # [6] Nome destinatário
            r'(BOVINO[A-Z0-9\s–]+?)\s+' +  # [7] Produto (começa com BOVINO)
            r'([\d.,]+)\s+' +  # [8] quantidade
            r'([\d.,]+)\s+' +  # [9] valor unitário
            r'([\d.,]+)\s*$',  # [10] valor total
            line
        )

        if match:
            try:
                nfa = NFA(
                    numero=match.group(1),
                    data=match.group(2),
                    remetente_cpf=match.group(3).replace(' ', ''),
                    remetente_nome=match.group(4).strip(),
                    cfop=match.group(5),
                    destinatario_cpf=match.group(6).replace(' ', ''),
                    destinatario_nome=match.group(7).strip(),
                    produto=match.group(8).strip(),
                    quantidade=limpar_valor(match.group(9)),
                    valor_unitario=limpar_valor(match.group(10)),
                    valor_total=limpar_valor(match.group(11)),
                )
                nfas.append(nfa)
            except Exception as e:
                logger.debug(f"Erro ao parsear linha: {e}")

    return nfas, nome_contribuinte, cpf_contribuinte


def main():
    """Função principal."""

    logger.info("=" * 70)
    logger.info("AUDITORIA FISCAL — DEUSDETE 2025")
    logger.info("=" * 70)

    input_dir = Path("./input_pdfs")
    output_dir = Path("./output_relatorios")
    output_dir.mkdir(exist_ok=True)

    pdfs = list(input_dir.glob("*.pdf"))
    logger.info(f"\nEncontrados {len(pdfs)} PDFs\n")

    # [FASE 1] Extração
    logger.info("[FASE 1] Extração de NFAs")
    todas_nfas = []
    nome_contribuinte = "DEUSDETE"
    cpf_contribuinte = ""

    for pdf_path in pdfs:
        logger.info(f"  Processando {pdf_path.name}...")
        nfas, nome, cpf = extrair_nfas_completo(str(pdf_path))

        if nfas:
            todas_nfas.extend(nfas)
            nome_contribuinte = nome or nome_contribuinte
            cpf_contribuinte = cpf or cpf_contribuinte
            logger.info(f"    ✓ Extraídas {len(nfas)} NFAs")
        else:
            logger.warning(f"    ⚠ Nenhuma NFA extraída")

    if not todas_nfas:
        logger.error("\nErro: Nenhuma NFA foi extraída!")
        return 1

    logger.info(f"\nTotal de NFAs extraídas: {len(todas_nfas)}")

    # [FASE 2] Resumo
    logger.info("\n[FASE 2] Resumo das NFAs")

    total_valor = sum(n.valor_total for n in todas_nfas)
    total_qtd = sum(n.quantidade for n in todas_nfas)
    total_valor_unit = sum(n.valor_unitario * n.quantidade for n in todas_nfas)

    logger.info(f"  Contribuinte: {nome_contribuinte} ({cpf_contribuinte})")
    logger.info(f"  Total de notas: {len(todas_nfas)}")
    logger.info(f"  Total de cabeças: {total_qtd:.1f}")
    logger.info(f"  Valor total: R$ {total_valor:,.2f}")

    # Agrupar por CFOP
    por_cfop = {}
    for nfa in todas_nfas:
        cfop = nfa.cfop
        if cfop not in por_cfop:
            por_cfop[cfop] = {'qtd': 0, 'valor': 0, 'notas': 0}
        por_cfop[cfop]['qtd'] += nfa.quantidade
        por_cfop[cfop]['valor'] += nfa.valor_total
        por_cfop[cfop]['notas'] += 1

    logger.info("\n  Por CFOP:")
    for cfop, dados in sorted(por_cfop.items()):
        tipo = "Entrada" if cfop == "5.101" else "Saída" if cfop == "5.914" else cfop
        logger.info(f"    {cfop} ({tipo}): {dados['notas']} notas | {dados['qtd']:.1f} qtd | R$ {dados['valor']:,.2f}")

    # [FASE 3] Relatório JSON
    logger.info("\n[FASE 3] Gerando Relatório")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    relatorio = {
        "titulo": "Relatório de Auditoria Fiscal",
        "data_geracao": datetime.now().isoformat(),
        "contribuinte": {
            "nome": nome_contribuinte,
            "cpf_cnpj": cpf_contribuinte
        },
        "periodo": {
            "inicio": "2025-01-01",
            "fim": "2025-12-31"
        },
        "resumo": {
            "total_notas": len(todas_nfas),
            "total_quantidade": round(total_qtd, 2),
            "total_valor": round(total_valor, 2),
            "valor_unitario_total": round(total_valor_unit, 2)
        },
        "por_cfop": {
            cfop: {
                "tipo": "Entrada" if cfop == "5.101" else "Saída" if cfop == "5.914" else "Outros",
                "notas": dados['notas'],
                "quantidade": round(dados['qtd'], 2),
                "valor_total": round(dados['valor'], 2)
            }
            for cfop, dados in por_cfop.items()
        },
        "notas": [
            {
                "numero": n.numero,
                "data": n.data,
                "cfop": n.cfop,
                "remetente": n.remetente_nome,
                "destinatario": n.destinatario_nome,
                "produto": n.produto,
                "quantidade": round(n.quantidade, 2),
                "valor_unitario": round(n.valor_unitario, 2),
                "valor_total": round(n.valor_total, 2)
            }
            for n in todas_nfas
        ]
    }

    # Salvar JSON
    json_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)

    logger.info(f"  ✓ Relatório JSON: {json_path}")

    # [FASE 4] Gerar PDF (se possível)
    logger.info("\n[FASE 4] Geração de PDF")

    try:
        from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json

        dados_pdf = {
            "contribuinte": {
                "nome": nome_contribuinte,
                "cpf": cpf_contribuinte.replace(".", "").replace("/", "").replace("-", "") if cpf_contribuinte else "00000000000",
                "ie": "",
                "municipio": "Tocantins"
            },
            "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
            "notas": [
                {
                    "numero": n.numero,
                    "serie": "1",
                    "data": n.data,
                    "destinatario": n.destinatario_nome,
                    "produto": n.produto,
                    "quantidade": round(n.quantidade, 2),
                    "valor_unitario": round(n.valor_unitario, 2),
                    "valor_total": round(n.valor_total, 2),
                }
                for n in todas_nfas
            ]
        }

        pdf_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.pdf"
        resultado = gerar_laudo_de_json(dados_pdf, str(pdf_path), strict_cpf=False)
        logger.info(f"  ✓ Relatório PDF: {pdf_path}")

    except Exception as e:
        logger.warning(f"  ⚠ Não foi possível gerar PDF: {e}")

    # [RESUMO FINAL]
    logger.info("\n" + "=" * 70)
    logger.info("AUDITORIA CONCLUÍDA COM SUCESSO!")
    logger.info("=" * 70)
    logger.info(f"\nResultados salvos em: {output_dir}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
