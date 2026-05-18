"""
Parser para NFAs do Tocantins usando regex no texto extraído.
"""

import re
import pdfplumber
from typing import List, Dict, Any


class NFA_Tocantins:
    """Representa uma nota fiscal do Tocantins."""

    def __init__(self, **kwargs):
        self.numero = kwargs.get('numero', '')
        self.data_emissao = kwargs.get('data_emissao', '')
        self.remetente_cpf = kwargs.get('remetente_cpf', '')
        self.remetente_nome = kwargs.get('remetente_nome', '')
        self.destinatario_cpf = kwargs.get('destinatario_cpf', '')
        self.destinatario_nome = kwargs.get('destinatario_nome', '')
        self.produto = kwargs.get('produto', '')
        self.quantidade = float(kwargs.get('quantidade', 0) or 0)
        self.valor_unitario = float(kwargs.get('valor_unitario', 0) or 0)
        self.valor_total = float(kwargs.get('valor_total', 0) or 0)

    def __repr__(self):
        return f"NFA#{self.numero} | {self.produto} | R${self.valor_total:,.2f}"


def extrair_nfas_tocantins_regex(caminho_pdf: str) -> tuple[List[NFA_Tocantins], str, str]:
    """Extrai NFAs usando regex no texto do PDF."""

    nfas = []
    nome_contribuinte = "DEUSDETE"
    cpf_contribuinte = ""

    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() or ""

    # Extrair CPF do contribuinte
    match_cpf = re.search(r"CNPJ/CPF:\s*([\d./-]+)", texto_completo)
    if match_cpf:
        cpf_contribuinte = match_cpf.group(1).strip()

    # Extrair nome do contribuinte
    match_nome = re.search(
        r"Raz[ãa]o\s+Social.*?Destinat[ãa]rio\s+(.*?)(?:\s+CNPJ|$)",
        texto_completo,
        re.IGNORECASE | re.DOTALL
    )
    if match_nome:
        nome = match_nome.group(1).strip().split('\n')[0]
        if nome:
            nome_contribuinte = nome

    # Pattern para linhas de notas:
    # Número (7-8 dígitos) | Data | CPF | Nome | CFOP | CPF | Nome | Produto | Qtd | Valor Unitário | Valor Total
    # Exemplo: 66191862 15/01/2025 014.779.641-50 MIGUEL BONFIM... 5.101 263.489.931-91 DEUSDETE... BOVINO... 7,00 1.600,00 11.200,00

    # Padrão mais flexível - procurar por linhas com números e valores
    lines = texto_completo.split('\n')

    for i, line in enumerate(lines):
        # Skip linhas vazias ou muito curtas
        if not line or len(line) < 50:
            continue

        # Procurar por padrão: número | data | cpf | ... | valor
        # Padrão simples: começa com 7-8 dígitos
        match_linha = re.search(
            r'^(\d{7,8})\s+(\d{2}/\d{2}/\d{4})\s+' +  # número e data
            r'([\d./-]+)\s+(.{30,100}?)\s+' +  # CPF remetente e nome (até 100 chars)
            r'(\d\.?\d{3})\s+' +  # CFOP (5.101, 5.914, etc)
            r'([\d./-]+)\s+(.{20,100}?)\s+' +  # CPF destinatário e nome (até 100 chars)
            r'(.{20,150}?)\s+' +  # Produto (20-150 chars, pode incluir "Comum", espaços)
            r'([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$',  # Qtd, Valor Unit, Valor Total
            line
        )

        if match_linha:
            try:
                def limpar_numero(s):
                    """Remove separadores de milhar e decimal."""
                    if not s:
                        return 0
                    s = str(s).replace('.', '').replace(',', '.')
                    return float(s)

                nfa = NFA_Tocantins(
                    numero=match_linha.group(1),
                    data_emissao=match_linha.group(2),
                    remetente_cpf=match_linha.group(3).strip(),
                    remetente_nome=match_linha.group(4).strip(),
                    destinatario_cpf=match_linha.group(6).strip(),
                    destinatario_nome=match_linha.group(7).strip(),
                    produto=match_linha.group(8).strip(),
                    quantidade=limpar_numero(match_linha.group(9)),
                    valor_unitario=limpar_numero(match_linha.group(10)),
                    valor_total=limpar_numero(match_linha.group(11)),
                )
                nfas.append(nfa)
            except (IndexError, ValueError) as e:
                continue

    return nfas, nome_contribuinte, cpf_contribuinte


def main():
    """Teste."""
    import sys

    if len(sys.argv) < 2:
        print("Uso: python parser_nfa_regex.py <arquivo_pdf>")
        return 1

    pdf_path = sys.argv[1]
    nfas, nome, cpf = extrair_nfas_tocantins_regex(pdf_path)

    print(f"Contribuinte: {nome} ({cpf})")
    print(f"Total de NFAs extraídas: {len(nfas)}\n")

    for nfa in nfas[:10]:  # Mostrar primeiras 10
        print(nfa)

    if nfas:
        total_valor = sum(n.valor_total for n in nfas)
        total_qtd = sum(n.quantidade for n in nfas)
        print(f"\nResumo:")
        print(f"  Total de notas: {len(nfas)}")
        print(f"  Total quantidade: {total_qtd}")
        print(f"  Total valor: R$ {total_valor:,.2f}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
