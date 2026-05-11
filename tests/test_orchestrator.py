"""Testes do Orchestrator + EventBus.

Cobre: filtro pf-gate, heurística audit-limpa, score consolidado, registry de
agentes, e ciclo publish/subscribe do EventBus.
"""
import asyncio

import pytest

from horizon_blue_one.agents.base_agent import AgentResult
from horizon_blue_one.core.orchestrator import (
    _AGENT_MODULES,
    PIPELINE_DEFAULT,
    EventBus,
    EventoBus,
    Orchestrator,
    _instanciar,
    _score_consolidado,
)

# ── EventBus ─────────────────────────────────────────────────────────────────

class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscriber_recebe_evento_com_filtro_correto(self):
        bus = EventBus()
        recebidos: list[EventoBus] = []

        async def callback(ev):
            recebidos.append(ev)

        bus.subscribe("ESCALADO", callback)
        await bus.start()
        await bus.publish(EventoBus(tipo="ESCALADO", agent_id="S2"))
        await asyncio.sleep(0.05)
        await bus.stop()

        assert len(recebidos) == 1
        assert recebidos[0].agent_id == "S2"

    @pytest.mark.asyncio
    async def test_subscriber_wildcard_recebe_qualquer_tipo(self):
        bus = EventBus()
        recebidos = []

        async def callback(ev):
            recebidos.append(ev.tipo)

        bus.subscribe("*", callback)
        await bus.start()
        await bus.publish(EventoBus(tipo="APROVADO", agent_id="S1"))
        await bus.publish(EventoBus(tipo="ESCALADO", agent_id="S2"))
        await asyncio.sleep(0.05)
        await bus.stop()

        assert "APROVADO" in recebidos
        assert "ESCALADO" in recebidos

    @pytest.mark.asyncio
    async def test_filtro_descarta_eventos_de_outro_tipo(self):
        bus = EventBus()
        recebidos = []

        async def callback(ev):
            recebidos.append(ev)

        bus.subscribe("ESCALADO", callback)
        await bus.start()
        await bus.publish(EventoBus(tipo="APROVADO", agent_id="S1"))
        await asyncio.sleep(0.05)
        await bus.stop()

        assert recebidos == []

    @pytest.mark.asyncio
    async def test_excecao_em_subscriber_nao_quebra_bus(self):
        bus = EventBus()
        sucessos = []

        async def quebra(ev):
            raise RuntimeError("boom")

        async def ok(ev):
            sucessos.append(ev.tipo)

        bus.subscribe("*", quebra)
        bus.subscribe("*", ok)
        await bus.start()
        await bus.publish(EventoBus(tipo="APROVADO", agent_id="X"))
        await asyncio.sleep(0.05)
        await bus.stop()

        assert sucessos == ["APROVADO"]

    @pytest.mark.asyncio
    async def test_start_idempotente(self):
        bus = EventBus()
        await bus.start()
        task1 = bus._task
        await bus.start()
        assert bus._task is task1
        await bus.stop()


# ── _aplicar_gate ────────────────────────────────────────────────────────────

class TestAplicarGate:
    def test_pf_baixo_reduz_para_s3_s5_s7(self):
        agentes, motivo = Orchestrator._aplicar_gate(
            ["S1", "S2", "S3", "S4", "S5", "S6", "S7"], pf=0.20
        )
        assert set(agentes) == {"S3", "S5", "S7"}
        assert "reduzido" in motivo

    def test_pf_medio_remove_s4_e_s6(self):
        agentes, motivo = Orchestrator._aplicar_gate(
            ["S1", "S2", "S3", "S4", "S5", "S6", "S7"], pf=0.70
        )
        assert "S4" not in agentes
        assert "S6" not in agentes
        assert "S1" in agentes and "S2" in agentes
        assert "amplo" in motivo

    def test_pf_alto_mantem_lista_completa(self):
        original = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
        agentes, motivo = Orchestrator._aplicar_gate(original, pf=0.95)
        assert agentes == original
        assert "full" in motivo

    def test_alias_a00_aceito(self):
        agentes, _ = Orchestrator._aplicar_gate(["A-00"], pf=0.20)
        assert "A-00" in agentes


# ── _audit_limpa ─────────────────────────────────────────────────────────────

class TestAuditLimpa:
    def _pre_limpo(self):
        return {
            "detectores": {
                "carrossel": False, "smurfing": False,
                "fornecedor_fantasma": [], "devolucao_posterior": False,
                "anomalia_temporal": False,
            },
            "xgboost": {"score": 10},
            "cfop": {"total_divergencias": 0},
            "lcdpr": {"divergencia": 0.0},
        }

    def test_limpa_retorna_true(self):
        assert Orchestrator._audit_limpa(self._pre_limpo()) is True

    def test_score_alto_quebra_limpa(self):
        pre = self._pre_limpo()
        pre["xgboost"]["score"] = 70
        assert Orchestrator._audit_limpa(pre) is False

    def test_carrossel_detectado_quebra_limpa(self):
        pre = self._pre_limpo()
        pre["detectores"]["carrossel"] = True
        assert Orchestrator._audit_limpa(pre) is False

    def test_fornecedor_fantasma_quebra_limpa(self):
        pre = self._pre_limpo()
        pre["detectores"]["fornecedor_fantasma"] = ["CNPJ_FAKE"]
        assert Orchestrator._audit_limpa(pre) is False

    def test_lcdpr_divergente_quebra_limpa(self):
        pre = self._pre_limpo()
        pre["lcdpr"]["divergencia"] = 5000
        assert Orchestrator._audit_limpa(pre) is False

    def test_cfop_divergente_quebra_limpa(self):
        pre = self._pre_limpo()
        pre["cfop"]["total_divergencias"] = 3
        assert Orchestrator._audit_limpa(pre) is False

    def test_precalc_vazio_retorna_false(self):
        assert Orchestrator._audit_limpa({}) is False

    def test_anomalia_temporal_quebra_limpa(self):
        pre = self._pre_limpo()
        pre["detectores"]["anomalia_temporal"] = True
        assert Orchestrator._audit_limpa(pre) is False


# ── _score_consolidado ───────────────────────────────────────────────────────

class TestScoreConsolidado:
    def test_pega_max_entre_fontes(self):
        pre = {"xgboost": {"score": 40}}
        resultados = {
            "S2": AgentResult(agent_id="S2", status="APROVADO",
                              output={"score_risco": 75}, confidence=0.9),
        }
        assert _score_consolidado(resultados, pre) == 75.0

    def test_usa_score_do_precalc_se_unico(self):
        pre = {"xgboost": {"score": 50}}
        assert _score_consolidado({}, pre) == 50.0

    def test_fallback_para_score_risco_no_precalc(self):
        pre = {"xgboost": {"score_risco": 30}}
        assert _score_consolidado({}, pre) == 30.0

    def test_sem_dados_retorna_zero(self):
        assert _score_consolidado({}, None) == 0.0
        assert _score_consolidado({}, {}) == 0.0

    def test_ignora_score_invalido(self):
        pre = {"xgboost": {"score": "nao-numerico"}}
        resultados = {
            "S7": AgentResult(agent_id="S7", status="APROVADO",
                              output={"score_global": 20}, confidence=0.5),
        }
        assert _score_consolidado(resultados, pre) == 20.0

    def test_le_score_global_ou_score_alem_de_score_risco(self):
        resultados = {
            "S7": AgentResult(agent_id="S7", status="APROVADO",
                              output={"score": 33}, confidence=0.5),
        }
        assert _score_consolidado(resultados, None) == 33.0

    def test_output_nao_dict_ignorado(self):
        resultados = {
            "S2": AgentResult(agent_id="S2", status="APROVADO",
                              output="string-nao-dict", confidence=0.5),
        }
        assert _score_consolidado(resultados, None) == 0.0


# ── Registry ─────────────────────────────────────────────────────────────────

class TestInstanciar:
    def test_instancia_todos_os_s1_a_s7(self):
        for aid in ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]:
            ag = _instanciar(aid)
            assert ag is not None

    def test_alias_a00_aponta_para_s7(self):
        ceo_alias = _instanciar("A-00")
        ceo_direto = _instanciar("S7")
        assert type(ceo_alias) is type(ceo_direto)

    def test_agent_id_desconhecido_levanta(self):
        with pytest.raises(ValueError, match="desconhecido"):
            _instanciar("S99")

    def test_pipeline_default_tem_7_agentes(self):
        assert PIPELINE_DEFAULT == ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]

    def test_registry_contem_consolidados_e_legacy(self):
        assert "S1" in _AGENT_MODULES
        assert "A-00" in _AGENT_MODULES
        # Pelo menos um legacy preservado
        assert any(k.endswith("_LEGACY") for k in _AGENT_MODULES)


# ── Orchestrator (smoke) ─────────────────────────────────────────────────────

class TestOrchestratorSmoke:
    def test_instancia_com_subscribers_default(self):
        orch = Orchestrator()
        assert orch.bus is not None
        # 2 subscribers default: ESCALADO + wildcard
        assert len(orch.bus._subscribers) >= 2

    @pytest.mark.asyncio
    async def test_executar_pipeline_early_exit_payload_limpo(self):
        """Audit determinística limpa não chama LLM e retorna __EARLY_EXIT__."""
        orch = Orchestrator()
        payload = {
            "notas": [],
            "contribuinte": {"cpf": "123.456.789-09"},
            "__precalc__": {
                "detectores": {
                    "carrossel": False, "smurfing": False,
                    "fornecedor_fantasma": [], "devolucao_posterior": False,
                    "anomalia_temporal": False,
                },
                "xgboost": {"score": 5, "probabilidade_autuacao": 0.1},
                "cfop": {"total_divergencias": 0},
                "lcdpr": {"divergencia": 0.0},
            },
        }
        resultados = await orch.executar_pipeline(payload, agentes=["S1", "S2"])
        # Deve haver __EARLY_EXIT__ OU __PF_GATE__
        assert "__EARLY_EXIT__" in resultados or "__PF_GATE__" in resultados
