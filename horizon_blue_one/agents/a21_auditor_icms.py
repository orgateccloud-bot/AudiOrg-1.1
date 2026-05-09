"""A-21: @Auditor-ICMS — Auditoria de ICMS Rural, CFOP e SPED EFD
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM — sem ID na spec oficial)
CRITICIDADE: 🔴 CRÍTICA

Agente customizado ORGATEC — auditoria de ICMS específica para agronegócio goiano.
Migrado de A-10 para A-21 para alinhar à spec oficial 05/05/2026.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Auditor-ICMS da ORGATEC IA, especialista em ICMS do agronegócio goiano e nacional.
Verifique: CFOP adequado à operação, base de cálculo ICMS, créditos e débitos, diferencial de alíquota (DIFAL).
Aplique convênios ICMS relevantes (Confaz) e legislação estadual GO.
Retorne JSON: {"debitos_icms": 0.0, "creditos_icms": 0.0, "saldo_icms": 0.0, "cfop_divergentes": [], "alertas": [], "risco_autuacao": "BAIXO|MÉDIO|ALTO"}"""

CFOP_RURAL_VALIDOS = {
    "1101", "2101", "3101",  "1102", "2102", "3102",
    "1111", "2111", "5101",  "6101", "7101", "5102",
    "6102", "1201", "2201",  "5201", "6201", "5905",
    "6905", "1906", "2906",
}


class AuditorICMSAgent(BaseAgent):
    agent_id = "A-21"
    name = "@Auditor-ICMS"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Auditando ICMS e CFOPs", total_notas=len(notas))
        cfop_divergentes = [
            {"numero": n.get("numero"), "cfop": n.get("cfop")}
            for n in notas
            if str(n.get("cfop", "")).strip() not in CFOP_RURAL_VALIDOS
        ]
        prompt = f"""Audite ICMS das {len(notas)} notas fiscais rurais.
CFOPs com possível divergência: {cfop_divergentes[:20]}
Calcule débitos, créditos e saldo ICMS. Verifique convênios CONFAZ aplicáveis.
Identifique operações com DIFAL e diferimento ICMS agropecuário."""
        resp = (await call_otimizado(prompt, SYSTEM, max_tokens=2048, agent_id=self.agent_id))[0]
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"debitos_icms": 0.0, "creditos_icms": 0.0, "saldo_icms": 0.0,
                    "cfop_divergentes": cfop_divergentes, "alertas": [], "risco_autuacao": "MÉDIO"}
        status = "ESCALADO" if data.get("risco_autuacao") == "ALTO" else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data, confidence=0.87)
