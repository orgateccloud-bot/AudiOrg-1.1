"""S-2 @Forense — Anomalias + Assurance + Grafo de conluio.

Substitui A-04 (Vigilante), A-07 (Auditoria-Assurance), A-23 (Anomalias), A-27 (Epsilon-Forensic).

Toda detecção determinística (5 detectores, XGBoost, métricas de grafo) roda em
`core/precalc.py`. Este agente:
  1. Lê detectores cacheados (sem recomputar).
  2. Se score > 65 ou ≥2 tipologias → chamada Sonnet com narrativa forense.
  3. Caso contrário, retorna análise determinística sem LLM.

Modelo: Sonnet 4.6 (auditoria padrão); upgrade Opus se score≥85 ou 3+ tipologias.
"""
from __future__ import annotations

import json

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import kv, resumo_detectores
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @Forense da ORGATEC: consolida detectores, score XGBoost e grafo de conluio. "
    "Produza narrativa fundamentada (CFOP, valores, datas, partes) e tipologias mapeadas a AN-01..AN-18. "
    'Retorne JSON: {"score_risco":0,"nivel":"BAIXO|MEDIO|ALTO|CRITICO","tipologias":[],'
    '"narrativa":"...","evidencias":[],"acoes":[],"confianca":0.0}'
)

_CAMPOS = ("score_risco", "nivel", "tipologias", "narrativa")


def _nivel(score: float) -> str:
    if score >= 85: return "CRITICO"
    if score >= 65: return "ALTO"
    if score >= 40: return "MEDIO"
    return "BAIXO"


class ForenseAgent(BaseAgent):
    agent_id = "S2"
    name = "@Forense"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        det = pre.get("detectores", {})
        xgb = pre.get("xgboost", {})
        grafo = pre.get("grafo", {})

        score = float(xgb.get("score", 0))
        criticas = int(xgb.get("tipologias_criticas", 0))
        prob = float(xgb.get("probabilidade_autuacao", 0))

        # Verde determinístico: nada detectado + score baixo
        sem_deteccoes = (
            not det.get("carrossel")
            and not det.get("smurfing")
            and not det.get("devolucao_posterior")
            and not det.get("anomalia_temporal")
            and not (det.get("fornecedor_fantasma") or [])
        )
        if sem_deteccoes and score < 40:
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "score_risco": score,
                    "nivel": _nivel(score),
                    "tipologias": [],
                    "narrativa": "Nenhuma tipologia AN-01..AN-18 detectada; score abaixo do limiar.",
                    "evidencias": [],
                    "detectores": det,
                    "grafo": grafo,
                    "fonte": "deterministico",
                },
                confidence=0.93,
            )

        prompt = (
            f"Detectores: {resumo_detectores(det)}\n"
            f"Score: {score:.1f} | prob_autuacao={prob:.2%} | criticas={criticas}\n"
            f"Grafo: {kv({k: v for k, v in grafo.items() if k != 'hubs'})}\n"
            "Narrativa forense + tipologias AN-01..AN-18 + ações."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.FORENSE,
            score_risco=score,
            tipologias_criticas=criticas,
            probabilidade_autuacao=prob,
            agent_id=self.agent_id,
            max_tokens=2048,
        )
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "score_risco": score,
                "nivel": _nivel(score),
                "tipologias": [k for k, v in det.items() if v],
                "narrativa": resp[:500] if resp else "",
                "evidencias": [],
                "acoes": [],
            },
            campos_esperados=_CAMPOS,
        )
        data.setdefault("score_risco", score)
        # Output enxuto: precalc já está em payload root, evita duplicação O(n²)

        try:
            score_final = float(data.get("score_risco", score))
        except (TypeError, ValueError):
            score_final = score
        status = "ESCALADO" if score_final >= 65 or criticas >= 2 else "APROVADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.90),
        )
