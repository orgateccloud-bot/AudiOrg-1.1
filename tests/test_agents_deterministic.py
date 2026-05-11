"""Testes dos agentes S1–S7 — caminhos determinísticos (sem chamada LLM).

Todos os agentes têm um caminho "verde" que retorna APROVADO sem LLM
quando os dados não apresentam anomalias. Esses testes cobrem esse caminho
e verificam a estrutura do AgentResult em cada agente.
"""
import pytest
from unittest.mock import AsyncMock, patch
from horizon_blue_one.agents.base_agent import AgentResult


# ── Payload sem anomalias (estado limpo) ──────────────────────────────────────

def _precalc_limpo():
    return {
        "notas_re1": [],
        "pii": {"total_pii": 0, "cpfs": [], "cnpjs": [], "contas": []},
        "documentos": {"total_pendencias": 0, "ie_valida": True, "pendencias": []},
        "detectores": {
            "carrossel": False, "smurfing": False,
            "fornecedor_fantasma": [], "devolucao_posterior": False, "anomalia_temporal": False,
        },
        "xgboost": {"score": 10.0, "score_risco": 10.0, "probabilidade_autuacao": 0.1,
                    "tipologias_criticas": 0, "shap": {}, "nivel": "BAIXO"},
        "lstm": {"modo": "heuristic", "score_medio": 0.1,
                 "produtores_anomalos": [], "detalhes": {}},
        "cfop": {"total": 0, "validos": 0, "divergentes": [], "total_divergencias": 0},
        "lcdpr": {"receita_notas": 0, "receita_lcdpr": 0,
                  "divergencia": 0.0, "status": "CONFORME"},
        "itr": {"area_total_ha": 100, "area_utilizada": 80,
                "gu_pct": 80.0, "status": "REGULAR"},
        "grafo": {"densidade": 0.1, "ciclos": 0, "hubs": []},
        "caixa": {"entradas": 10000, "saidas": 8000, "saldo": 2000},
    }


def _payload_limpo():
    return {
        "notas": [],
        "contribuinte": {"cpf": "123.456.789-09", "nome": "Produtor Teste"},
        "lcdpr_data": {},
        "__precalc__": _precalc_limpo(),
    }


def _payload_esocial():
    payload = _payload_limpo()
    payload["esocial"] = {
        "empregados": [],
        "divergencias_fgts": [],
        "divergencias_inss": [],
        "eventos_pendentes": 0,
    }
    return payload


# ── S1 @Sentinel ──────────────────────────────────────────────────────────────

class TestS1Sentinel:
    @pytest.mark.asyncio
    async def test_aprovado_sem_pii_sem_pendencias(self):
        from horizon_blue_one.agents.s1_sentinel import SentinelAgent
        agent = SentinelAgent()
        result = await agent.process(_payload_limpo())
        assert isinstance(result, AgentResult)
        assert result.agent_id == "S1"
        assert result.status == "APROVADO"
        assert result.output["lgpd_status"] == "CONFORME"
        assert result.output["documentos_status"] == "OK"
        assert result.output.get("fonte") == "deterministico"

    @pytest.mark.asyncio
    async def test_confidence_alta_no_caminho_deterministico(self):
        from horizon_blue_one.agents.s1_sentinel import SentinelAgent
        result = await SentinelAgent().process(_payload_limpo())
        assert result.confidence >= 0.90

    @pytest.mark.asyncio
    async def test_chama_llm_quando_ha_pii(self):
        from horizon_blue_one.agents.s1_sentinel import SentinelAgent
        payload = _payload_limpo()
        payload["__precalc__"]["pii"]["total_pii"] = 3
        payload["__precalc__"]["documentos"]["ie_valida"] = False

        resposta_mock = '{"lgpd_status":"ALERTA","documentos_status":"PENDENCIA","recomendacoes":["revisar IE"],"confianca":0.8}'
        with patch("horizon_blue_one.agents.s1_sentinel.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await SentinelAgent().process(payload)

        assert result.agent_id == "S1"
        assert result.output["lgpd_status"] in ("ALERTA", "CONFORME", "VIOLACAO")


# ── S2 @Forense ───────────────────────────────────────────────────────────────

class TestS2Forense:
    @pytest.mark.asyncio
    async def test_aprovado_sem_deteccoes_score_baixo(self):
        from horizon_blue_one.agents.s2_forense import ForenseAgent
        result = await ForenseAgent().process(_payload_limpo())
        assert result.status == "APROVADO"
        assert result.output["nivel"] == "BAIXO"
        assert result.output.get("fonte") == "deterministico"

    @pytest.mark.asyncio
    async def test_escalado_quando_score_alto(self):
        from horizon_blue_one.agents.s2_forense import ForenseAgent
        payload = _payload_limpo()
        payload["__precalc__"]["xgboost"]["score"] = 90.0
        payload["__precalc__"]["xgboost"]["tipologias_criticas"] = 3
        payload["__precalc__"]["detectores"]["carrossel"] = True

        resposta_mock = '{"score_risco":90,"nivel":"CRITICO","tipologias":["carrossel"],"narrativa":"fraude","evidencias":[],"acoes":[],"confianca":0.95}'
        with patch("horizon_blue_one.agents.s2_forense.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await ForenseAgent().process(payload)

        assert result.status == "ESCALADO"

    @pytest.mark.asyncio
    async def test_lstm_sem_anomalia_nao_eleva_score(self):
        from horizon_blue_one.agents.s2_forense import ForenseAgent
        payload = _payload_limpo()
        payload["__precalc__"]["lstm"]["score_medio"] = 0.2
        result = await ForenseAgent().process(payload)
        assert result.status == "APROVADO"


# ── S3 @Fiscal ────────────────────────────────────────────────────────────────

class TestS3Fiscal:
    @pytest.mark.asyncio
    async def test_retorna_agent_result(self):
        from horizon_blue_one.agents.s3_fiscal import FiscalAgent
        resposta_mock = '{"icms_status":"CONFORME","itr_status":"REGULAR","lcdpr_status":"CONFORME","cfop_status":"OK","alertas":[],"confianca":0.9}'
        with patch("horizon_blue_one.agents.s3_fiscal.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await FiscalAgent().process(_payload_limpo())
        assert isinstance(result, AgentResult)
        assert result.agent_id == "S3"

    @pytest.mark.asyncio
    async def test_fallback_quando_llm_falha(self):
        from horizon_blue_one.agents.s3_fiscal import FiscalAgent
        with patch("horizon_blue_one.agents.s3_fiscal.call_otimizado",
                   new=AsyncMock(side_effect=Exception("API timeout"))):
            result = await FiscalAgent().process(_payload_limpo())
        # Deve retornar resultado (fallback determinístico), não explodir
        assert isinstance(result, AgentResult)


# ── S4 @Contabil ──────────────────────────────────────────────────────────────

class TestS4Contabil:
    @pytest.mark.asyncio
    async def test_retorna_agent_result(self):
        from horizon_blue_one.agents.s4_contabil import ContabilAgent
        resposta_mock = '{"patrimonio_status":"REGULAR","biologicos_status":"CPC29_OK","caixa_status":"EQUILIBRADO","alertas":[],"confianca":0.85}'
        with patch("horizon_blue_one.agents.s4_contabil.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await ContabilAgent().process(_payload_limpo())
        assert isinstance(result, AgentResult)
        assert result.agent_id == "S4"


# ── S5 @AuditorNFA ────────────────────────────────────────────────────────────

class TestS5NFA:
    @pytest.mark.asyncio
    async def test_retorna_agent_result(self):
        from horizon_blue_one.agents.s5_nfa import NFAAgent
        resposta_mock = '{"parecer":"REGULAR","irregularidades":[],"confianca":0.88}'
        with patch("horizon_blue_one.agents.s5_nfa.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await NFAAgent().process(_payload_limpo())
        assert isinstance(result, AgentResult)
        assert result.agent_id == "S5"


# ── S6 @RH ────────────────────────────────────────────────────────────────────

class TestS6RH:
    @pytest.mark.asyncio
    async def test_retorna_agent_result(self):
        from horizon_blue_one.agents.s6_rh import RHAgent
        resposta_mock = '{"esocial_status":"CONFORME","fgts_status":"OK","inss_status":"OK","alertas":[],"confianca":0.87}'
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await RHAgent().process(_payload_esocial())
        assert isinstance(result, AgentResult)
        assert result.agent_id == "S6"


# ── S7 @CEO ───────────────────────────────────────────────────────────────────

class TestS7CEO:
    @pytest.mark.asyncio
    async def test_retorna_agent_result(self):
        from horizon_blue_one.agents.s7_ceo import CEOAgent
        payload = _payload_limpo()
        payload["resultados_agentes"] = {
            "S1": {"status": "APROVADO", "output": {}},
            "S2": {"status": "APROVADO", "output": {"score_risco": 10}},
            "S3": {"status": "APROVADO", "output": {}},
        }
        resposta_mock = '{"veredito":"APROVADO","score_consolidado":15,"parecer_juridico":"Sem irregularidades","mda":"Produtor regular","acoes_recomendadas":[],"confianca":0.92}'
        with patch("horizon_blue_one.agents.s7_ceo.call_otimizado",
                   new=AsyncMock(return_value=(resposta_mock, None))):
            result = await CEOAgent().process(payload)
        assert isinstance(result, AgentResult)
        assert result.agent_id == "S7"
        assert result.status in ("APROVADO", "REJEITADO", "ESCALADO", "ERRO")


# ── AgentResult — contrato base ───────────────────────────────────────────────

class TestAgentResult:
    def test_audit_hash_gerado(self):
        result = AgentResult(
            agent_id="TEST", status="APROVADO",
            output={"key": "value"}, confidence=0.9
        )
        assert len(result.audit_hash) == 64  # SHA-256 hex

    def test_timestamp_presente(self):
        result = AgentResult(agent_id="T", status="APROVADO", output={}, confidence=1.0)
        assert result.timestamp

    def test_status_validos(self):
        for status in ("APROVADO", "REJEITADO", "ESCALADO", "ERRO"):
            result = AgentResult(agent_id="T", status=status, output={}, confidence=0.5)
            assert result.status == status
