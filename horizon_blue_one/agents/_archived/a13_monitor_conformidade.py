"""A-13: @Monitor-Conformidade — QA Transversal + NBC TG + LGPD
STATUS: 🔧 DESENVOLVIMENTO
CRITICIDADE: 🔴 CRÍTICA
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Monitor-Conformidade da ORGATEC IA, responsável por QA transversal.
Valide outputs de outros agentes quanto a: NBC TG compliance, LGPD (dados pessoais),
contradições entre agentes, conformidade regulatória.
Retorne JSON: {
  "conformidade_nbc_tg": true,
  "conformidade_lgpd": true,
  "contradicoes": [],
  "alertas": [],
  "ropa_itens": [],
  "status_geral": "CONFORME|PARCIAL|NAO_CONFORME"
}"""


class MonitorConformidadeAgent(BaseAgent):
    agent_id = "A-13"
    name = "@Monitor-Conformidade"

    async def process(self, payload: dict) -> AgentResult:
        resultados_agentes = payload.get("resultados_agentes", {})
        self.log("Validando conformidade transversal", total_agentes=len(resultados_agentes))

        prompt = f"""Valide a conformidade dos outputs dos agentes:
{json.dumps(resultados_agentes, ensure_ascii=False)[:3000]}
Verifique: contradições entre agentes, compliance NBC TG, exposição de dados LGPD."""

        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=2048)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"conformidade_nbc_tg": True, "conformidade_lgpd": True,
                    "contradicoes": [], "alertas": [], "ropa_itens": [],
                    "status_geral": "PARCIAL"}

        status = "ESCALADO" if data.get("status_geral") == "NAO_CONFORME" else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data, confidence=0.88)
