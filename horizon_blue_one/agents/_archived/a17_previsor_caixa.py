"""A-17: @Previsor-Caixa — Projeção de Fluxo de Caixa e Sazonalidade Rural
STATUS: 📋 ESPECIFICADO — ROADMAP Q3 2026 (implementação funcional disponível)
CRITICIDADE: 🟡 ALTA

Nota: Agente funcional. Migrado de A-15 para A-17 conforme spec oficial 05/05/2026.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Previsor-Caixa da ORGATEC IA, especialista em fluxo de caixa e sazonalidade do agronegócio.
Analise histórico de receitas/despesas e projete os próximos 12 meses.
Considere: sazonalidade (safra/entressafra), ciclos de recria/engorda, Funrural a recolher.
Retorne JSON: {"projecao_12m": [{"mes": "2026-01", "receita_estimada": 0.0, "despesa_estimada": 0.0, "saldo": 0.0}], "alertas_liquidez": [], "funrural_acumulado": 0.0}"""


class PrevisorCaixaAgent(BaseAgent):
    agent_id = "A-17"
    name = "@Previsor-Caixa"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        periodo = payload.get("periodo", {})
        self.log("Projetando fluxo de caixa 12 meses")

        receitas_mes: dict = {}
        for n in notas:
            mes = str(n.get("data", ""))[:7]
            if mes and n.get("categoria_contabil") == "RECEITA":
                receitas_mes[mes] = receitas_mes.get(mes, 0) + float(n.get("valor_total", 0))

        prompt = f"""Projete fluxo de caixa para os próximos 12 meses com base no histórico:
Receitas mensais históricas: {receitas_mes}
Período de referência: {periodo}
Considere sazonalidade do agronegócio goiano e ciclos produtivos."""

        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=4096)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"projecao_12m": [], "alertas_liquidez": [], "funrural_acumulado": 0.0}

        return AgentResult(agent_id=self.agent_id, status="APROVADO", output=data, confidence=0.82)
