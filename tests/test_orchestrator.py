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


# ── Pipeline completo (não-early-exit) ───────────────────────────────────────

import importlib

from horizon_blue_one.agents.base_agent import BaseAgent
from horizon_blue_one.core import orchestrator as orch_mod


class _AgenteFake(BaseAgent):
    agent_id = "FAKE"
    name = "Fake"

    async def process(self, payload):
        return AgentResult(
            agent_id="FAKE",
            status="APROVADO",
            output={"motivo": "ok", "score": 50},
            confidence=0.8,
        )


class _AgenteFalha(BaseAgent):
    agent_id = "FALHA"
    name = "Falha"

    async def process(self, payload):
        raise RuntimeError("agente explodiu")


def _precalc_alto_risco():
    """Pré-cálculo que NÃO dispara early-exit nem pf-gate de arquivamento."""
    return {
        "detectores": {
            "carrossel": True, "smurfing": True,
            "fornecedor_fantasma": ["X"], "devolucao_posterior": True,
            "anomalia_temporal": True,
        },
        "xgboost": {"score": 90, "probabilidade_autuacao": 0.95},
        "cfop": {"total_divergencias": 10},
        "lcdpr": {"divergencia": 50_000},
        "notas_re1": [],
    }


class TestPipelineCompleto:
    @pytest.mark.asyncio
    async def test_pipeline_paralelo_executa_agentes_e_ceo(self, monkeypatch):
        # Força _instanciar a devolver um agente fake para qualquer aid
        monkeypatch.setattr(orch_mod, "_instanciar", lambda aid: _AgenteFake())
        orch = Orchestrator()
        payload = {
            "notas": [{"valor_total": 1000}],
            "contribuinte": {},
            "__precalc__": _precalc_alto_risco(),
        }
        resultados = await orch.executar_pipeline(
            payload, agentes=["S1", "S2", "S7"],
            paralelo=True, chamar_ceo_no_fim=True,
        )
        # S7 (CEO) é chamado ao final; S1+S2 rodam em paralelo
        assert "S7" in resultados
        assert resultados["S7"].status == "APROVADO"

    @pytest.mark.asyncio
    async def test_pipeline_sequencial(self, monkeypatch):
        monkeypatch.setattr(orch_mod, "_instanciar", lambda aid: _AgenteFake())
        orch = Orchestrator()
        payload = {
            "notas": [{"valor_total": 1000}],
            "contribuinte": {},
            "__precalc__": _precalc_alto_risco(),
        }
        resultados = await orch.executar_pipeline(
            payload, agentes=["S1", "S2", "S7"],
            paralelo=False, chamar_ceo_no_fim=False,
        )
        # Sem CEO no fim → só S1 e S2 + S7 já no pipeline
        assert "S1" in resultados or "S2" in resultados or "S7" in resultados

    @pytest.mark.asyncio
    async def test_agente_que_explode_e_capturado(self, monkeypatch):
        monkeypatch.setattr(orch_mod, "_instanciar",
                            lambda aid: _AgenteFalha() if aid == "S2" else _AgenteFake())
        orch = Orchestrator()
        payload = {
            "notas": [],
            "contribuinte": {},
            "__precalc__": _precalc_alto_risco(),
        }
        resultados = await orch.executar_pipeline(
            payload, agentes=["S1", "S2"],
            paralelo=True, chamar_ceo_no_fim=False,
        )
        # S1 deve estar; S2 falhou → omitido do dict
        assert "S1" in resultados
        assert "S2" not in resultados

    @pytest.mark.asyncio
    async def test_ceo_que_explode_nao_quebra_pipeline(self, monkeypatch):
        # CEO (S7) levanta exceção → orchestrator captura e segue
        def fake_instanciar(aid):
            if aid == "S7":
                return _AgenteFalha()
            return _AgenteFake()

        monkeypatch.setattr(orch_mod, "_instanciar", fake_instanciar)
        orch = Orchestrator()
        payload = {
            "notas": [],
            "contribuinte": {},
            "__precalc__": _precalc_alto_risco(),
        }
        resultados = await orch.executar_pipeline(
            payload, agentes=["S1", "S7"],
            paralelo=True, chamar_ceo_no_fim=True,
        )
        # S1 está; S7 falhou no caminho CEO → ausente
        assert "S1" in resultados

    @pytest.mark.asyncio
    async def test_pf_gate_arquiva_baixa_probabilidade(self):
        """pf < PF_GATE_ARQUIVA dispara arquivamento sem LLM."""
        orch = Orchestrator()
        payload = {
            "notas": [],
            "contribuinte": {},
            "__precalc__": {
                "detectores": {
                    "carrossel": False, "smurfing": False,
                    "fornecedor_fantasma": [], "devolucao_posterior": False,
                    "anomalia_temporal": False,
                },
                # Score alto bloqueia early-exit, mas pf baixíssimo dispara arquiva
                "xgboost": {"score": 50, "probabilidade_autuacao": 0.05},
                "cfop": {"total_divergencias": 5},
                "lcdpr": {"divergencia": 100},
            },
        }
        resultados = await orch.executar_pipeline(payload, agentes=["S1", "S2"])
        assert "__PF_GATE__" in resultados

    @pytest.mark.asyncio
    async def test_budget_exceeded_em_sequencial_corta_pipeline(self, monkeypatch):
        """Orçamento de tokens estourado interrompe o sequencial."""
        monkeypatch.setattr(orch_mod, "_instanciar", lambda aid: _AgenteFake())

        # Faz snapshot_stats devolver totais crescentes para simular consumo
        chamadas = {"n": 0}

        def fake_snapshot():
            chamadas["n"] += 1
            return {"total_tokens": chamadas["n"] * 100_000}

        monkeypatch.setattr(
            "horizon_blue_one.core.token_router.snapshot_stats",
            fake_snapshot,
        )
        orch = Orchestrator()
        payload = {
            "notas": [],
            "contribuinte": {},
            "__precalc__": _precalc_alto_risco(),
        }
        resultados = await orch.executar_pipeline(
            payload, agentes=["S1", "S2", "S3", "S4"],
            paralelo=False, chamar_ceo_no_fim=False,
            max_tokens_orcamento=1_000,  # vai estourar logo
        )
        # Pelo menos um agente roda; depois budget corta
        assert len(resultados) < 4


class TestInstanciarFalhaSubclass:
    def test_modulo_sem_subclass_baseagent_levanta_runtimeerror(self, tmp_path, monkeypatch):
        """Se o módulo do agente não tem subclass de BaseAgent, levanta RuntimeError."""
        # Cria módulo fake sem BaseAgent
        import sys
        import types
        mod_fake = types.ModuleType("horizon_blue_one.agents._fake_sem_baseagent")
        mod_fake.algo = 42
        sys.modules["horizon_blue_one.agents._fake_sem_baseagent"] = mod_fake

        monkeypatch.setitem(
            orch_mod._AGENT_MODULES, "S_FAKE", "_fake_sem_baseagent",
        )
        try:
            with pytest.raises(RuntimeError, match="BaseAgent subclass"):
                orch_mod._instanciar("S_FAKE")
        finally:
            sys.modules.pop("horizon_blue_one.agents._fake_sem_baseagent", None)


# ── Subscribers default do Orchestrator ──────────────────────────────────────

class TestSubscribersDefault:
    @pytest.mark.asyncio
    async def test_on_escalado_loga_no_ledger(self):
        """Publica ESCALADO no bus do orchestrator e verifica que não quebra."""
        orch = Orchestrator()
        await orch.bus.start()
        try:
            await orch.bus.publish(EventoBus(
                tipo="ESCALADO", agent_id="S2",
                payload={"requisicao_id": "req-1", "motivo": "score_alto"},
            ))
            await asyncio.sleep(0.05)
        finally:
            await orch.bus.stop()
        # Sem assert específica — apenas exercita o subscriber default _on_escalado

    @pytest.mark.asyncio
    async def test_on_qualquer_loga_telemetria(self):
        orch = Orchestrator()
        await orch.bus.start()
        try:
            await orch.bus.publish(EventoBus(tipo="APROVADO", agent_id="S1"))
            await asyncio.sleep(0.05)
        finally:
            await orch.bus.stop()
