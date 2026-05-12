"""A-20: @Esocial-IA — eSocial Rural, Trabalhadores e Previdência
STATUS: 🔧 DESENVOLVIMENTO
CRITICIDADE: 🟡 ALTA

Nota: Agente funcional. Migrado de A-18 para A-20 conforme spec oficial 05/05/2026.
Hardening v1.2 (R-02): parse_json_response + coerção segura de campos numéricos.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Esocial-IA da ORGATEC IA, especialista em eSocial do produtor rural.
Verifique: S-1200 (remuneração), S-1210 (pagamentos), S-2200 (admissão), S-2299 (desligamento).
Calcule: contribuição previdenciária rural, FGTS trabalhadores rurais, SENAR.
Identifique: trabalhadores não informados, contribuições em atraso, irregularidades CLT Rural.
Retorne JSON: {"trabalhadores": 0, "folha_total": 0.0, "contribuicao_previdenciaria": 0.0, "senar": 0.0, "pendencias_esocial": [], "status": "REGULAR|PENDENTE|IRREGULAR"}"""

_CAMPOS = ("trabalhadores", "folha_total", "contribuicao_previdenciaria", "senar", "pendencias_esocial", "status")
_FALLBACK = {
    "trabalhadores": 0, "folha_total": 0.0, "contribuicao_previdenciaria": 0.0,
    "senar": 0.0, "pendencias_esocial": [], "status": "PENDENTE",
}

def _coerce_numericos(data: dict) -> dict:
    """Converte campos numéricos do eSocial para float/int com segurança."""
    for campo in ("folha_total", "contribuicao_previdenciaria", "senar"):
        try:
            data[campo] = float(data.get(campo) or 0)
        except (TypeError, ValueError):
            data[campo] = 0.0
    try:
        data["trabalhadores"] = int(data.get("trabalhadores") or 0)
    except (TypeError, ValueError):
        data["trabalhadores"] = 0
    if not isinstance(data.get("pendencias_esocial"), list):
        data["pendencias_esocial"] = []
    return data


class EsocialIAAgent(BaseAgent):
    agent_id = "A-20"
    name = "@Esocial-IA"

    async def process(self, payload: dict) -> AgentResult:
        esocial_data = payload.get("esocial_data", {})
        contribuinte = payload.get("contribuinte", {})
        self.log("Analisando eSocial Rural", cpf=contribuinte.get("cpf"))

        prompt = f"""Analise o eSocial do produtor rural {contribuinte.get('nome')}:
{json.dumps(esocial_data, ensure_ascii=False, indent=2)[:3000]}
Calcule contribuições previdenciárias, SENAR e verifique pendências de eventos obrigatórios."""

        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=2048)
        data, parseou_ok = self.parse_json_response(resp, _FALLBACK, _CAMPOS)
        data = _coerce_numericos(data)
        confidence = self.derivar_confidence(parseou_ok, data, _CAMPOS)

        status = "ESCALADO" if data.get("status") == "IRREGULAR" else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data, confidence=confidence)
