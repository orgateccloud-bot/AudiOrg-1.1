"""A-23: @Analista-Anomalias — Varredura Completa AN-01..AN-18
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM)
Migrado de A-12 para A-23 conforme spec oficial 05/05/2026.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.core.privacy import anonymize_payload
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa
from horizon_blue_one.orgaudi.anomalias import CATALOGO, buscar_por_codigo, listar_criticos
from horizon_blue_one.ml.xgboost_scorer import calcular_score
from horizon_blue_one.agents.detectores_forenses import (
    detectar_carrossel,
    detectar_smurfing,
    detectar_fornecedor_fantasma,
    detectar_devolucao_posterior,
    detectar_anomalia_temporal,
)

SYSTEM = """Você é o @Analista-Anomalias da ORGATEC IA, especialista em tipologias fiscais AN-01..AN-18.
Retorne JSON: {"anomalias_detectadas": [{"codigo":"AN-01","confianca":0.0,"evidencias":[]}], "score_global": 0.0, "acoes_recomendadas": []}"""


class AnalistaAnomaliasAgent(BaseAgent):
    agent_id = "A-23"
    name = "@Analista-Anomalias"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Iniciando varredura AN-01..AN-18", total_notas=len(notas))

        # M-03: reutiliza dados pré-computados pelo PipelineOrchestrator se disponíveis
        det_pre = payload.get("detectores_pre") or {}
        score_info = payload.get("score_info") or calcular_score(notas)

        if not det_pre:
            det_pre = {
                "carrossel":           detectar_carrossel(notas),
                "smurfing":            detectar_smurfing(notas),
                "fornecedor_fantasma": detectar_fornecedor_fantasma(notas),
                "devolucao_posterior": detectar_devolucao_posterior(notas),
                "anomalia_temporal":   detectar_anomalia_temporal(notas),
            }
        self.log("Detectores determinísticos", **{k: v for k, v in det_pre.items() if v})
        catalogo_resumido = {k: {"nome": v.nome, "severidade": v.severidade} for k, v in CATALOGO.items()}

        # Protocolo @Delta — anonimiza det_pre antes de enviar ao Claude (LGPD)
        det_pre_anon = anonymize_payload(det_pre)

        prompt = f"""Score XGBoost: {score_info['score']} | SHAP: {score_info['shap_values']}
Detectores determinísticos (PII anonimizada): {det_pre_anon}
Catálogo AN-01..AN-18: {catalogo_resumido}
Identifique tipologias prováveis e proponha cruzamentos documentais."""

        # call_otimizado: A-Token decide Haiku/Sonnet/Opus pelo score (economia ~35%)
        resp, _decision = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            score_risco=float(score_info.get("score", 0)),
            num_notas=len(notas),
            agent_id=self.agent_id,
            max_tokens=4096,
        )
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"anomalias_detectadas": [], "score_global": score_info["score"], "acoes_recomendadas": []}
        data["score_xgboost"] = score_info
        data["detectores_pre"] = det_pre
        data["modelo_usado"] = _decision.modelo.value
        status = "ESCALADO" if score_info["score"] > 65 else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data,
                           confidence=min(1.0, score_info["score"] / 100))
