"""
Parser especializado para NFAs do Tocantins em formato tabular PDF.
Extrai tabelas estruturadas de entrada/saída.
"""

import re
import pdfplumber
from datetime import datetime
from typing import List, Dict, Any


class LinhaTabularNFA:
    """Representa uma linha da tabela de NFAs do Tocantins."""

    def __init__(self, dados: Dict[str, Any]):
        self.numero = dados.get('numero', '')
        self.data_emissao = dados.get('data_emissao', '')
        self.remetente_cpf = dados.get('remetente_cpf', '')
        self.remetente_nome = dados.get('remetente_nome', '')
        self.cfop = dados.get('cfop', '')
        self.destinatario_cpf = dados.get('destinatario_cpf', '')
        self.destinatario_nome = dados.get('destinatario_nome', '')
        self.produto_desc = dados.get('produto_desc', '')
        self.quantidade = float(dados.get('quantidade', 0) or 0)
        self.valor_unitario = float(dados.get('valor_unitario', 0) or 0)
        self.valor_total = float(dados.get('valor_total', 0) or 0)

    def __repr__(self):
        return f"NFA#{self.numero} | {self.produto_desc} | Qtd:{self.quantidade} | Total:R${self.valor_total:,.2f}"


def extrair_nfas_tocantins(caminho_pdf: str) -> tuple[List[LinhaTabularNFA], str, str]:
    """
    Extrai NFAs do PDF estruturado do Tocantins.

    Returns:
        (lista_nfas, nome_contribuinte, cpf_contribuinte)
    """
    nfas = []
    nome_contribuinte = ""
    cpf_contribuinte = ""

    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = ""
        tabelas_todas = []

        # Extrair texto e tabelas
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""
            tabelas = page.extract_tables()
            if tabelas:
                tabelas_todas.extend(tabelas)

    # Extrair CPF/CNPJ do contribuinte
    match_cpf = re.search(r"CNPJ/CPF:\s*([\d./-]+)", texto_completo)
    if match_cpf:
        cpf_contribuinte = match_cpf.group(1).strip()

    # Extrair nome do contribuinte (procura por "DEUSDETE" ou similar)
    match_nome = re.search(r"DESTINAT[ÁA]RIO:\s*(.*?)(?:\s+CNPJ|\s+CPF|$)", texto_completo, re.IGNORECASE)
    if not match_nome:
        match_nome = re.search(r"Raz[ãa]o Social.*?:\s*(.*?)(?:\n|$)", texto_completo)
    if match_nome:
        nome_contribuinte = match_nome.group(1).strip()
    else:
        nome_contribuinte = "CONTRIBUINTE"

    # Processar tabelas extraídas
    for tabela in tabelas_todas:
        # Pular cabeçalho (primeira linha com "N° Nota", "Dt.Emissão", etc)
        if not tabela or len(tabela) < 2:
            continue

        # Procurar linhas que começam com número (número da nota)
        for row_idx, row in enumerate(tabela[1:], 1):  # Pular primeira linha (cabeçalho)
            if not row or len(row) < 11:
                continue

            try:
                # Colunas esperadas (baseadas no layout do Tocantins):
                # 0: Nº Nota, 1: Dt.Emissão, 2: CNPJ Remetente, 3: Remetente,
                # 4: CFOP, 5: CNPJ Destinatário, 6: Destinatário, 7: Produto,
                # 8: Quantidade, 9: Valor Unit, 10: Vlr Total

                numero = str(row[0] or "").strip()
                if not numero or not numero[0].isdigit():
                    continue

                nfa = LinhaTabularNFA({
                    'numero': numero,
                    'data_emissao': str(row[1] or "").strip(),
                    'remetente_cpf': str(row[2] or "").strip(),
                    'remetente_nome': str(row[3] or "").strip(),
                    'cfop': str(row[4] or "").strip(),
                    'destinatario_cpf': str(row[5] or "").strip(),
                    'destinatario_nome': str(row[6] or "").strip(),
                    'produto_desc': str(row[7] or "").strip(),
                    'quantidade': row[8],
                    'valor_unitario': row[9],
                    'valor_total': row[10],
                })

                nfas.append(nfa)

            except (IndexError, ValueError, TypeError) as e:
                # Linha mal formatada, pular
                continue

    return nfas, nome_contribuinte, cpf_contribuinte


def main():
    """Teste do parser."""
    import sys

    if len(sys.argv) < 2:
        print("Uso: python parser_nfa_tocantins.py <arquivo_pdf>")
        return 1

    pdf_path = sys.argv[1]
    nfas, nome, cpf = extrair_nfas_tocantins(pdf_path)

    print(f"Contribuinte: {nome} ({cpf})")
    print(f"Total de NFAs extraídas: {len(nfas)}")
    print("\nNFAs:")
    for nfa in nfas:
        print(f"  {nfa}")

    # Resumo
    total_valor = sum(n.valor_total for n in nfas)
    total_qtd = sum(n.quantidade for n in nfas)
    print(f"\nResumo:")
    print(f"  Total de notas: {len(nfas)}")
    print(f"  Total de quantidade: {total_qtd}")
    print(f"  Total de valor: R$ {total_valor:,.2f}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
