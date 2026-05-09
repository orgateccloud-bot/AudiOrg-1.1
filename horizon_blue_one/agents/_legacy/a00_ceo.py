"""A-00 @CEO — Governança, Anti-Alucinação, Decisão Final.

Hardening v1.1:
- Score de risco e valor da operação são VALIDADOS antes de seleção do modelo.
  Cliente que injetar score_risco=0.99 no payload não força mais Opus:
  exigimos `score_origem == "xgboost_scorer"` para considerar o valor.
- Caso falte essa marcação, default Sonnet (custo controlado).
"""
import json

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType, call_model

SYSTEM = """Você é o agente @CEO da plataforma ORGATEC IA.
Sua função é EXCLUSIVAMENTE governança: aprovar, rejeitar ou escalar outputs de outros agentes.
Critérios de escalação obrigatória:
- Score de risco > 0.85
- Fraude detectada com confiança > 0.80
- Valor da operação > R$ 1.000.000
- Contradição entre agentes detectada
- Confiança do output < 0.50
Responda APENAS com JSON: {"decisao":"APROVADO|REJEITADO|ESCALAR","motivo":"...","confianca":0.0}"""

# Origem confiável de score: somente o módulo interno xgboost_scorer pode
# carimbar o payload com este valor. Qualquer outro fica desconsiderado para
# fins de upgrade de modelo.
ORIGEM_SCORE_CONFIAVEL = {"xgboost_scorer", "a07_assurance", "internal"}


def _selecionar_modelo(payload: dict) -> ModelType:
    """Decide entre Opus e Sonnet com base em sinais CONFIÁVEIS.

    Apenas score que veio do XGBoost (carimbado por `score_origem`) é
    considerado. Valor da operação é aceito porque vem do schema validado.
    """
    score = float(payload.get("score_risco", 0) or 0)
    origem = str(payload.get("score_origem", "")).lower()

    score_confiavel = score if origem in ORIGEM_SCORE_CONFIAVEL else 0.0

    valor = float(payload.get("valor_total", 0) or 0)

    if score_confiavel > 0.85 or valor > 1_000_000:
        return ModelType.OPUS
    return ModelType.SONNET


class CEOAgent(BaseAgent):
    agent_id = "A-00"
    name = "@CEO"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Iniciando avaliação de governança", payload_keys=list(payload.keys()))

        model_to_use = _selecionar_modelo(payload)
        self.log(f"Selecionando modelo para decisão final: {model_to_use}")

        prompt = f"Avalie o output do agente:\n{payload}"
        resp = await call_model(model_to_use, prompt, SYSTEM, max_tokens=512)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            self.log_error("Resposta não é JSON válido", exc=None, raw=resp[:200])
            data = {
                "decisao": "ESCALADO",
                "motivo": "Falha ao parsear resposta do modelo",
                "confianca": 0.0,
            }
        # Confiança de fallback agora é 0.0 (anteriormente 0.9 enganoso).
        return AgentResult(
            agent_id=self.agent_id,
            status=data.get("decisao", "ESCALADO"),
            output=data,
            confidence=float(data.get("confianca", 0.0)),
        )
