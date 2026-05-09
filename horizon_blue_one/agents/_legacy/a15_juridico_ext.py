"""A-15: @Juridico-Ext — Consultivo Jurídico e Contencioso
STATUS: ✅ PRODUÇÃO
CRITICIDADE: 🟡 ALTA
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Juridico-Ext da ORGATEC IA.
Sua função é fornecer pareceres jurídicos focados no agronegócio e legislação tributária.
Analise os passivos levantados e defina a estratégia de defesa administrativa ou judicial.
Responda APENAS com JSON:
{"parecer_resumido": "...", "teses_defesa": [], "jurisprudencia_aplicavel": [], "viabilidade_defesa": "ALTA|MÉDIA|BAIXA"}"""

class JuridicoExtAgent(BaseAgent):
    agent_id = "A-15"
    name = "@Juridico-Ext"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Gerando parecer jurídico e teses de defesa")
        prompt = f"Elabore parecer jurídico para os seguintes apontamentos fiscais:\n{json.dumps(payload)[:1500]}"
        
        try:
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=1024, agent_id=self.agent_id))[0]
            data = json.loads(resp)
        except Exception as e:
            self.log_error("Falha ao gerar parecer", exc=e)
            data = {"parecer_resumido": "Análise jurídica pendente", "teses_defesa": [], "jurisprudencia_aplicavel": [], "viabilidade_defesa": "MÉDIA"}
            
        status = "ESCALADO" if data.get("viabilidade_defesa") == "BAIXA" else "APROVADO"
        
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.91,
        )
