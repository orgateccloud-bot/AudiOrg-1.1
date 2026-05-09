"""S-5 @NFA — Auditoria núcleo de Notas Fiscais Avulsas.

Substitui A-06 (Extrator) parcial + A-08 (Auditor-NFA) + A-05 (Engenheiro-ERP).

A extração XML/OCR continua sendo etapa de ingestão (A-06 fica como utilitário
em `_legacy/`). Este agente foca na auditoria das notas já extraídas e
pré-classificadas pela RE-1 no precalc.

Modelo: Sonnet 4.6 (auditoria padrão NFA).
"""
from __future__ import annotations

import json

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import resumo_detectores, resumo_notas
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @AuditorNFA da ORGATEC: audita Notas Fiscais Avulsas rurais (Goiás SEFAZ). "
    "Receba totais agregados e amostra de notas já classificadas pela Regra Especial 1. "
    'Retorne JSON: {"total_notas":0,"total_valor":0.0,"divergencias":[],"riscos":[],'
    '"conformidade_sefaz_go":"CONFORME|DIVERGENTE|CRITICO","confianca":0.0}'
)

_CAMPOS = ("total_notas", "total_valor", "divergencias", "conformidade_sefaz_go")


class NFAAgent(BaseAgent):
    agent_id = "S5"
    name = "@AuditorNFA"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        notas_re1 = pre.get("notas_re1", payload.get("notas", []))
        cfop = pre.get("cfop", {})
        det = pre.get("detectores", {})
        xgb = pre.get("xgboost", {})

        total_valor = sum(float(n.get("valor_total", 0)) for n in notas_re1)

        # Skip-LLM: zero divergências CFOP + zero detecções → conformidade certa
        sem_deteccoes = not any([
            det.get("carrossel"), det.get("smurfing"),
            det.get("devolucao_posterior"), det.get("anomalia_temporal"),
            det.get("fornecedor_fantasma"),
        ])
        if cfop.get("total_divergencias", 0) == 0 and sem_deteccoes:
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "total_notas": len(notas_re1),
                    "total_valor": round(total_valor, 2),
                    "divergencias": [],
                    "riscos": [],
                    "conformidade_sefaz_go": "CONFORME",
                    "fonte": "deterministico",
                },
                confidence=0.93,
            )

        prompt = (
            f"Total: {len(notas_re1)} notas R$ {total_valor:,.2f} | "
            f"CFOP_div: {cfop.get('total_divergencias', 0)}\n"
            f"Det: {resumo_detectores(det)}\n"
            f"Amostra:\n{resumo_notas(notas_re1, limite=20)}\n"
            "Conformidade SEFAZ-GO + divergencias natureza/CFOP/categoria + riscos."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            score_risco=float(xgb.get("score", 0)),
            num_notas=len(notas_re1),
            agent_id=self.agent_id,
            max_tokens=1536,
        )
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "total_notas": len(notas_re1),
                "total_valor": round(total_valor, 2),
                "divergencias": cfop.get("divergentes", [])[:20],
                "riscos": [k for k, v in det.items() if v],
                "conformidade_sefaz_go": "DIVERGENTE" if cfop.get("total_divergencias", 0) else "CONFORME",
            },
            campos_esperados=_CAMPOS,
        )
        data["total_notas"] = len(notas_re1)
        data["total_valor"] = round(total_valor, 2)

        critico = data.get("conformidade_sefaz_go") == "CRITICO" or cfop.get("total_divergencias", 0) > 10
        return AgentResult(
            agent_id=self.agent_id,
            status="ESCALADO" if critico else "APROVADO",
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.90),
        )
