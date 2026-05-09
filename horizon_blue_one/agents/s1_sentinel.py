"""S-1 @Sentinel — LGPD + ZeroTrust + TI consolidados.

Substitui A-02 (Protetor), A-03 (ZeroTrust), A-09 (Auditor-TI), A-16 (LGPD).

Toda a lógica determinística (regex CPF/CNPJ/conta, validação documental, IE)
roda no `core/precalc.py`. Aqui apenas:
  1. Lê o cache `__precalc__` (zero recomputo).
  2. Se houver pendências críticas, faz UMA chamada Haiku (compliance simples).
  3. Caso contrário, retorna verde sem LLM.

Modelo: Haiku 4.5 (tarefa de classificação/conformidade simples).
"""
from __future__ import annotations

import json

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.limiares import PENDENCIAS_DOCUMENTAIS_CRITICAS
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import kv
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @Sentinel da ORGATEC: avalia LGPD + ZeroTrust + TI em conjunto. "
    "Receba PII detectado, pendências documentais e IE. "
    'Retorne JSON: {"lgpd_status":"CONFORME|ALERTA|VIOLACAO","documentos_status":"OK|PENDENCIA|CRITICO",'
    '"recomendacoes":[],"confianca":0.0}'
)

_CAMPOS = ("lgpd_status", "documentos_status", "recomendacoes")


class SentinelAgent(BaseAgent):
    agent_id = "S1"
    name = "@Sentinel"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        pii = pre.get("pii", {})
        docs = pre.get("documentos", {})

        total_pii = int(pii.get("total_pii", 0))
        pendencias = int(docs.get("total_pendencias", 0))
        ie_valida = bool(docs.get("ie_valida", False))

        # Verde determinístico: zero PII em campos abertos + zero pendências + IE válida
        if total_pii == 0 and pendencias == 0 and ie_valida:
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "lgpd_status": "CONFORME",
                    "documentos_status": "OK",
                    "pii": pii,
                    "documentos": docs,
                    "recomendacoes": [],
                    "fonte": "deterministico",
                },
                confidence=0.95,
            )

        prompt = (
            f"PII: {kv(pii)}\n"
            f"Docs: {kv(docs)}\n"
            "Avalie conformidade LGPD, ZeroTrust documental e indique top-3 ações."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.LGPD,
            agent_id=self.agent_id,
            max_tokens=512,
        )
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "lgpd_status": "ALERTA" if total_pii > 0 else "CONFORME",
                "documentos_status": "CRITICO" if pendencias > PENDENCIAS_DOCUMENTAIS_CRITICAS else "PENDENCIA" if pendencias else "OK",
                "recomendacoes": ["revisar pendencias documentais"] if pendencias else [],
            },
            campos_esperados=_CAMPOS,
        )
        data["pii"] = pii
        data["documentos"] = docs

        status = "ESCALADO" if data.get("lgpd_status") == "VIOLACAO" or data.get("documentos_status") == "CRITICO" else "APROVADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.88),
        )
