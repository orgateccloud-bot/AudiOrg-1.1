"""Testes do catálogo AN-01..AN-18 e da apuração fiscal F1-F6/FUNRURAL/IRPF."""
from datetime import date

from horizon_blue_one.orgaudi.anomalias import (
    CATALOGO,
    TipologiaAnomalia,
    buscar_por_codigo,
    listar_criticos,
)
from horizon_blue_one.orgaudi.resumo_fiscal import ResumoFiscal, apurar_resumo

# ── Catálogo de Anomalias ────────────────────────────────────────────────────

class TestCatalogoAnomalias:
    def test_tem_18_tipologias(self):
        assert len(CATALOGO) == 18
        for i in range(1, 19):
            assert f"AN-{i:02d}" in CATALOGO

    def test_todas_sao_tipologia_anomalia(self):
        for v in CATALOGO.values():
            assert isinstance(v, TipologiaAnomalia)
            assert v.codigo
            assert v.severidade in {"CRÍTICO", "ALTO", "MÉDIO", "BAIXO"}
            assert isinstance(v.cruzamentos, list)

    def test_buscar_por_codigo_maiusculo(self):
        a = buscar_por_codigo("AN-01")
        assert a is not None
        assert a.nome == "Smurfing Rural"

    def test_buscar_por_codigo_minusculo_tambem_funciona(self):
        a = buscar_por_codigo("an-02")
        assert a is not None
        assert a.codigo == "AN-02"

    def test_buscar_codigo_inexistente_retorna_none(self):
        assert buscar_por_codigo("AN-99") is None

    def test_listar_criticos_retorna_apenas_criticos(self):
        criticos = listar_criticos()
        assert len(criticos) >= 3
        for c in criticos:
            assert c.severidade == "CRÍTICO"

    def test_smurfing_carrossel_nota_fria_funrural_e_caixa_dois_sao_criticos(self):
        # Garante que tipologias de alto risco fiscal estão marcadas como CRÍTICO
        codigos_criticos = {c.codigo for c in listar_criticos()}
        for esperado in ("AN-01", "AN-02", "AN-03", "AN-09", "AN-12"):
            assert esperado in codigos_criticos


# ── Apuração Fiscal (FUNRURAL + IRPF) ────────────────────────────────────────

class TestApurarResumo:
    def test_sem_notas_retorna_zerado(self):
        r = apurar_resumo([])
        assert r.f1_receita_imediata == 0
        assert r.funrural == 0
        assert r.irpf_estimado == 0
        assert r.total_notas == 0

    def test_pf_aliquota_pre_corte_1_50(self):
        r = apurar_resumo(
            [{"categoria_contabil": "RECEITA", "valor_total": 10_000}],
            eh_pj=False,
            data_referencia=date(2026, 1, 1),
        )
        assert r.aliquota_funrural == 0.0150
        assert r.funrural == 150.0  # 10_000 × 1,5%

    def test_pf_aliquota_pos_corte_1_63(self):
        r = apurar_resumo(
            [{"categoria_contabil": "RECEITA", "valor_total": 10_000}],
            eh_pj=False,
            data_referencia=date(2026, 6, 1),
        )
        assert r.aliquota_funrural == 0.0163
        assert r.funrural == 163.0

    def test_pj_aliquota_pre_corte_2_05(self):
        r = apurar_resumo(
            [{"categoria_contabil": "RECEITA", "valor_total": 100_000}],
            eh_pj=True,
            data_referencia=date(2026, 1, 1),
        )
        assert r.aliquota_funrural == 0.0205
        assert r.funrural == 2050.0

    def test_pj_aliquota_pos_corte_2_23(self):
        r = apurar_resumo(
            [{"categoria_contabil": "RECEITA", "valor_total": 100_000}],
            eh_pj=True,
            data_referencia=date(2026, 6, 1),
        )
        assert r.aliquota_funrural == 0.0223
        assert r.funrural == 2230.0

    def test_segurado_especial_aliquota_fixa_1_50(self):
        r = apurar_resumo(
            [{"categoria_contabil": "RECEITA", "valor_total": 1_000}],
            eh_segurado_especial=True,
            data_referencia=date(2026, 12, 1),  # pós-corte, mas segurado especial
        )
        assert r.aliquota_funrural == 0.0150
        assert r.funrural == 15.0

    def test_calculo_f4_e_f5_corretos(self):
        notas = [
            {"categoria_contabil": "RECEITA", "valor_total": 10_000},
            {"categoria_contabil": "DESPESA", "valor_total": 3_000},
        ]
        r = apurar_resumo(notas)
        assert r.f1_receita_imediata == 10_000
        assert r.f6_despesa == 3_000
        assert r.f4_receita_bruta == 10_000  # f3 = 0
        assert r.f5_resultado_rural == 7_000
        assert r.irpf_estimado == 1400.0  # 7000 × 20%

    def test_transito_alimenta_f2(self):
        notas = [
            {"categoria_contabil": "TRANSITO", "valor_total": 500},
            {"categoria_contabil": "TRÂNSITO", "valor_total": 200},
        ]
        r = apurar_resumo(notas)
        assert r.f2_transito == 700

    def test_irpf_minimo_zero(self):
        # Resultado rural negativo → IRPF não pode ser negativo
        notas = [
            {"categoria_contabil": "RECEITA", "valor_total": 1_000},
            {"categoria_contabil": "DESPESA", "valor_total": 5_000},
        ]
        r = apurar_resumo(notas)
        assert r.f5_resultado_rural == -4_000
        assert r.irpf_estimado == 0

    def test_data_referencia_default_hoje(self):
        # Não deve quebrar quando data_referencia=None
        r = apurar_resumo([{"categoria_contabil": "RECEITA", "valor_total": 100}])
        assert r.total_notas == 1
        assert r.f1_receita_imediata == 100

    def test_categoria_via_natureza_exibicao_fallback(self):
        # Quando 'categoria_contabil' não está presente, usa 'natureza_exibicao'
        notas = [{"natureza_exibicao": "RECEITA", "valor_total": 500}]
        r = apurar_resumo(notas)
        assert r.f1_receita_imediata == 500

    def test_to_dict_serializa_dataclass(self):
        r = ResumoFiscal(f1_receita_imediata=100)
        d = r.to_dict()
        assert d["f1_receita_imediata"] == 100
        assert "funrural" in d
        assert "aliquota_funrural" in d
