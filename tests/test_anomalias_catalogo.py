"""Testes do catálogo AN-01..AN-18 — completude e integridade.

P0-4: garante que todas as 18 tipologias estão catalogadas com campos
obrigatórios, severidades válidas e cruzamentos documentais definidos.
"""
from __future__ import annotations

import pytest

from horizon_blue_one.orgaudi.anomalias import (
    CATALOGO,
    TipologiaAnomalia,
    buscar_por_codigo,
    listar_criticos,
)


SEVERIDADES_VALIDAS = {"CRÍTICO", "ALTO", "MÉDIO", "BAIXO"}


# ── Completude: 18 tipologias exatas ────────────────────────────────────────


def test_catalogo_tem_18_tipologias():
    assert len(CATALOGO) == 18


def test_catalogo_codigos_an01_a_an18():
    esperados = {f"AN-{i:02d}" for i in range(1, 19)}
    assert set(CATALOGO.keys()) == esperados


# ── Integridade de cada tipologia ───────────────────────────────────────────


@pytest.mark.parametrize("codigo", sorted(CATALOGO.keys()))
def test_cada_tipologia_tem_campos_obrigatorios(codigo: str):
    tip = CATALOGO[codigo]
    assert isinstance(tip, TipologiaAnomalia)
    assert tip.codigo == codigo
    assert tip.nome and isinstance(tip.nome, str)
    assert tip.eixo and isinstance(tip.eixo, str)
    assert tip.severidade in SEVERIDADES_VALIDAS
    assert tip.descricao and isinstance(tip.descricao, str)
    assert isinstance(tip.cruzamentos, list) and len(tip.cruzamentos) > 0


@pytest.mark.parametrize("codigo", sorted(CATALOGO.keys()))
def test_cada_tipologia_tem_pelo_menos_um_cruzamento(codigo: str):
    tip = CATALOGO[codigo]
    assert len(tip.cruzamentos) >= 1
    assert all(isinstance(c, str) and c.strip() for c in tip.cruzamentos)


# ── Distribuição de severidade (sanity) ─────────────────────────────────────


def test_existem_tipologias_criticas():
    criticos = listar_criticos()
    # AN-01 Smurfing, AN-02 Carrossel, AN-03 Nota Fria, AN-09 IE Inativa,
    # AN-12 Caixa Dois → mínimo 5
    assert len(criticos) >= 5
    codigos_criticos = {c.codigo for c in criticos}
    assert "AN-01" in codigos_criticos
    assert "AN-02" in codigos_criticos
    assert "AN-12" in codigos_criticos


def test_listar_criticos_filtra_corretamente():
    for tip in listar_criticos():
        assert tip.severidade == "CRÍTICO"


# ── buscar_por_codigo ───────────────────────────────────────────────────────


def test_buscar_por_codigo_uppercase():
    tip = buscar_por_codigo("AN-01")
    assert tip is not None
    assert tip.nome == "Smurfing Rural"


def test_buscar_por_codigo_lowercase():
    tip = buscar_por_codigo("an-05")
    assert tip is not None
    assert tip.codigo == "AN-05"


def test_buscar_por_codigo_inexistente_retorna_none():
    assert buscar_por_codigo("AN-99") is None
    assert buscar_por_codigo("XYZ") is None


# ── Coerência semântica (regressão de catálogo) ─────────────────────────────


def test_an01_smurfing_eixo_fragmentacao():
    assert CATALOGO["AN-01"].eixo == "Fragmentação"


def test_an02_carrossel_eixo_circularidade():
    assert CATALOGO["AN-02"].eixo == "Circularidade"


def test_an18_ausencia_gta_severidade_alta():
    assert CATALOGO["AN-18"].nome.startswith("Ausência de GTA")
    assert CATALOGO["AN-18"].severidade == "ALTO"


def test_an15_funrural_subdeclarado_referencia_lcdpr():
    assert "LCDPR" in CATALOGO["AN-15"].cruzamentos
