"""A-10: @Auditor-Patrimonio — Auditoria de Ativos e Patrimônio
STATUS: ✅ PRODUÇÃO
CRITICIDADE: 🟡 ALTA
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Auditor-Patrimonio da ORGATEC IA.
Sua função é avaliar o ativo imobilizado (máquinas, terras, implementos) de empresas agropecuárias.
Identifique superavaliações, alienações irregulares ou ausência de depreciação de maquinários.
Responda APENAS com JSON:
{"risco_patrimonial": "BAIXO|MÉDIO|ALTO", "divergencias_ativos": [], "recomendacoes": []}"""

class AuditorPatrimonioAgent(BaseAgent):
    agent_id = "A-10"
    name = "@Auditor-Patrimonio"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Avaliando ativo imobilizado e mutações patrimoniais")
        prompt = f"Analise as informações de patrimônio/bens:\n{json.dumps(payload)[:1500]}"
        
        try:
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=1024, agent_id=self.agent_id))[0]
            data = json.loads(resp)
        except Exception as e:
            self.log_error("Falha ao analisar patrimônio", exc=e)
            data = {"risco_patrimonial": "MÉDIO", "divergencias_ativos": ["Não foi possível validar ativos"], "recomendacoes": ["Levantamento in loco"]}
            
        status = "ESCALADO" if data.get("risco_patrimonial") == "ALTO" else "APROVADO"
        
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.88,
        )
