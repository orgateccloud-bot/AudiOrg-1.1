"""S-2 @Forense — Anomalias + Assurance + Grafo de conluio + LSTM + MCP.

Substitui A-04 (Vigilante), A-07 (Auditoria-Assurance), A-23 (Anomalias), A-27 (Epsilon-Forensic).

Toda detecção determinística (5 detectores, XGBoost, LSTM, métricas de grafo) roda em
`core/precalc.py`. Este agente:
  1. Lê detectores cacheados (sem recomputar).
  2. Eleva alerta se LSTM detectar produtores anômalos (score_medio ≥ 0.70).
  3. Se score > 65 ou ≥2 tipologias → chamada Sonnet com MCP tools para histórico.
  4. Caso contrário, retorna análise determinística sem LLM.

Modelo: Sonnet 4.6 (auditoria padrão); upgrade Opus se score≥85 ou 3+ tipologias.
"""
from __future__ import annotations

import json

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.limiares import (
    SCORE_ALTO,
    SCORE_BAIXO,
    SCORE_CRITICO,
    TIPOLOGIAS_LIMITE_ESCALA,
)
from horizon_blue_one.core.model_adapter import ModelType, call_model_with_tools
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import kv, resumo_detectores
from horizon_blue_one.core.token_router import TipoTarefa
from horizon_blue_one.tools.mcp_bridge import MCP_TOOLS, executar_tool

SYSTEM = (
    "Você é o @Forense da ORGATEC: consolida detectores, score XGBoost, análise temporal LSTM "
    "e grafo de conluio. Produza narrativa fundamentada (CFOP, valores, datas, partes) e tipologias "
    "mapeadas a AN-01..AN-18. Use as ferramentas disponíveis para consultar histórico do produtor "
    "quando houver anomalia temporal. "
    "RESPOSTA CONCISA: narrativa em até 8 linhas, máx 5 evidencias e 5 acoes, sem repetições. "
    'Retorne JSON: {"score_risco":0,"nivel":"BAIXO|MEDIO|ALTO|CRITICO","tipologias":[],'
    '"narrativa":"...","evidencias":[],"acoes":[],"confianca":0.0}'
)

# Limiar LSTM para acionar consulta histórica via MCP
_LSTM_THRESHOLD_MCP = 0.70

_CAMPOS = ("score_risco", "nivel", "tipologias", "narrativa")


def _nivel(score: float) -> str:
    if score >= SCORE_CRITICO: return "CRITICO"
    if score >= SCORE_ALTO:    return "ALTO"
    if score >= SCORE_BAIXO:   return "MEDIO"
    return "BAIXO"


class ForenseAgent(BaseAgent):
    agent_id = "S2"
    name = "@Forense"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        det = pre.get("detectores", {})
        xgb = pre.get("xgboost", {})
        lstm = pre.get("lstm", {})
        grafo = pre.get("grafo", {})

        score = float(xgb.get("score", 0))
        criticas = int(xgb.get("tipologias_criticas", 0))
        prob = float(xgb.get("probabilidade_autuacao", 0))

        # LSTM: eleva score se produtores anômalos detectados na série temporal
        lstm_score_medio = float(lstm.get("score_medio", 0))
        lstm_anomalos = lstm.get("produtores_anomalos", [])
        if lstm_anomalos and lstm_score_medio >= _LSTM_THRESHOLD_MCP:
            # Penalidade adicional proporcional ao score LSTM
            bonus_lstm = round(lstm_score_medio * 15, 2)
            score = min(score + bonus_lstm, 100.0)
            criticas = max(criticas, 1)
            self.log("lstm_anomalia_detectada", produtores=len(lstm_anomalos), bonus=bonus_lstm)

        # Verde determinístico: nada detectado + score baixo + LSTM limpo
        sem_deteccoes = (
            not det.get("carrossel")
            and not det.get("smurfing")
            and not det.get("devolucao_posterior")
            and not det.get("anomalia_temporal")
            and not (det.get("fornecedor_fantasma") or [])
            and not lstm_anomalos
        )
        if sem_deteccoes and score < SCORE_BAIXO:
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
                    "lstm": {"score_medio": lstm_score_medio, "anomalos": []},
                    "fonte": "deterministico",
                },
                confidence=0.93,
            )

        # Usa MCP tools quando há anomalia temporal LSTM (consulta histórico)
        usar_mcp = bool(lstm_anomalos) and lstm_score_medio >= _LSTM_THRESHOLD_MCP
        lstm_resumo = (
            f" | LSTM: score_medio={lstm_score_medio:.2f}, anomalos={len(lstm_anomalos)}"
            if lstm_anomalos else ""
        )

        prompt = (
            f"Detectores: {resumo_detectores(det)}\n"
            f"Score: {score:.1f} | prob_autuacao={prob:.2%} | criticas={criticas}{lstm_resumo}\n"
            f"Grafo: {kv({k: v for k, v in grafo.items() if k != 'hubs'})}\n"
            + (
                f"Produtores com anomalia temporal LSTM: {', '.join(lstm_anomalos[:5])}\n"
                "Use consultar_historico_produtor para investigar o padrão evolutivo.\n"
                if usar_mcp else ""
            )
            + "Narrativa forense + tipologias AN-01..AN-18 + ações."
        )

        if usar_mcp:
            # Chama com MCP tools para acesso ao histórico SQLite
            from horizon_blue_one.core.token_router import rotear
            decision = rotear(
                tipo_tarefa=TipoTarefa.FORENSE,
                score_risco=score,
                tipologias_criticas=criticas,
                probabilidade_autuacao=prob,
                agent_id=self.agent_id,
            )
            resp, uso_mcp = await call_model_with_tools(
                model_type=decision.modelo,
                prompt=prompt,
                system=SYSTEM,
                max_tokens=1900,
                tools=MCP_TOOLS,
                tool_handler=executar_tool,
            )
            self.log("mcp_tools_usados", tool_calls=uso_mcp.get("tool_calls", 0))
        else:
            resp, _ = await call_otimizado(
                prompt, SYSTEM,
                tipo_tarefa=TipoTarefa.FORENSE,
                score_risco=score,
                tipologias_criticas=criticas,
                probabilidade_autuacao=prob,
                agent_id=self.agent_id,
                max_tokens=1700,
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
        status = "ESCALADO" if score_final >= SCORE_ALTO or criticas >= TIPOLOGIAS_LIMITE_ESCALA else "APROVADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.90),
        )
