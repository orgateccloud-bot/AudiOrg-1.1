"""Testes do F3 — precalc estendido CFOP/ICMS/ITR."""
from __future__ import annotations

import pytest

from horizon_blue_one.core.precalc import (
    _cfop_tipo,
    _cfop_validator,
    _classe_gu,
    _icms_por_cfop,
    _itr_capacidade,
    precalcular,
)

# ── CFOP tipo (classificação por 1º dígito) ──────────────────────────────────

class TestCfopTipo:
    def test_entrada_interna(self):
        assert _cfop_tipo("1102") == "entrada_interna"

    def test_entrada_interestadual(self):
        assert _cfop_tipo("2102") == "entrada_interestadual"

    def test_saida_interna(self):
        assert _cfop_tipo("5102") == "saida_interna"

    def test_saida_interestadual(self):
        assert _cfop_tipo("6102") == "saida_interestadual"

    def test_ausente_string_vazia(self):
        assert _cfop_tipo("") == "ausente"

    def test_outro_digito_inesperado(self):
        assert _cfop_tipo("7999") == "outro"
        assert _cfop_tipo("9999") == "outro"


# ── CFOP validator + breakdown ────────────────────────────────────────────────

class TestCfopValidatorBreakdown:
    def test_breakdown_por_tipo(self):
        notas = [
            {"cfop": "1102", "valor_total": 100, "numero": "1"},
            {"cfop": "5102", "valor_total": 200, "numero": "2"},
            {"cfop": "6102", "valor_total": 300, "numero": "3"},
            {"cfop": "",     "valor_total": 50,  "numero": "4"},
        ]
        out = _cfop_validator(notas)
        assert out["total"] == 4
        assert out["por_tipo"]["entrada_interna"]   == 1
        assert out["por_tipo"]["saida_interna"]     == 1
        assert out["por_tipo"]["saida_interestadual"] == 1
        assert out["por_tipo"]["ausente"]           == 1

    def test_valor_agregado_por_tipo(self):
        notas = [
            {"cfop": "5102", "valor_total": 100},
            {"cfop": "5102", "valor_total": 200},
            {"cfop": "6102", "valor_total": 500},
        ]
        out = _cfop_validator(notas)
        assert out["valor_por_tipo"]["saida_interna"]       == 300.0
        assert out["valor_por_tipo"]["saida_interestadual"] == 500.0

    def test_divergente_tem_tipo(self):
        notas = [{"cfop": "9999", "valor_total": 10, "numero": "X"}]
        out = _cfop_validator(notas)
        assert out["total_divergencias"] == 1
        assert out["divergentes"][0]["tipo"] == "outro"


# ── ICMS por CFOP ─────────────────────────────────────────────────────────────

class TestIcmsPorCfop:
    def test_agrega_por_tipo(self):
        notas = [
            {"cfop": "1102", "valor_total": 1000, "valor_icms": 0,   "numero": "1"},
            {"cfop": "5102", "valor_total": 2000, "valor_icms": 0,   "numero": "2"},
            {"cfop": "6102", "valor_total": 3000, "valor_icms": 360, "numero": "3"},  # 12% OK
        ]
        out = _icms_por_cfop(notas)
        assert out["por_tipo"]["saida_interestadual"]["aliquota_efetiva"] == 0.12
        assert out["por_tipo"]["saida_interestadual"]["icms_total"] == 360.0
        assert out["n_suspeitas"] == 0

    def test_aliquota_zero_em_interestadual_eh_suspeita(self):
        notas = [
            {"cfop": "6102", "valor_total": 1000, "valor_icms": 0, "numero": "Z"},
        ]
        out = _icms_por_cfop(notas)
        assert out["n_suspeitas"] == 1
        assert out["suspeitas"][0]["motivo"] == "fora_banda_interestadual"

    def test_aliquota_acima_banda_interestadual_suspeita(self):
        # 20% > banda max 18%
        notas = [{"cfop": "6102", "valor_total": 1000, "valor_icms": 200, "numero": "X"}]
        out = _icms_por_cfop(notas)
        assert out["n_suspeitas"] == 1

    def test_icms_em_intra_uf_eh_suspeito(self):
        # Rural intra-UF tende a isenção; ICMS > 0 sinaliza
        notas = [{"cfop": "5102", "valor_total": 1000, "valor_icms": 50, "numero": "Y"}]
        out = _icms_por_cfop(notas)
        assert out["n_suspeitas"] == 1
        assert out["suspeitas"][0]["motivo"] == "icms_em_intra_uf_rural"

    def test_lista_vazia(self):
        out = _icms_por_cfop([])
        assert out == {"por_tipo": {}, "suspeitas": [], "n_suspeitas": 0}

    def test_valor_zero_nao_quebra(self):
        notas = [{"cfop": "5102", "valor_total": 0, "valor_icms": 0, "numero": "0"}]
        out = _icms_por_cfop(notas)
        # Não calcula alíquota nem suspeita quando valor = 0
        assert out["n_suspeitas"] == 0
        assert out["por_tipo"]["saida_interna"]["aliquota_efetiva"] == 0.0


# ── ITR — classe GU ───────────────────────────────────────────────────────────

class TestClasseGu:
    @pytest.mark.parametrize("gu,esperado", [
        (90, "alta"),
        (80, "alta"),
        (79, "media"),
        (50, "media"),
        (49, "baixa"),
        (30, "baixa"),
        (29, "subutilizada"),
        (0,  "subutilizada"),
    ])
    def test_faixas(self, gu, esperado):
        assert _classe_gu(gu, area_total=100) == esperado

    def test_sem_imovel(self):
        assert _classe_gu(0, area_total=0) == "sem_imovel"


class TestItrCapacidade:
    def test_imovel_produtivo(self):
        out = _itr_capacidade({"area_total_ha": 100, "area_utilizada_ha": 85})
        assert out["classe_gu"] == "alta"
        assert out["risco_autuacao"] is False
        assert out["subutilizado"] is False

    def test_imovel_subutilizado_risco(self):
        out = _itr_capacidade({"area_total_ha": 1000, "area_utilizada_ha": 200})
        assert out["classe_gu"] == "subutilizada"
        assert out["risco_autuacao"] is True
        assert out["subutilizado"] is True

    def test_imovel_baixa_utilizacao_risco(self):
        # 35% → baixa → risco
        out = _itr_capacidade({"area_total_ha": 100, "area_utilizada_ha": 35})
        assert out["classe_gu"] == "baixa"
        assert out["risco_autuacao"] is True

    def test_sem_imovel_nao_risco(self):
        out = _itr_capacidade({})
        assert out["classe_gu"] == "sem_imovel"
        assert out["risco_autuacao"] is False


# ── Integração com precalcular() ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_precalcular_inclui_icms():
    """ICMS calculator deve aparecer no resultado do precalc."""
    payload = {
        "notas": [
            {"cfop": "6102", "valor_total": 1000, "valor_icms": 120, "numero": "N1"},
        ],
        "contribuinte": {},
        "lcdpr_data": {},
    }
    out = await precalcular(payload)
    assert "icms" in out["__precalc__"]
    assert "saida_interestadual" in out["__precalc__"]["icms"]["por_tipo"]


@pytest.mark.asyncio
async def test_precalcular_itr_inclui_classe_gu():
    payload = {
        "notas": [],
        "contribuinte": {"area_total_ha": 100, "area_utilizada_ha": 25},
        "lcdpr_data": {},
    }
    out = await precalcular(payload)
    assert out["__precalc__"]["itr"]["classe_gu"] == "subutilizada"
    assert out["__precalc__"]["itr"]["risco_autuacao"] is True
