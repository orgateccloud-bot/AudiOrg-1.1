"""A-16: @LGPD — Conformidade e Privacidade de Dados.

Hardening v1.1:
- Confidence DERIVADA do response (não mais hardcoded 0.95).
- Schema de saída declarado para validação automática.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @LGPD da ORGATEC IA.
Avalie o tratamento de dados pessoais (PII) nas operações analisadas, garantindo aderência à Lei Geral de Proteção de Dados.
Responda APENAS com JSON:
{"risco_lgpd": "BAIXO|MÉDIO|ALTO", "dados_sensiveis_expostos": [], "recomendacoes_anonimizacao": [], "confianca": 0.0}"""

CAMPOS_ESPERADOS = ("risco_lgpd", "dados_sensiveis_expostos", "recomendacoes_anonimizacao")
FALLBACK = {
    "risco_lgpd": "MÉDIO",
    "dados_sensiveis_expostos": ["Verificação pendente"],
    "recomendacoes_anonimizacao": [],
}


class LGPDAgent(BaseAgent):
    agent_id = "A-16"
    name = "@LGPD"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Varrendo payload em busca de PII e violações LGPD")
        prompt = f"Avalie o nível de exposição de dados pessoais:\n{json.dumps(payload)[:1500]}"

        try:
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=1024, agent_id=self.agent_id))[0]
        except Exception as exc:
            self.log_error("Falha ao chamar modelo LGPD", exc=exc)
            resp = ""

        data, parseou_ok = self.parse_json_response(resp, FALLBACK, CAMPOS_ESPERADOS)
        status = "ESCALADO" if data.get("risco_lgpd") == "ALTO" else "APROVADO"
        confidence = self.derivar_confidence(parseou_ok, data, CAMPOS_ESPERADOS, 0.95)

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=confidence,
        )
