"""Fixtures compartilhadas entre todas as suítes de testes do NFA Extractor."""

import sys
from pathlib import Path

import pytest

# Garante que o diretório raiz do projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractor import NFA, Parte, Produto


@pytest.fixture
def produto_simples() -> Produto:
    """Produto com valores básicos para testes."""
    return Produto(
        codigo='1070',
        descricao='GADO BOVINO NELORE MACHO PARA CRIA ATE 12 MESES CB',
        quantidade=10.0,
        vlr_icms=0.0,
        vlr_unitario=2500.0,
        vlr_total=25000.0,
    )


@pytest.fixture
def parte_comprador() -> Parte:
    """Parte (comprador) com dados completos para testes."""
    return Parte(
        nome='FRIGORIFICO EXEMPLO LTDA',
        ie='987654321',
        cpf_cnpj='12.345.678/0001-90',
        municipio='GOIANIA',
    )


@pytest.fixture
def parte_produtor() -> Parte:
    """Parte (produtor rural) com dados completos."""
    return Parte(
        nome='JOAO DA SILVA',
        ie='123456789',
        cpf_cnpj='012.345.678-90',
        municipio='TROMBAS',
    )


@pytest.fixture
def nfa_venda(parte_comprador: Parte, produto_simples: Produto) -> NFA:
    """NFA de VENDA completa para testes."""
    return NFA(
        chave_acesso='1' * 44,
        numero='123456',
        emissao='15/04/2025',
        natureza='VENDA DE GADO BOVINO',
        local_emissao='AGENCIA FAZENDARIA DE TROMBAS',
        destinatario=parte_comprador,
        produtos=[produto_simples],
    )


@pytest.fixture
def nfa_remessa() -> NFA:
    """NFA de REMESSA para testes."""
    return NFA(
        numero='234567',
        emissao='20/05/2025',
        natureza='REMESSA DE BEZERROS PARA RECRIA',
        local_emissao='NOTA EMITIDA PELO PRÓPRIO CONTRIBUINTE',
        destinatario=Parte(
            nome='FAZENDA BOA VISTA',
            cpf_cnpj='98.765.432/0001-10',
            municipio='FORMOSO',
        ),
        produtos=[Produto(quantidade=15.0, vlr_total=30000.0)],
    )


@pytest.fixture
def lista_notas_mock(nfa_venda: NFA, nfa_remessa: NFA) -> list[NFA]:
    """Lista com 3 notas (2 vendas + 1 remessa) para testes de agregação."""
    nfa_venda2 = NFA(
        numero='345678',
        emissao='10/04/2025',
        natureza='VENDA DE GADO BOVINO',
        destinatario=Parte(
            nome='FRIGORIFICO EXEMPLO LTDA',
            cpf_cnpj='12.345.678/0001-90',
            municipio='GOIANIA',
        ),
        produtos=[Produto(quantidade=5.0, vlr_total=12500.0)],
    )
    return [nfa_venda, nfa_remessa, nfa_venda2]
