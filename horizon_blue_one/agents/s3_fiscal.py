"""S-3 @Fiscal — ICMS + ITR + LCDPR + CFOP + Tributário consolidados.

Substitui A-11 (Planejador-Tributario), A-12 (Descobridor-Deducoes),
A-21 (Auditor-ICMS), A-22 (Auditor-ITR), A-24 (Classificador-CFOP),
A-25 (Auditor-LCDPR).

Determinístico (precalc): CFOP_RURAL_VALIDOS check, divergência LCDPR, GU ITR,
caixa entradas/saídas. Aqui:
  1. Se zero divergências em CFOP/LCDPR/ITR → resposta determinística.
  2. Caso contrário, UMA chamada Sonnet com TODOS os totais agregados.

Modelo: Sonnet 4.6 (auditoria fiscal rural padrão).
"""
from __future__ import annotations

import json

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.limiares import (
    CFOP_DIV_LIMITE_FISCAL,
    LCDPR_DIVERGENCIA_CRITICA,
    LCDPR_TOLERANCIA,
)
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import kv
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @Fiscal da ORGATEC: ICMS rural, ITR, LCDPR, CFOP e planejamento tributário. "
    "Receba totais agregados (não notas individuais). "
    'Retorne JSON: {"icms_status":"OK|DIVERGENTE","itr_status":"OK|SUBUTILIZADO",'
    '"lcdpr_status":"CONFORME|DIVERGENTE|CRITICO","cfop_status":"OK|DIVERGENTE",'
    '"deducoes_legais":[],"alertas":[],"total_divergencia":0.0,"confianca":0.0}'
)

_CAMPOS = ("icms_status", "itr_status", "lcdpr_status", "cfop_status")


class FiscalAgent(BaseAgent):
    agent_id = "S3"
    name = "@Fiscal"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        cfop = pre.get("cfop", {})
        lcdpr = pre.get("lcdpr", {})
        itr = pre.get("itr", {})
        caixa = pre.get("caixa", {})

        cfop_div = int(cfop.get("total_divergencias", 0))
        lcdpr_div = float(lcdpr.get("divergencia", 0))
        gu = float(itr.get("gu_pct", 100))
        subutilizado = bool(itr.get("subutilizado", False))

        # Verde determinístico
        if cfop_div == 0 and abs(lcdpr_div) < LCDPR_TOLERANCIA and not subutilizado:
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "icms_status": "OK",
                    "itr_status": "OK",
                    "lcdpr_status": "CONFORME",
                    "cfop_status": "OK",
                    "cfop": cfop, "lcdpr": lcdpr, "itr": itr, "caixa": caixa,
                    "deducoes_legais": [],
                    "alertas": [],
                    "total_divergencia": 0.0,
                    "fonte": "deterministico",
                },
                confidence=0.94,
            )

        # Top-5 divergentes em formato denso (numero:cfop)
        exemplos = ",".join(f"{d.get('numero','?')}:{d.get('cfop','?')}"
                            for d in cfop.get("divergentes", [])[:5]) or "-"
        prompt = (
            f"CFOP: {cfop_div}/{cfop.get('total', 0)} div | top: {exemplos}\n"
            f"LCDPR: {kv({'rec_notas': lcdpr.get('receita_notas'), 'rec_lcdpr': lcdpr.get('receita_lcdpr'), 'div': lcdpr_div, 'status': lcdpr.get('status_conformidade')})}\n"
            f"ITR: GU={gu:.1f}% area={itr.get('area_total_ha')}ha subutil={'sim' if subutilizado else 'nao'}\n"
            f"Caixa: ent={caixa.get('entradas')} sai={caixa.get('saidas')}\n"
            "ICMS rural + LCDPR + ITR + CFOPs corretos + deduções legais."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            num_notas=int(cfop.get("total", 0)),
            agent_id=self.agent_id,
            max_tokens=2048,
        )
        fallback_lcdpr = lcdpr.get("status_conformidade", "DIVERGENTE")
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "icms_status":      "DIVERGENTE" if cfop_div else "OK",
                "itr_status":       "SUBUTILIZADO" if subutilizado else "OK",
                "lcdpr_status":     fallback_lcdpr,
                "cfop_status":      "DIVERGENTE" if cfop_div else "OK",
                "deducoes_legais":  [],
                "alertas":          [],
                "total_divergencia": abs(lcdpr_div),
            },
            campos_esperados=_CAMPOS,
        )
        # Output enxuto — precalc no root do payload, sem duplicação

        critico = (
            data.get("lcdpr_status") == "CRITICO"
            or cfop_div > CFOP_DIV_LIMITE_FISCAL
            or abs(lcdpr_div) > LCDPR_DIVERGENCIA_CRITICA
        )
        return AgentResult(
            agent_id=self.agent_id,
            status="ESCALADO" if critico else "APROVADO",
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.90),
        )
