"""A-26: @Auditor-Biologicos — Auditoria de Ativos Biológicos (NBC TG 29 / CPC 29)
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM — sem ID na spec oficial)
CRITICIDADE: 🟡 ALTA

Agente customizado ORGATEC para auditoria de ativos biológicos segundo CPC 29.
Migrado de A-09 para A-26. Pode ser incorporado ao A-08 @AuditorNFA-e no futuro.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1

SYSTEM = """Você é o @Auditor-Biologicos da ORGATEC IA, especialista em ativos biológicos conforme NBC TG 29 (CPC 29).
Avalie: mensuração a valor justo, transformação biológica, ganhos/perdas biológicas.
Retorne JSON: {"ativos_biologicos": [], "valor_justo_total": 0.0, "ganhos_biologicos": 0.0, "perdas_biologicas": 0.0, "alertas_cpc29": [], "classificacao_contabil": {}}"""


class AuditorBiologicosAgent(BaseAgent):
    agent_id = "A-26"
    name = "@Auditor-Biologicos"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        contribuinte = payload.get("contribuinte", {})
        self.log("Auditando ativos biológicos CPC-29", total_notas=len(notas))
        # Reutiliza classificação do A-08 se disponível, evita dupla aplicação da RE-1
        notas_classificadas = payload.get("notas_classificadas") or [aplicar_regra_especial_1(n) for n in notas]
        prompt = f"""Analise os ativos biológicos do contribuinte {contribuinte}:
{notas_classificadas}
Aplique NBC TG 29: calcule valor justo por cabeça, identifique ganhos por transformação biológica."""
        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"analise": resp}
        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output={"notas_classificadas": notas_classificadas, "analise": data},
            confidence=0.91,
        )
