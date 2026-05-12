"""Testes do loader de alíquotas FUNRURAL (data/funrural_aliquotas.yaml)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from horizon_blue_one.orgaudi import aliquotas_loader
from horizon_blue_one.orgaudi.aliquotas_loader import (
    TabelaFUNRURAL,
    _FALLBACK,
    carregar_tabela,
    limpar_cache,
)


@pytest.fixture(autouse=True)
def _cache_limpo():
    limpar_cache()
    yield
    limpar_cache()


class TestCarregarTabela:
    def test_yaml_existe_e_carrega(self):
        tabela = carregar_tabela()
        assert tabela.versao == "2026.1"
        assert tabela.corte_vigencia == date(2026, 4, 1)

    def test_valores_pos_corte(self):
        tabela = carregar_tabela()
        assert tabela.aliquotas_pos_corte.pj == 0.0223
        assert tabela.aliquotas_pos_corte.pf == 0.0163
        assert tabela.aliquotas_pos_corte.segurado_especial == 0.0150

    def test_valores_pre_corte(self):
        tabela = carregar_tabela()
        assert tabela.aliquotas_pre_corte.pj == 0.0205
        assert tabela.aliquotas_pre_corte.pf == 0.0150
        assert tabela.aliquotas_pre_corte.segurado_especial == 0.0150

    def test_irpf_resultado_rural(self):
        tabela = carregar_tabela()
        assert tabela.irpf_resultado_rural == 0.20


class TestAliquota:
    @pytest.fixture
    def tabela(self):
        return carregar_tabela()

    def test_pf_pos_corte(self, tabela):
        assert tabela.aliquota(eh_pj=False, eh_segurado_especial=False, data_referencia=date(2026, 5, 1)) == 0.0163

    def test_pf_pre_corte(self, tabela):
        assert tabela.aliquota(eh_pj=False, eh_segurado_especial=False, data_referencia=date(2026, 3, 31)) == 0.0150

    def test_pj_pos_corte(self, tabela):
        assert tabela.aliquota(eh_pj=True, eh_segurado_especial=False, data_referencia=date(2026, 4, 1)) == 0.0223

    def test_pj_pre_corte(self, tabela):
        assert tabela.aliquota(eh_pj=True, eh_segurado_especial=False, data_referencia=date(2026, 1, 1)) == 0.0205

    def test_segurado_especial_pos_corte(self, tabela):
        assert tabela.aliquota(eh_pj=False, eh_segurado_especial=True, data_referencia=date(2026, 5, 1)) == 0.0150

    def test_segurado_especial_pre_corte(self, tabela):
        assert tabela.aliquota(eh_pj=False, eh_segurado_especial=True, data_referencia=date(2025, 6, 1)) == 0.0150

    def test_corte_inclui_o_dia(self, tabela):
        no_dia = tabela.aliquota(eh_pj=True, eh_segurado_especial=False, data_referencia=date(2026, 4, 1))
        anterior = tabela.aliquota(eh_pj=True, eh_segurado_especial=False, data_referencia=date(2026, 3, 31))
        assert no_dia == 0.0223
        assert anterior == 0.0205


class TestFallback:
    def test_fallback_quando_yaml_ausente(self, monkeypatch, tmp_path):
        monkeypatch.setattr(aliquotas_loader, "_path_yaml", lambda: tmp_path / "nao_existe.yaml")
        tabela = carregar_tabela()
        assert tabela.versao == _FALLBACK.versao
        assert tabela.aliquotas_pos_corte.pj == 0.0223

    def test_fallback_quando_yaml_invalido(self, monkeypatch, tmp_path):
        ruim = tmp_path / "ruim.yaml"
        ruim.write_text("versao: x\nfonte: y\n", encoding="utf-8")
        monkeypatch.setattr(aliquotas_loader, "_path_yaml", lambda: ruim)
        tabela = carregar_tabela()
        assert tabela.versao == _FALLBACK.versao

    def test_cache_lru(self):
        primeira = carregar_tabela()
        segunda = carregar_tabela()
        assert primeira is segunda


class TestValidacao:
    def test_aliquota_negativa_rejeitada(self):
        with pytest.raises(Exception):  # noqa: PT011 — Pydantic levanta ValidationError
            TabelaFUNRURAL(
                versao="x",
                fonte="y",
                corte_vigencia=date(2026, 1, 1),
                aliquotas_pre_corte={"pj": -0.01, "pf": 0.01, "segurado_especial": 0.01},
                aliquotas_pos_corte={"pj": 0.01, "pf": 0.01, "segurado_especial": 0.01},
                irpf_resultado_rural=0.2,
            )

    def test_aliquota_acima_de_1_rejeitada(self):
        with pytest.raises(Exception):  # noqa: PT011
            TabelaFUNRURAL(
                versao="x",
                fonte="y",
                corte_vigencia=date(2026, 1, 1),
                aliquotas_pre_corte={"pj": 1.5, "pf": 0.01, "segurado_especial": 0.01},
                aliquotas_pos_corte={"pj": 0.01, "pf": 0.01, "segurado_especial": 0.01},
                irpf_resultado_rural=0.2,
            )


class TestResumoFiscalIntegracao:
    """Confere que a refatoração mantém os mesmos números antes/depois do YAML."""

    def test_apurar_resumo_pf_pos_corte(self):
        from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo

        notas = [
            {"categoria_contabil": "RECEITA", "valor_total": 10000.0},
            {"categoria_contabil": "DESPESA", "valor_total": 3000.0},
        ]
        r = apurar_resumo(notas, eh_pj=False, data_referencia=date(2026, 6, 1))
        assert r.aliquota_funrural == 0.0163
        assert r.funrural == round(10000.0 * 0.0163, 2)
        assert r.f5_resultado_rural == 7000.0
        assert r.irpf_estimado == round(7000.0 * 0.20, 2)

    def test_apurar_resumo_pj_pre_corte(self):
        from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo

        notas = [{"categoria_contabil": "RECEITA", "valor_total": 50000.0}]
        r = apurar_resumo(notas, eh_pj=True, data_referencia=date(2026, 1, 15))
        assert r.aliquota_funrural == 0.0205
        assert r.funrural == round(50000.0 * 0.0205, 2)
