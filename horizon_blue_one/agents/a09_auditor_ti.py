"""A-09: @Auditor-TI — Auditoria de Controles Internos em TI.

Hardening v1.1:
- Confidence DERIVADA do response (parse_json_response + derivar_confidence)
  em vez de hardcoded 0.85.
- Schema de saída esperado declarado em CAMPOS_ESPERADOS.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Auditor-TI da ORGATEC IA.
Sua função é avaliar controles internos de TI, segurança da informação e rastreabilidade sistêmica.
Identifique acessos indevidos, manipulação de logs e falhas em integrações ERP.
Responda APENAS com JSON:
{"risco_ti": "BAIXO|MÉDIO|ALTO", "vulnerabilidades": [], "recomendacoes": [], "confianca": 0.0}"""

CAMPOS_ESPERADOS = ("risco_ti", "vulnerabilidades", "recomendacoes")
FALLBACK = {
    "risco_ti": "MÉDIO",
    "vulnerabilidades": ["Análise sistêmica incompleta"],
    "recomendacoes": ["Verificação manual de logs"],
}


class AuditorTIAgent(BaseAgent):
    agent_id = "A-09"
    name = "@Auditor-TI"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Analisando controles internos de TI", payload_keys=list(payload.keys()))
        prompt = f"Avalie a integridade sistêmica e controles de TI dos dados:\n{json.dumps(payload)[:1500]}"

        try:
            resp = await call_model(ModelType.SONNET, prompt, SYSTEM, max_tokens=1024)
        except Exception as exc:
            self.log_error("Falha ao chamar modelo", exc=exc)
            resp = ""

        data, parseou_ok = self.parse_json_response(resp, FALLBACK, CAMPOS_ESPERADOS)
        status = "ESCALADO" if data.get("risco_ti") == "ALTO" else "APROVADO"
        confidence = self.derivar_confidence(parseou_ok, data, CAMPOS_ESPERADOS, 0.85)

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=confidence,
        )
