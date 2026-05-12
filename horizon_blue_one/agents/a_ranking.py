"""A-Ranking — Priorização de risco em lote.

Recebe N laudos já processados e devolve ranking CRÍTICO / ATENÇÃO / OK
para que o contador veja primeiro os casos que mais importam.

Heurística determinística primeiro (score, qtd anomalias, valor); Claude
interpreta o ranking final e gera o sumário executivo.
"""
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType

SYSTEM = """Você é o @Ranking do OrgAudi. Recebe um conjunto de laudos já
emitidos e produz um sumário executivo em pt-BR para o contador.

Sua tarefa: explicar em 1 parágrafo o panorama do lote (quantos críticos,
quantas notas no total, principais tipologias AN detectadas) e listar os
top 3 produtores que demandam atenção imediata, com 1 frase de justificativa
cada.

Devolva JSON:
{
  "sumario": "...",
  "top_atencao": [{"cliente_id": int, "motivo": "..."}],
  "tipologias_dominantes": ["AN-XX", ...]
}
"""


def _classificar(laudo: dict) -> str:
    """Heurística determinística — Python, não Claude."""
    score = 0.0
    score_info = laudo.get("score_xgboost")
    if isinstance(score_info, dict):
        score = float(score_info.get("score") or 0)
    elif isinstance(score_info, (int, float)):
        score = float(score_info)

    qtd_anom = len(laudo.get("anomalias_detectadas") or [])
    valor = float(laudo.get("valor_total") or 0)

    if score >= 85 or qtd_anom >= 5 or valor > 1_000_000:
        return "CRITICO"
    if score >= 65 or qtd_anom >= 2:
        return "ATENCAO"
    return "OK"


class ARankingAgent(BaseAgent):
    agent_id = "A-RANKING"
    name = "@Ranking"

    async def process(self, payload: dict) -> AgentResult:
        """Espera payload: {laudos: list[dict]}."""
        laudos = payload.get("laudos") or []
        if not laudos:
            return AgentResult(
                agent_id=self.agent_id,
                status="REJEITADO",
                output={"erro": "lista de laudos vazia"},
                confidence=0.0,
            )

        # Classificação determinística primeiro
        classificados = []
        for laudo in laudos:
            categoria = _classificar(laudo)
            classificados.append({
                "cliente_id":  laudo.get("cliente_id") or laudo.get("client_id"),
                "result_id":   laudo.get("result_id"),
                "categoria":   categoria,
                "qtd_anomalias": len(laudo.get("anomalias_detectadas") or []),
                "valor_total": float(laudo.get("valor_total") or 0),
                "score":       (laudo.get("score_xgboost") or {}).get("score")
                                if isinstance(laudo.get("score_xgboost"), dict)
                                else laudo.get("score_xgboost"),
            })

        # Sumário pelo modelo
        contagem = {
            "CRITICO":  sum(1 for c in classificados if c["categoria"] == "CRITICO"),
            "ATENCAO":  sum(1 for c in classificados if c["categoria"] == "ATENCAO"),
            "OK":       sum(1 for c in classificados if c["categoria"] == "OK"),
        }

        self.log("Ranking determinístico", **contagem)

        # Claude gera o sumário com base nos classificados (anonimizados pelo @Delta)
        resp = await self._call_llm(
            model_type=ModelType.SONNET,
            prompt_payload={
                "contagem":      contagem,
                "classificados": classificados[:50],  # cap para não estourar tokens
            },
            prompt_template=(
                "Lote auditado: {payload}\n\n"
                "Gere o sumário executivo conforme schema do system."
            ),
            system=SYSTEM,
            max_tokens=1500,
        )

        data, ok = self.parse_json_response(
            resp,
            fallback={
                "sumario": f"Lote processado: {contagem['CRITICO']} crítico(s), "
                           f"{contagem['ATENCAO']} atenção, {contagem['OK']} OK.",
                "top_atencao": [],
                "tipologias_dominantes": [],
            },
            campos_esperados=("sumario",),
        )

        confidence = self.derivar_confidence(ok, data, campos_esperados=("sumario",))

        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output={
                "contagem":        contagem,
                "classificados":   classificados,
                "sumario":         data.get("sumario"),
                "top_atencao":     data.get("top_atencao") or [],
                "tipologias_dominantes": data.get("tipologias_dominantes") or [],
            },
            confidence=confidence,
        )
