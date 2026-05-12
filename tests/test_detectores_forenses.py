"""Testes determinísticos das 5 tipologias forenses (A-07 / detectores_forenses.py).

Cada fixture em tests/fixtures/forenses/ é o caso golden mínimo que aciona
o respectivo detector. Casos negativos (sem alerta) também são cobertos.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from horizon_blue_one.agents.detectores_forenses import (
    detectar_anomalia_temporal,
    detectar_carrossel,
    detectar_devolucao_posterior,
    detectar_fornecedor_fantasma,
    detectar_smurfing,
)

DIR_FIXTURES = Path(__file__).parent / "fixtures" / "forenses"


def _carregar(nome: str) -> list[dict]:
    with (DIR_FIXTURES / nome).open(encoding="utf-8") as fp:
        return json.load(fp)["notas"]


# ── Golden cases (cada fixture aciona o detector correspondente) ─────────────


class TestGoldenFixtures:
    def test_carrossel_fiscal(self):
        assert detectar_carrossel(_carregar("carrossel_fiscal.json")) is True

    def test_smurfing_rural(self):
        assert detectar_smurfing(_carregar("smurfing_rural.json")) is True

    def test_fornecedor_fantasma(self):
        suspeitos = detectar_fornecedor_fantasma(_carregar("fornecedor_fantasma.json"))
        assert suspeitos == ["F001", "F002"]

    def test_devolucao_posterior(self):
        assert detectar_devolucao_posterior(_carregar("devolucao_posterior.json")) is True

    def test_anomalia_temporal(self):
        assert detectar_anomalia_temporal(_carregar("anomalia_temporal.json")) is True


# ── Casos negativos (sanity check — sem alerta quando não deve haver) ────────


class TestCasosNegativos:
    def test_carrossel_nao_aciona_em_valores_unicos(self):
        notas = [
            {"valor_total": 1000.0, "cfop": "5102"},
            {"valor_total": 2000.0, "cfop": "5102"},
            {"valor_total": 3000.0, "cfop": "5102"},
        ]
        assert detectar_carrossel(notas) is False

    def test_smurfing_nao_aciona_com_menos_de_5_pequenas(self):
        notas = [
            {"valor_total": 5000.0, "data": "2026-03-02"},
            {"valor_total": 6000.0, "data": "2026-03-03"},
        ]
        assert detectar_smurfing(notas) is False

    def test_fornecedor_fantasma_lista_vazia_com_ie_valida(self):
        notas = [
            {"natureza": "VENDA DE GADO", "posicao": "DESTINATARIO", "ie_remetente": "123456789", "numero": "X1"},
        ]
        assert detectar_fornecedor_fantasma(notas) == []

    def test_devolucao_posterior_sem_par_correspondente(self):
        notas = [
            {"natureza": "VENDA DE GADO", "remetente_cpf": "111", "valor_total": 10000.0},
            {"natureza": "DEVOLUCAO", "destinatario_cpf": "999", "valor_total": 1000.0},
        ]
        assert detectar_devolucao_posterior(notas) is False

    def test_anomalia_temporal_nao_aciona_com_valores_homogeneos(self):
        notas = [{"valor_total": 10000.0} for _ in range(8)]
        assert detectar_anomalia_temporal(notas) is False

    def test_anomalia_temporal_nao_aciona_com_menos_de_6_notas(self):
        notas = [{"valor_total": v} for v in (100, 200, 300, 400, 500000)]
        assert detectar_anomalia_temporal(notas) is False


# ── Parametrizado: cada fixture deve ter os campos mínimos ───────────────────


@pytest.mark.parametrize("arquivo", [
    "carrossel_fiscal.json",
    "smurfing_rural.json",
    "fornecedor_fantasma.json",
    "devolucao_posterior.json",
    "anomalia_temporal.json",
])
def test_fixtures_tem_estrutura_minima(arquivo):
    caminho = DIR_FIXTURES / arquivo
    assert caminho.exists(), f"fixture {arquivo} sumiu"
    with caminho.open(encoding="utf-8") as fp:
        dados = json.load(fp)
    assert "notas" in dados and len(dados["notas"]) > 0
    assert "descricao" in dados
    assert "esperado" in dados
