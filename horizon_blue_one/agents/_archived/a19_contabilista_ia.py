"""A-19: @Contabilista-IA — Lançamentos Contábeis NBC TG + IFRS
STATUS: 🔧 DESENVOLVIMENTO
CRITICIDADE: 🔴 CRÍTICA

Nota: Agente funcional. Migrado de A-17 para A-19 conforme spec oficial 05/05/2026.
"""
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Contabilista-IA da ORGATEC IA, especialista em contabilidade rural e NBC TG.
Gere lançamentos contábeis completos para cada operação fiscal classificada.
Plano de contas ORGATEC: 1.1.2.01 Gado em Rebanho, 2.1.1.1.01 Fornecedores, 3.1.1 Receita Rural, 4.1.1 Custo Rural.
Aplique: CPC 29 (ativos biológicos), NBC TG 16 (estoques), NBC TG 26 (apresentação).
Retorne JSON: {"lancamentos": [{"debito": "conta", "credito": "conta", "valor": 0.0, "historico": "..."}], "total_debitos": 0.0, "total_creditos": 0.0}"""

_CAMPOS = ("lancamentos", "total_debitos", "total_creditos")
_FALLBACK = {"lancamentos": [], "total_debitos": 0.0, "total_creditos": 0.0}


class ContabilistaIAAgent(BaseAgent):
    agent_id = "A-19"
    name = "@Contabilista-IA"

    async def process(self, payload: dict) -> AgentResult:
        notas_classificadas = payload.get("notas_classificadas", [])
        self.log("Gerando lançamentos contábeis", total_notas=len(notas_classificadas))

        prompt = f"""Gere lançamentos contábeis para as notas classificadas:
{notas_classificadas[:20]}
Use plano de contas ORGATEC. Para notas com REGRA_ESPECIAL_1, debite 1.1.2.01 e credite 2.1.1.1.01."""

        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=4096)
        data, parseou_ok = self.parse_json_response(resp, _FALLBACK, _CAMPOS)
        confidence = self.derivar_confidence(parseou_ok, data, _CAMPOS)

        return AgentResult(agent_id=self.agent_id, status="APROVADO", output=data, confidence=confidence)
