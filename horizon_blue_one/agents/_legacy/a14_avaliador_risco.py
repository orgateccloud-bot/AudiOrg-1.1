"""A-14: @Avaliador-Risco — Scoring de Probabilidades e Malhas Fiscais
STATUS: ✅ PRODUÇÃO
CRITICIDADE: 🔴 CRÍTICA
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Avaliador-Risco da ORGATEC IA.
Calcule a probabilidade matemática do contribuinte cair em malha fiscal (ICMS, ITR, Receita Federal).
Utilize os dados históricos e padrões anômalos.
Responda APENAS com JSON:
{"score_risco_global": 0.0, "probabilidade_malha": 0.0, "vetores_risco": [], "classificacao": "BAIXO|MÉDIO|ALTO|CRÍTICO"}"""

class AvaliadorRiscoAgent(BaseAgent):
    agent_id = "A-14"
    name = "@Avaliador-Risco"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Calculando matriz de risco e probabilidade de malha")
        prompt = f"Calcule a probabilidade de autuação fiscal com base nos apontamentos:\n{json.dumps(payload)[:1500]}"
        
        try:
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=1024, agent_id=self.agent_id))[0]
            data = json.loads(resp)
        except Exception as e:
            self.log_error("Falha ao avaliar risco matemático", exc=e)
            data = {"score_risco_global": 50.0, "probabilidade_malha": 0.5, "vetores_risco": ["Indeterminado"], "classificacao": "MÉDIO"}
            
        status = "ESCALADO" if data.get("classificacao") in ["ALTO", "CRÍTICO"] else "APROVADO"
        
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.89,
        )
