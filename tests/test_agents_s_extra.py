"""Testes que cobrem o caminho LLM dos agentes S2-S6 via mock de call_otimizado.

Cada agente tem dois caminhos:
  1) Determinístico (skip-LLM) — já coberto em outros testes
  2) Chamada LLM — coberto aqui via patch de `call_otimizado`
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from horizon_blue_one.agents.s2_forense import ForenseAgent
from horizon_blue_one.agents.s3_fiscal import FiscalAgent
from horizon_blue_one.agents.s4_contabil import ContabilAgent
from horizon_blue_one.agents.s5_nfa import NFAAgent
from horizon_blue_one.agents.s6_rh import RHAgent


def _payload_com_pre(pre: dict, **extras) -> dict:
    return {"__precalc__": pre, **extras}


# ── S2 @Forense ──────────────────────────────────────────────────────────────

class TestS2Forense:
    @pytest.mark.asyncio
    async def test_caminho_llm_sem_mcp_score_alto(self):
        pre = {
            "detectores": {
                "carrossel": True, "smurfing": False,
                "fornecedor_fantasma": [], "devolucao_posterior": False,
                "anomalia_temporal": False,
            },
            "xgboost": {
                "score": 80, "tipologias_criticas": 2,
                "probabilidade_autuacao": 0.85,
            },
            "lstm": {"score_medio": 0.0, "produtores_anomalos": []},
            "grafo": {"densidade": 0.1, "ciclos": 0, "hubs": []},
        }
        resp = json.dumps({
            "score_risco": 80, "nivel": "ALTO", "tipologias": ["carrossel"],
            "narrativa": "n", "evidencias": [], "acoes": [],
        })
        with patch("horizon_blue_one.agents.s2_forense.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await ForenseAgent().process(_payload_com_pre(pre))
        assert r.status in ("APROVADO", "ESCALADO")
        assert r.output["score_risco"] >= 80

    @pytest.mark.asyncio
    async def test_caminho_lstm_eleva_score_e_usa_mcp(self):
        pre = {
            "detectores": {
                "carrossel": False, "smurfing": False,
                "fornecedor_fantasma": [], "devolucao_posterior": False,
                "anomalia_temporal": False,
            },
            "xgboost": {"score": 30, "tipologias_criticas": 0, "probabilidade_autuacao": 0.3},
            # LSTM dispara MCP: score_medio alto + anomalos não-vazio
            "lstm": {"score_medio": 0.95, "produtores_anomalos": ["111", "222"]},
            "grafo": {"densidade": 0.0, "ciclos": 0, "hubs": []},
        }
        resp = json.dumps({
            "score_risco": 65, "nivel": "ALTO", "tipologias": ["lstm"],
            "narrativa": "x", "evidencias": [], "acoes": [],
        })
        with patch(
            "horizon_blue_one.agents.s2_forense.call_model_with_tools",
            new_callable=AsyncMock, return_value=(resp, {"tool_calls": 1}),
        ):
            r = await ForenseAgent().process(_payload_com_pre(pre))
        # Score elevado pelo bônus LSTM
        assert r.output["score_risco"] >= 30


# ── S3 @Fiscal ───────────────────────────────────────────────────────────────

class TestS3Fiscal:
    @pytest.mark.asyncio
    async def test_caminho_llm_quando_cfop_divergente(self):
        pre = {
            "cfop": {
                "total": 10, "total_divergencias": 3,
                "divergentes": [{"numero": "n1", "cfop": "9999"}],
                "validos": 7,
            },
            "lcdpr": {
                "divergencia": 5_000, "receita_notas": 100, "receita_lcdpr": 95,
                "status_conformidade": "DIVERGENTE",
            },
            "itr": {"area_total_ha": 100, "gu_pct": 50, "subutilizado": True},
            "caixa": {"entradas": 1000, "saidas": 500, "saldo": 500},
        }
        resp = json.dumps({
            "icms_status": "DIVERGENTE", "itr_status": "SUBUTILIZADO",
            "lcdpr_status": "DIVERGENTE", "cfop_status": "DIVERGENTE",
            "deducoes_legais": [], "alertas": [], "total_divergencia": 5000.0,
        })
        with patch("horizon_blue_one.agents.s3_fiscal.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await FiscalAgent().process(_payload_com_pre(pre))
        assert r.output["cfop_status"] == "DIVERGENTE"

    @pytest.mark.asyncio
    async def test_critico_lcdpr_marca_escalado(self):
        pre = {
            "cfop": {"total": 1, "total_divergencias": 0, "divergentes": [], "validos": 1},
            "lcdpr": {
                "divergencia": 1_000_000, "receita_notas": 0, "receita_lcdpr": 0,
                "status_conformidade": "CRITICO",
            },
            "itr": {"area_total_ha": 100, "gu_pct": 90, "subutilizado": False},
            "caixa": {"entradas": 0, "saidas": 0, "saldo": 0},
        }
        resp = json.dumps({
            "icms_status": "OK", "itr_status": "OK",
            "lcdpr_status": "CRITICO", "cfop_status": "OK",
            "deducoes_legais": [], "alertas": [], "total_divergencia": 1_000_000.0,
        })
        with patch("horizon_blue_one.agents.s3_fiscal.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await FiscalAgent().process(_payload_com_pre(pre))
        assert r.status == "ESCALADO"


# ── S4 @Contabil ─────────────────────────────────────────────────────────────

class TestS4Contabil:
    @pytest.mark.asyncio
    async def test_caminho_llm_com_biologicos(self):
        pre = {
            "notas_re1": [
                {"numero": "1", "natureza": "VENDA", "valor_total": 5000,
                 "categoria_contabil": "BIOLOGICO", "descricao": "ANIMAL bovino"},
            ],
            "caixa": {"entradas": 5000, "saidas": 0, "saldo": 5000},
        }
        resp = json.dumps({
            "ativos_biologicos": ["1"], "valor_justo_total": 5000.0,
            "ganhos_biologicos": 100.0, "previsao_caixa_30d": 5000.0,
            "lancamentos_sugeridos": [], "alertas_cpc29": [],
        })
        with patch("horizon_blue_one.agents.s4_contabil.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await ContabilAgent().process(_payload_com_pre(
                pre, contribuinte={"razao_social": "Fazenda X"}
            ))
        assert r.status == "APROVADO"
        assert r.output["valor_justo_total"] == 5000.0

    @pytest.mark.asyncio
    async def test_caminho_llm_quando_caixa_negativa(self):
        # Sem biológicos mas saldo negativo → entra no caminho LLM
        pre = {
            "notas_re1": [{"numero": "1", "valor_total": 100,
                           "categoria_contabil": "DESPESA"}],
            "caixa": {"entradas": 100, "saidas": 500, "saldo": -400},
        }
        resp = json.dumps({
            "ativos_biologicos": [], "valor_justo_total": 0.0,
            "ganhos_biologicos": 0.0, "previsao_caixa_30d": -400.0,
            "lancamentos_sugeridos": [], "alertas_cpc29": ["caixa negativo"],
        })
        with patch("horizon_blue_one.agents.s4_contabil.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await ContabilAgent().process(_payload_com_pre(pre))
        assert r.output["previsao_caixa_30d"] == -400.0


# ── S5 @AuditorNFA ───────────────────────────────────────────────────────────

class TestS5NFA:
    @pytest.mark.asyncio
    async def test_caminho_llm_com_divergencias(self):
        pre = {
            "notas_re1": [{"numero": "1", "valor_total": 1000, "natureza": "VENDA"}],
            "cfop": {
                "total": 1, "total_divergencias": 1,
                "divergentes": [{"numero": "1", "cfop": "9999"}],
                "validos": 0,
            },
            "detectores": {
                "carrossel": False, "smurfing": False,
                "fornecedor_fantasma": [], "devolucao_posterior": False,
                "anomalia_temporal": False,
            },
            "xgboost": {"score": 50, "tipologias_criticas": 1, "probabilidade_autuacao": 0.5},
        }
        resp = json.dumps({
            "total_notas": 1, "total_valor": 1000.0,
            "divergencias": [{"numero": "1", "cfop": "9999"}],
            "riscos": [], "conformidade_sefaz_go": "DIVERGENTE",
        })
        with patch("horizon_blue_one.agents.s5_nfa.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await NFAAgent().process(_payload_com_pre(pre))
        assert r.output["conformidade_sefaz_go"] == "DIVERGENTE"

    @pytest.mark.asyncio
    async def test_critico_quando_conformidade_critica(self):
        pre = {
            "notas_re1": [{"numero": "1", "valor_total": 100}],
            "cfop": {"total": 1, "total_divergencias": 100, "divergentes": [], "validos": 0},
            "detectores": {
                "carrossel": True, "smurfing": False,
                "fornecedor_fantasma": [], "devolucao_posterior": False,
                "anomalia_temporal": False,
            },
            "xgboost": {"score": 90, "tipologias_criticas": 1, "probabilidade_autuacao": 0.95},
        }
        resp = json.dumps({
            "total_notas": 1, "total_valor": 100.0, "divergencias": [],
            "riscos": ["carrossel"], "conformidade_sefaz_go": "CRITICO",
        })
        with patch("horizon_blue_one.agents.s5_nfa.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await NFAAgent().process(_payload_com_pre(pre))
        assert r.status == "ESCALADO"


# ── S6 @RH ───────────────────────────────────────────────────────────────────

class TestS6RH:
    @pytest.mark.asyncio
    async def test_sem_esocial_retorna_aprovado_deterministico(self):
        # esocial_data ausente → caminho determinístico
        r = await RHAgent().process({})
        assert r.status == "APROVADO"
        assert r.output["fonte"] == "deterministico"
        assert r.output["alertas"] == ["Sem dados eSocial no payload"]

    @pytest.mark.asyncio
    async def test_caminho_llm_quando_esocial_presente(self):
        resp = json.dumps({
            "eventos_pendentes": ["S-1000"], "divergencias_inss": 100.0,
            "fgts_a_recolher": 50.0, "alertas": [], "conformidade": "DIVERGENTE",
        })
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await RHAgent().process({
                "esocial_data": {"trabalhadores": 5},
                "contribuinte": {"razao_social": "X"},
            })
        assert r.output["divergencias_inss"] == 100.0
        assert r.status == "APROVADO"

    @pytest.mark.asyncio
    async def test_critico_marca_escalado(self):
        resp = json.dumps({
            "eventos_pendentes": [], "divergencias_inss": 999.0,
            "fgts_a_recolher": 0.0, "alertas": [], "conformidade": "CRITICO",
        })
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await RHAgent().process({
                "esocial_data": {"x": 1},
                "contribuinte": {},
            })
        assert r.status == "ESCALADO"

    @pytest.mark.asyncio
    async def test_coerce_num_aceita_string_invalida(self):
        # response com valores inválidos vira 0.0
        resp = json.dumps({
            "eventos_pendentes": [], "divergencias_inss": "nao-numerico",
            "fgts_a_recolher": None, "alertas": [], "conformidade": "CONFORME",
        })
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})):
            r = await RHAgent().process({
                "esocial_data": {"x": 1}, "contribuinte": {},
            })
        assert r.output["divergencias_inss"] == 0.0
        assert r.output["fgts_a_recolher"] == 0.0
