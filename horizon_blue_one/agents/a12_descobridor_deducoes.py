"""A-12: @Descobridor-Deducoes — Otimização Tributária e Isenções
STATUS: ✅ PRODUÇÃO
CRITICIDADE: 🟢 NORMAL
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

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
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=1024, agent_id=self.agent_id))[0]
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
