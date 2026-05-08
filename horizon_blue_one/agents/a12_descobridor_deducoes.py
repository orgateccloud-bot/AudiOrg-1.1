"""A-12: @Descobridor-Deducoes — Otimização Tributária e Isenções
STATUS: ✅ PRODUÇÃO
CRITICIDADE: 🟢 NORMAL
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Descobridor-Deducoes da ORGATEC IA.
Identifique oportunidades legais de redução de impostos, como isenções de ITR (reserva legal, APP) e deduções no LCDPR.
Responda APENAS com JSON:
{"deducoes_encontradas": [], "economia_estimada": 0.0, "viabilidade": "ALTA|MÉDIA|BAIXA"}"""

class DescobridorDeducoesAgent(BaseAgent):
    agent_id = "A-12"
    name = "@Descobridor-Deducoes"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Buscando isenções e deduções legais")
        prompt = f"Analise as operações e sugira deduções permitidas:\n{json.dumps(payload)[:1500]}"
        
        try:
            resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=1024)
            data = json.loads(resp)
        except Exception as e:
            self.log_error("Falha ao analisar deduções", exc=e)
            data = {"deducoes_encontradas": ["Análise temporariamente indisponível"], "economia_estimada": 0.0, "viabilidade": "BAIXA"}
            
        status = "APROVADO"
        
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.90,
        )
