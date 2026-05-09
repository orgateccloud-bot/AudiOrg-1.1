"""S-7 @CEO — Governança + Jurídico + MD&A consolidados.

Substitui A-00 (CEO), A-15 (Juridico-Ext), A-18 (Analista-CSuite).

Roda SEMPRE por último, agregando saídas de S1..S6. Decide:
  - Aprovação final
  - Escalada jurídica (se S2 detectou tipologias críticas)
  - Geração de MD&A executivo

Modelo: Sonnet 4.6 default; UPGRADE para Opus 4.7 se score≥85 OU valor>R$1M
                                  OU 3+ tipologias críticas.
"""
from __future__ import annotations

import json

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.limiares import (
    SCORE_ALTO,
    SCORE_CRITICO,
    TIPOLOGIAS_LIMITE_OPUS,
)
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import kv
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @CEO da ORGATEC: governança final, parecer jurídico e MD&A. "
    "Receba consolidação de todos os agentes (S1..S6) e o precalc determinístico. "
    'Retorne JSON: {"decisao":"APROVAR|REVISAR|ESCALAR_JURIDICO|REJEITAR",'
    '"score_final":0.0,"parecer_juridico":"...","mda_executivo":"...",'
    '"acoes_imediatas":[],"riscos_residuais":[],"confianca":0.0}'
)

_CAMPOS = ("decisao", "score_final", "parecer_juridico", "mda_executivo")


class CEOAgent(BaseAgent):
    agent_id = "S7"
    name = "@CEO"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        resultados = payload.get("resultados_agentes", {})
        contribuinte = payload.get("contribuinte", {}) or {}

        xgb = pre.get("xgboost", {})
        score = float(payload.get("score_risco", xgb.get("score", 0)))
        criticas = int(xgb.get("tipologias_criticas", 0))
        prob = float(xgb.get("probabilidade_autuacao", 0))
        valor_total = float(pre.get("caixa", {}).get("entradas", 0))

        # Resumo ultra-compacto: 1 linha por agente em formato kv
        linhas = []
        chaves = ("lgpd_status", "documentos_status", "nivel", "lcdpr_status",
                  "cfop_status", "conformidade_sefaz_go", "conformidade")
        for aid, out in resultados.items():
            if not isinstance(out, dict):
                continue
            sub = {k: out.get(k) for k in chaves if k in out}
            if sub:
                linhas.append(f"{aid}: {kv(sub)}")
        resumo_txt = "\n".join(linhas) or "(sem agentes)"

        prompt = (
            f"Contrib: {contribuinte.get('razao_social', '?')} | "
            f"score={score:.1f} criticas={criticas} prob={prob:.2%} | "
            f"valor=R${valor_total:,.0f}\n"
            f"Agentes:\n{resumo_txt}\n"
            "Decisao + parecer juridico curto + MD&A executivo."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            score_risco=score,
            tipologias_criticas=criticas,
            probabilidade_autuacao=prob,
            agent_id=self.agent_id,
            max_tokens=2048,
        )
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "decisao":          "ESCALAR_JURIDICO" if score >= SCORE_CRITICO or criticas >= TIPOLOGIAS_LIMITE_OPUS else
                                    "REVISAR" if score >= SCORE_ALTO else "APROVAR",
                "score_final":      score,
                "parecer_juridico": "Parecer indisponível (parse falhou).",
                "mda_executivo":    "MD&A indisponível.",
                "acoes_imediatas":  [],
                "riscos_residuais": [],
            },
            campos_esperados=_CAMPOS,
        )
        data["resumo_agentes"] = resumo_txt
        data["precalc_score"] = score

        decisao = data.get("decisao", "APROVAR")
        if decisao == "REJEITAR":
            status = "REJEITADO"
        elif decisao in ("ESCALAR_JURIDICO", "REVISAR"):
            status = "ESCALADO"
        else:
            status = "APROVADO"

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.92),
        )
