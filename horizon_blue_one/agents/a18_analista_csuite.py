"""A-18: @Analista-CSuite — MD&A + Relatórios Executivos C-Suite.

Hardening v1.1:
- Confidence DERIVADA do response (parse_json_response + derivar_confidence).
- Fallback determinístico inclui o resp truncado em resumo_executivo.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Analista-CSuite da ORGATEC IA, responsável por relatórios executivos para CTO, CFO e CEO.
Consolide resultados de todos os agentes em um resumo executivo acionável (MD&A).
Linguagem: objetiva, sem jargão técnico excessivo. Destaque: riscos, oportunidades, ações prioritárias.
Retorne JSON: {"resumo_executivo": "...", "kpis": {}, "riscos_prioritarios": [],
               "oportunidades": [], "proximos_passos": [], "confianca": 0.0}"""

CAMPOS_ESPERADOS = ("resumo_executivo", "kpis", "riscos_prioritarios",
                    "oportunidades", "proximos_passos")


class AnalistaCsuiteAgent(BaseAgent):
    agent_id = "A-18"
    name = "@Analista-CSuite"

    async def process(self, payload: dict) -> AgentResult:
        resultados_agentes = payload.get("resultados_agentes", {})
        contribuinte = payload.get("contribuinte", {})
        self.log("Gerando relatório executivo C-Suite", contribuinte=contribuinte.get("nome"))

        prompt = f"""Consolide os resultados da auditoria de {contribuinte.get('nome')} em relatório executivo (MD&A):
{json.dumps(resultados_agentes, ensure_ascii=False, indent=2)[:5000]}

Destaque: score de risco, principais anomalias, impacto financeiro estimado e ações urgentes."""

        try:
            resp = await call_model(ModelType.SONNET, prompt, SYSTEM, max_tokens=4096)
        except Exception as exc:
            self.log_error("Falha ao chamar modelo C-Suite", exc=exc)
            resp = ""

        fallback = {
            "resumo_executivo": resp[:1000] if resp else "Relatório indisponível.",
            "kpis": {}, "riscos_prioritarios": [],
            "oportunidades": [], "proximos_passos": [],
        }
        data, parseou_ok = self.parse_json_response(resp, fallback, CAMPOS_ESPERADOS)
        confidence = self.derivar_confidence(parseou_ok, data, CAMPOS_ESPERADOS, 0.95)

        return AgentResult(
            agent_id=self.agent_id, status="APROVADO",
            output=data, confidence=confidence,
        )
