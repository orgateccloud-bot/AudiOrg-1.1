"""Testes do A-Token — agente roteador + call_otimizado + relatorio_custo."""
from unittest.mock import AsyncMock, patch

import pytest

from horizon_blue_one.agents.a_token import (
    TokenAgent,
    call_otimizado,
    relatorio_custo,
)
from horizon_blue_one.core.model_adapter import ModelType
from horizon_blue_one.core.token_router import TipoTarefa, reset_stats


@pytest.fixture(autouse=True)
def _zera_stats():
    reset_stats()
    yield
    reset_stats()


# ── TokenAgent (BaseAgent.process) ───────────────────────────────────────────

class TestTokenAgent:
    @pytest.mark.asyncio
    async def test_processa_payload_basico(self):
        agent = TokenAgent()
        r = await agent.process({"notas": [], "tipo_tarefa": "lgpd"})
        assert r.agent_id == "A-Token"
        assert r.status == "APROVADO"
        assert r.output["modelo_recomendado"] == "haiku"

    @pytest.mark.asyncio
    async def test_tipo_tarefa_invalido_fallback_auditoria(self):
        agent = TokenAgent()
        r = await agent.process({"notas": [], "tipo_tarefa": "INEXISTENTE"})
        # AUDITORIA default → Sonnet (mas com score=0 e tipos=0, downgrade p/ Haiku
        # se for AUDITORIA operacional)
        assert r.output["modelo_recomendado"] in {"haiku", "sonnet"}

    @pytest.mark.asyncio
    async def test_score_risco_como_dict_extrai_score(self):
        agent = TokenAgent()
        r = await agent.process({
            "notas": [], "tipo_tarefa": "forense",
            "score_risco": {"score": 90},
        })
        # FORENSE com score 90 → escala p/ OPUS
        assert r.output["modelo_recomendado"] == "opus"
        assert r.output["upgrade_aplicado"] is True

    @pytest.mark.asyncio
    async def test_agent_id_alvo_define_tipo_tarefa(self):
        agent = TokenAgent()
        r = await agent.process({
            "notas": [],
            "agent_id_alvo": "A-01",  # ROTEAMENTO → Haiku
        })
        assert r.output["modelo_recomendado"] == "haiku"


# ── call_otimizado ───────────────────────────────────────────────────────────

class TestCallOtimizado:
    @pytest.mark.asyncio
    async def test_call_otimizado_usa_haiku_para_lgpd(self):
        with patch(
            "horizon_blue_one.agents.a_token.call_model",
            new=AsyncMock(return_value="ok"),
        ) as mock_call:
            resp, dec = await call_otimizado(
                "pergunta", "system",
                tipo_tarefa=TipoTarefa.LGPD,
                agent_id="S1",
            )
        assert resp == "ok"
        assert dec.modelo == ModelType.HAIKU
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_call_otimizado_escala_opus_em_score_alto(self):
        with patch(
            "horizon_blue_one.agents.a_token.call_model",
            new=AsyncMock(return_value="resp"),
        ):
            _resp, dec = await call_otimizado(
                "p", "s",
                tipo_tarefa=TipoTarefa.FORENSE,
                score_risco=95,
            )
        assert dec.modelo == ModelType.OPUS
        assert dec.upgrade_aplicado

    @pytest.mark.asyncio
    async def test_max_tokens_default_via_agent_id(self):
        capturado = {}

        async def mock_call_model(model_type, prompt, system, max_tokens, **kw):
            capturado["max_tokens"] = max_tokens
            return "ok"

        with patch(
            "horizon_blue_one.agents.a_token.call_model",
            side_effect=mock_call_model,
        ):
            await call_otimizado("p", "s", agent_id="S2")  # S2 → 2048
        assert capturado["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_max_tokens_explicito_sobrescreve(self):
        capturado = {}

        async def mock_call_model(model_type, prompt, system, max_tokens, **kw):
            capturado["max_tokens"] = max_tokens
            return "ok"

        with patch(
            "horizon_blue_one.agents.a_token.call_model",
            side_effect=mock_call_model,
        ):
            await call_otimizado("p", "s", max_tokens=99, agent_id="S2")
        assert capturado["max_tokens"] == 99


# ── relatorio_custo ──────────────────────────────────────────────────────────

class TestRelatorioCusto:
    @pytest.mark.asyncio
    async def test_relatorio_estrutura(self):
        rel = await relatorio_custo()
        assert rel["agente"] == "A-Token @Token"
        assert "relatorio" in rel
        assert "projecao_mensal_usd" in rel["relatorio"]

    @pytest.mark.asyncio
    async def test_projecao_mensal_30x_custo(self):
        with patch(
            "horizon_blue_one.agents.a_token.call_model",
            new=AsyncMock(return_value="resp"),
        ):
            await call_otimizado("p", "s", tipo_tarefa=TipoTarefa.LGPD)
        rel = await relatorio_custo()
        custo = rel["relatorio"]["custo_total_usd"]
        proj = rel["relatorio"]["projecao_mensal_usd"]
        assert proj == round(custo * 30, 4)
