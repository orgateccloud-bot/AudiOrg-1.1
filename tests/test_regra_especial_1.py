"""Testes da Regra Especial 1 — reclassificação VENDA → COMPRA rural.

P0-4: regras que produzem o veredito fiscal precisam de cobertura.
Base legal: NBC TG 16/25 + Lei 9.250/1995. Não modificar sem CRC-GO.
"""
from __future__ import annotations

import pytest

from horizon_blue_one.orgaudi.regra_especial_1 import (
    ATIVIDADES_RURAIS,
    aplicar_regra_especial_1,
)


def _nota(**overrides) -> dict:
    base = {
        "numero": "1",
        "natureza": "VENDA",
        "posicao": "DESTINATARIO",
        "atividade": "bovino",
        "tipo_doc": "nfa-e",
        "valor_total": 10000.0,
    }
    base.update(overrides)
    return base


# ── Caminho positivo (RE-1 aplicada) ────────────────────────────────────────


def test_re1_aplicada_para_venda_destinatario_rural():
    nota = aplicar_regra_especial_1(_nota())
    assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"
    assert nota["natureza_exibicao"] == "COMPRA"
    assert nota["categoria_contabil"] == "DESPESA"
    assert nota["efeito_irpf"] == "SUBTRAI"
    assert nota["confianca"] == 0.99
    assert nota["alertas_re1"] == []


def test_re1_contas_contabeis_corretas():
    nota = aplicar_regra_especial_1(_nota())
    assert nota["conta_debito"]  == "1.1.2.01"   # Gado em Rebanho
    assert nota["conta_credito"] == "2.1.1.1.01"  # Fornecedores


@pytest.mark.parametrize("atividade", sorted(ATIVIDADES_RURAIS))
def test_re1_aplicada_para_toda_atividade_do_whitelist(atividade: str):
    nota = aplicar_regra_especial_1(_nota(atividade=atividade))
    assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"


def test_re1_aplica_case_insensitive_na_posicao():
    nota = aplicar_regra_especial_1(_nota(posicao="destinatario"))
    assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"


def test_re1_aceita_posicao_destinatario_com_acento():
    # "DESTIN" prefix substring match
    nota = aplicar_regra_especial_1(_nota(posicao="DESTINATÁRIO FINAL"))
    assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"


# ── Caminho negativo (RE-1 NÃO aplicada) ────────────────────────────────────


def test_re1_nao_aplica_quando_remetente():
    nota = aplicar_regra_especial_1(_nota(posicao="REMETENTE"))
    assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"
    assert nota["natureza_exibicao"] == "VENDA"
    assert nota["categoria_contabil"] == "RECEITA"
    assert nota["efeito_irpf"] == "SOMA"


def test_re1_nao_aplica_quando_natureza_nao_venda():
    nota = aplicar_regra_especial_1(_nota(natureza="REMESSA"))
    assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"
    assert nota["efeito_irpf"] == "NEUTRO"


def test_re1_nao_aplica_quando_atividade_nao_rural():
    nota = aplicar_regra_especial_1(_nota(atividade="comércio varejista"))
    assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"


def test_re1_nao_aplica_quando_tipo_doc_nao_nfa():
    nota = aplicar_regra_especial_1(_nota(tipo_doc="nfe-55"))
    assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"


def test_re1_nao_aplica_com_campos_vazios():
    nota = aplicar_regra_especial_1({})
    assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"
    assert nota["confianca"] == 0.99


# ── Bordas de valor (alertas + confiança reduzida) ──────────────────────────


def test_re1_alerta_valor_acima_500k_reduz_confianca():
    nota = aplicar_regra_especial_1(_nota(valor_total=750_000.0))
    assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"
    assert nota["confianca"] == 0.75
    assert any("500k" in a for a in nota["alertas_re1"])


def test_re1_alerta_valor_abaixo_100_reduz_confianca():
    nota = aplicar_regra_especial_1(_nota(valor_total=50.0))
    assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"
    assert nota["confianca"] == 0.75
    assert any("100" in a for a in nota["alertas_re1"])


def test_re1_valor_no_meio_da_faixa_sem_alerta():
    nota = aplicar_regra_especial_1(_nota(valor_total=50_000.0))
    assert nota["alertas_re1"] == []
    assert nota["confianca"] == 0.99


# ── Coerência: aplicar 2x não muda o resultado ──────────────────────────────


def test_re1_idempotente():
    nota1 = aplicar_regra_especial_1(_nota())
    # Re-aplicar sobre a saída deve manter o mesmo resultado (mas categoria
    # contábil já foi reescrita — a re-aplicação parte de "natureza=VENDA")
    nota2 = aplicar_regra_especial_1(dict(nota1))
    assert nota2["regra_aplicada"] == nota1["regra_aplicada"]
    assert nota2["categoria_contabil"] == nota1["categoria_contabil"]
