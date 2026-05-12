"""S-6 @RH — eSocial isolado.

Substitui A-20 (Esocial-IA). Mantido isolado dos outros 6 porque o domínio
trabalhista/previdenciário não compartilha precalc fiscal/contábil.

Modelo: Sonnet 4.6 (regras eSocial S-1000..S-2240).
"""
from __future__ import annotations

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.prompt_compactor import kv
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @RH da ORGATEC: especialista em eSocial rural (S-1000..S-2240, FGTS, INSS rural). "
    'Retorne JSON: {"eventos_pendentes":[],"divergencias_inss":0.0,"fgts_a_recolher":0.0,'
    '"alertas":[],"conformidade":"CONFORME|DIVERGENTE|CRITICO","confianca":0.0}'
)

_CAMPOS = ("eventos_pendentes", "divergencias_inss", "fgts_a_recolher", "conformidade")


def _coerce_num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _audit_esocial_trivial(esocial: dict) -> bool:
    """Heurística: dados eSocial sem divergência → skip LLM.

    Critérios (todos devem ser verdadeiros):
      - trabalhadores ≤ 5 (microprodutor; baixíssimo risco)
      - eventos_pendentes ausente ou lista vazia
      - inss_divergencia / fgts_pendente ausentes ou zerados
    """
    trabalhadores = int(esocial.get("trabalhadores", 0) or 0)
    pendentes = esocial.get("eventos_pendentes", []) or []
    inss_div = _coerce_num(esocial.get("inss_divergencia", 0))
    fgts_pend = _coerce_num(esocial.get("fgts_pendente", 0))
    return (
        trabalhadores <= 5
        and not pendentes
        and inss_div == 0.0
        and fgts_pend == 0.0
    )


class RHAgent(BaseAgent):
    agent_id = "S6"
    name = "@RH"

    async def process(self, payload: dict) -> AgentResult:
        esocial = payload.get("esocial_data", {}) or {}
        contribuinte = payload.get("contribuinte", {}) or {}

        if not esocial:
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "eventos_pendentes": [],
                    "divergencias_inss": 0.0,
                    "fgts_a_recolher": 0.0,
                    "alertas": ["Sem dados eSocial no payload"],
                    "conformidade": "CONFORME",
                    "fonte": "deterministico",
                },
                confidence=0.80,
            )

        # Skip-LLM: dados triviais sem risco → resposta determinística
        if _audit_esocial_trivial(esocial):
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "eventos_pendentes": [],
                    "divergencias_inss": 0.0,
                    "fgts_a_recolher": 0.0,
                    "alertas": ["eSocial trivial — análise determinística aplicada"],
                    "conformidade": "CONFORME",
                    "fonte": "deterministico",
                },
                confidence=0.82,
            )

        prompt = (
            f"Contrib: {contribuinte.get('razao_social', '?')}\n"
            f"eSocial: {kv(esocial)}\n"
            "Eventos S-1000..S-2240 + INSS rural + FGTS + regularizações."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            agent_id=self.agent_id,
            max_tokens=1024,
        )
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "eventos_pendentes": [],
                "divergencias_inss": 0.0,
                "fgts_a_recolher": 0.0,
                "alertas": ["Parse falhou — revisar manualmente"],
                "conformidade": "DIVERGENTE",
            },
            campos_esperados=_CAMPOS,
        )
        data["divergencias_inss"] = _coerce_num(data.get("divergencias_inss"))
        data["fgts_a_recolher"] = _coerce_num(data.get("fgts_a_recolher"))

        critico = data.get("conformidade") == "CRITICO"
        return AgentResult(
            agent_id=self.agent_id,
            status="ESCALADO" if critico else "APROVADO",
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.87),
        )
