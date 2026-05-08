"""A-23: @Analista-Anomalias — Varredura Completa AN-01..AN-18
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM)
Migrado de A-12 para A-23 conforme spec oficial 05/05/2026.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
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
        prompt = f"""Score XGBoost: {score_info['score']} | SHAP: {score_info['shap_values']}
Detectores determinísticos: {det_pre}
Catálogo AN-01..AN-18: {catalogo_resumido}
Identifique tipologias prováveis e proponha cruzamentos documentais."""
        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=4096)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"anomalias_detectadas": [], "score_global": score_info["score"], "acoes_recomendadas": []}
        data["score_xgboost"] = score_info
        data["detectores_pre"] = det_pre
        status = "ESCALADO" if score_info["score"] > 65 else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data,
                           confidence=min(1.0, score_info["score"] / 100))
