"""S-4 @Contabil — Patrimônio + Biológicos + Caixa + Lançamentos.

Substitui A-10 (Auditor-Patrimonio), A-13 (Monitor-Conformidade),
A-14 (Avaliador-Risco), A-17 (Previsor-Caixa), A-19 (Contabilista-IA),
A-26 (Auditor-Biologicos).

Determinístico via precalc: caixa (entradas/saídas/saldo), notas_re1 (RE-1
aplicada antes de anonimizar — corrige F14).

Modelo: Sonnet 4.6 (CPC 29 + IFRS rural).
"""
from __future__ import annotations

from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.precalc import get_precalc
from horizon_blue_one.core.prompt_compactor import kv, tsv
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = (
    "Você é o @Contabil da ORGATEC: NBC TG 29 (CPC 29) ativos biológicos, patrimônio rural, "
    "previsão de caixa e lançamentos contábeis. Receba notas já reclassificadas pela RE-1. "
    'Retorne JSON: {"ativos_biologicos":[],"valor_justo_total":0.0,"ganhos_biologicos":0.0,'
    '"previsao_caixa_30d":0.0,"lancamentos_sugeridos":[],"alertas_cpc29":[],"confianca":0.0}'
)

_CAMPOS = ("ativos_biologicos", "valor_justo_total", "previsao_caixa_30d", "lancamentos_sugeridos")


class ContabilAgent(BaseAgent):
    agent_id = "S4"
    name = "@Contabil"

    async def process(self, payload: dict) -> AgentResult:
        pre = get_precalc(payload)
        notas_re1 = pre.get("notas_re1", payload.get("notas", []))
        caixa = pre.get("caixa", {})
        contribuinte = payload.get("contribuinte", {})

        # Filtra apenas notas de ativos biológicos
        biologicos = [
            n for n in notas_re1
            if "BIOLOGICO" in str(n.get("categoria_contabil", "")).upper()
            or "ANIMAL" in str(n.get("descricao", "")).upper()
        ][:30]

        # Skip-LLM determinístico: sem ativos biológicos + caixa em ordem → resposta fixa
        if not biologicos and float(caixa.get("saldo", 0)) >= 0:
            return AgentResult(
                agent_id=self.agent_id,
                status="APROVADO",
                output={
                    "ativos_biologicos": [],
                    "valor_justo_total": 0.0,
                    "ganhos_biologicos": 0.0,
                    "previsao_caixa_30d": float(caixa.get("saldo", 0)),
                    "lancamentos_sugeridos": [],
                    "alertas_cpc29": [],
                    "fonte": "deterministico",
                },
                confidence=0.92,
            )

        amostra_tsv = tsv(biologicos, ("numero", "natureza", "valor_total", "categoria_contabil", "descricao"))
        prompt = (
            f"Contrib: {contribuinte.get('razao_social', '?')}\n"
            f"Caixa: {kv(caixa)}\n"
            f"Ativos biologicos ({len(biologicos)}/{len(notas_re1)}):\n{amostra_tsv}\n"
            "CPC 29: valor justo + ganhos transf. biologica + previsao caixa 30d + lancamentos."
        )
        resp, _ = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            num_notas=len(notas_re1),
            agent_id=self.agent_id,
            max_tokens=1536,
        )
        data, ok = self.parse_json_response(
            resp,
            fallback={
                "ativos_biologicos": [b.get("numero") for b in biologicos],
                "valor_justo_total": sum(float(b.get("valor_total", 0)) for b in biologicos),
                "ganhos_biologicos": 0.0,
                "previsao_caixa_30d": float(caixa.get("saldo", 0)),
                "lancamentos_sugeridos": [],
                "alertas_cpc29": [],
            },
            campos_esperados=_CAMPOS,
        )

        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output=data,
            confidence=self.derivar_confidence(ok, data, _CAMPOS, 0.89),
        )
