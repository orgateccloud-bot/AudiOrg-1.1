"""A-23 @Analista-Anomalias — Varredura completa AN-01..AN-18.

STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM)
v1.1: chamada ao LLM passa por @Delta via BaseAgent._call_llm().
"""
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.agents.detectores_forenses import (
    detectar_anomalia_temporal,
    detectar_carrossel,
    detectar_devolucao_posterior,
    detectar_fornecedor_fantasma,
    detectar_smurfing,
)
from horizon_blue_one.core.model_adapter import ModelType
from horizon_blue_one.ml.xgboost_scorer import calcular_score
from horizon_blue_one.orgaudi.anomalias import CATALOGO

SYSTEM = """Você é o @Analista-Anomalias da ORGATEC IA, especialista em tipologias fiscais AN-01..AN-18.
Retorne JSON: {"anomalias_detectadas": [{"codigo":"AN-01","confianca":0.0,"evidencias":[]}], "score_global": 0.0, "acoes_recomendadas": []}"""


class AnalistaAnomaliasAgent(BaseAgent):
    agent_id = "A-23"
    name = "@Analista-Anomalias"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Iniciando varredura AN-01..AN-18", total_notas=len(notas))

        # Reutiliza dados pré-computados se disponíveis (PipelineOrchestrator)
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

        resp = await self._call_llm(
            model_type=ModelType.CLAUDE,
            prompt_payload={
                "score_xgboost": score_info["score"],
                "shap_values": score_info["shap_values"],
                "detectores": det_pre,
                "catalogo": catalogo_resumido,
                "notas": notas[:50],
            },
            prompt_template=(
                "{payload}\n\nIdentifique tipologias prováveis e proponha "
                "cruzamentos documentais."
            ),
            system=SYSTEM,
            max_tokens=4096,
        )

        data, _ok = self.parse_json_response(
            resp,
            fallback={
                "anomalias_detectadas": [],
                "score_global": score_info["score"],
                "acoes_recomendadas": [],
            },
        )
        data["score_xgboost"] = score_info
        data["detectores_pre"] = det_pre

        status = "ESCALADO" if score_info["score"] > 65 else "APROVADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=min(1.0, score_info["score"] / 100),
        )
