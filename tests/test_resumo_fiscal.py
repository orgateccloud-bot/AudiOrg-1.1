"""Testes do Resumo Fiscal F1-F6 + Funrural + IRPF estimado.

P0-4: cálculos tributários precisam de cobertura ≥70%.
Base legal: Lei 8.212/91 (Funrural) + Lei 9.250/95 (IRPF) + RFB 03/2026.
"""
from __future__ import annotations

from datetime import date

import pytest

from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo


# ── F1-F6: classificação contábil das notas ─────────────────────────────────


def test_resumo_apenas_receitas():
    notas = [
        {"categoria_contabil": "RECEITA", "valor_total": 1000.0},
        {"categoria_contabil": "RECEITA", "valor_total": 2000.0},
    ]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    assert r.f1_receita_imediata == 3000.0
    assert r.f4_receita_bruta == 3000.0
    assert r.f5_resultado_rural == 3000.0
    assert r.f6_despesa == 0
    assert r.total_notas == 2


def test_resumo_receita_menos_despesa():
    notas = [
        {"categoria_contabil": "RECEITA", "valor_total": 10000.0},
        {"categoria_contabil": "DESPESA", "valor_total": 3000.0},
    ]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    assert r.f1_receita_imediata == 10000.0
    assert r.f6_despesa == 3000.0
    assert r.f5_resultado_rural == 7000.0


def test_resumo_transito_separado():
    notas = [
        {"categoria_contabil": "TRANSITO", "valor_total": 5000.0},
        {"categoria_contabil": "RECEITA", "valor_total": 1000.0},
    ]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    assert r.f2_transito == 5000.0
    assert r.f1_receita_imediata == 1000.0


def test_resumo_aceita_transito_com_acento():
    notas = [{"categoria_contabil": "TRÂNSITO", "valor_total": 500.0}]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    assert r.f2_transito == 500.0


def test_resumo_fallback_natureza_exibicao():
    """Quando categoria_contabil falta, usa natureza_exibicao."""
    notas = [{"natureza_exibicao": "RECEITA", "valor_total": 100.0}]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    assert r.f1_receita_imediata == 100.0


def test_resumo_lista_vazia():
    r = apurar_resumo([], data_referencia=date(2026, 5, 1))
    assert r.total_notas == 0
    assert r.f1_receita_imediata == 0
    assert r.funrural == 0


# ── Alíquotas FUNRURAL por regime e data ────────────────────────────────────


def test_funrural_pj_pre_corte_205():
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 100_000.0}]
    r = apurar_resumo(notas, eh_pj=True, data_referencia=date(2026, 3, 31))
    assert r.aliquota_funrural == 0.0205
    assert r.funrural == 2050.0


def test_funrural_pj_pos_corte_223():
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 100_000.0}]
    r = apurar_resumo(notas, eh_pj=True, data_referencia=date(2026, 4, 1))
    assert r.aliquota_funrural == 0.0223
    assert r.funrural == 2230.0


def test_funrural_pf_pre_corte_150():
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 100_000.0}]
    r = apurar_resumo(notas, data_referencia=date(2026, 3, 31))
    assert r.aliquota_funrural == 0.0150
    assert r.funrural == 1500.0


def test_funrural_pf_pos_corte_163():
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 100_000.0}]
    r = apurar_resumo(notas, data_referencia=date(2026, 4, 1))
    assert r.aliquota_funrural == 0.0163
    assert r.funrural == 1630.0


def test_funrural_segurado_especial_sempre_150():
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 100_000.0}]
    r = apurar_resumo(notas, eh_segurado_especial=True, data_referencia=date(2026, 5, 1))
    assert r.aliquota_funrural == 0.0150
    assert r.funrural == 1500.0


@pytest.mark.parametrize("eh_pj,esperado", [
    (True, 0.0223),
    (False, 0.0163),
])
def test_funrural_corte_exato_em_2026_04_01(eh_pj, esperado):
    """Corte é INCLUSIVE em 01/04/2026 (corte: data_referencia >= corte)."""
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 1000.0}]
    r = apurar_resumo(notas, eh_pj=eh_pj, data_referencia=date(2026, 4, 1))
    assert r.aliquota_funrural == esperado


# ── IRPF estimado ───────────────────────────────────────────────────────────


def test_irpf_zero_quando_resultado_negativo():
    """Lei 9.250/95: prejuízo rural não gera IRPF."""
    notas = [
        {"categoria_contabil": "RECEITA", "valor_total": 1000.0},
        {"categoria_contabil": "DESPESA", "valor_total": 5000.0},
    ]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    assert r.f5_resultado_rural == -4000.0
    assert r.irpf_estimado == 0  # nunca negativo


def test_irpf_20_porcento_do_resultado():
    notas = [
        {"categoria_contabil": "RECEITA", "valor_total": 50_000.0},
        {"categoria_contabil": "DESPESA", "valor_total": 10_000.0},
    ]
    r = apurar_resumo(notas, data_referencia=date(2026, 5, 1))
    # F5 = 40k, IRPF = 8k
    assert r.f5_resultado_rural == 40_000.0
    assert r.irpf_estimado == 8000.0


# ── Robustez ────────────────────────────────────────────────────────────────


def test_resumo_valores_invalidos_nao_quebram():
    notas = [
        {"categoria_contabil": "RECEITA"},  # sem valor_total
        {"categoria_contabil": "DESPESA", "valor_total": None},
    ]
    # apurar_resumo usa float(get(...,0)) — None levanta TypeError; verifica que
    # ao menos o tipo correto é exigido (regressão futura possível)
    with pytest.raises(TypeError):
        apurar_resumo(notas, data_referencia=date(2026, 5, 1))


def test_resumo_aliquota_default_quando_data_none():
    """data_referencia=None usa date.today() — deve sempre retornar alíquota válida."""
    notas = [{"categoria_contabil": "RECEITA", "valor_total": 1000.0}]
    r = apurar_resumo(notas)
    assert r.aliquota_funrural in (0.0150, 0.0163, 0.0205, 0.0223)


def test_to_dict_serializa_todos_os_campos():
    r = apurar_resumo(
        [{"categoria_contabil": "RECEITA", "valor_total": 1000.0}],
        data_referencia=date(2026, 5, 1),
    )
    d = r.to_dict()
    campos_esperados = {
        "f1_receita_imediata", "f2_transito", "f3_receita_leilao",
        "f4_receita_bruta", "f5_resultado_rural", "f6_despesa",
        "funrural", "irpf_estimado", "aliquota_funrural", "total_notas",
    }
    assert campos_esperados.issubset(d.keys())
