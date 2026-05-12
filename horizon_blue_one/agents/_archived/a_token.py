"""A-Token @Token — Agente de Otimização de Tokens e Roteamento de Modelos.

Responsabilidades:
  1. Analisar complexidade do payload e decidir qual modelo usar.
  2. Expor `call_otimizado()` para que outros agentes deleguem o roteamento.
  3. Rastrear uso e custo acumulado de toda a sessão.
  4. Reportar economia vs "sempre Sonnet".

Política:
  Haiku  → classificação, extração, LGPD, roteamento, conformidade simples
  Sonnet → auditoria padrão (fiscal rural, ICMS, ITR, forense ≤ 2 tipologias)
  Opus   → score ≥ 85  |  tipologias críticas ≥ 3  |  prob. autuação ≥ 75%
"""
from __future__ import annotations

import json
import time
from typing import Optional

import structlog

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType, call_model
from horizon_blue_one.core.token_router import (
    TipoTarefa,
    RotingDecision,
    estimar_tokens,
    get_stats,
    registrar_uso,
    rotear,
)

logger = structlog.get_logger()


class TokenAgent(BaseAgent):
    """@Token — Roteador e otimizador de consumo de tokens Claude."""

    agent_id = "A-Token"
    name     = "@Token"

    async def process(self, payload: dict) -> AgentResult:
        """Analisa o payload e retorna a decisão de roteamento com estatísticas."""
        notas                  = payload.get("notas", [])
        score_risco            = float(payload.get("score_risco", {}).get("score", 0)
                                       if isinstance(payload.get("score_risco"), dict)
                                       else payload.get("score_risco", 0))
        tipologias_criticas    = int(payload.get("tipologias_criticas", 0))
        probabilidade_autuacao = float(payload.get("probabilidade_autuacao", 0.0))
        agent_id_alvo          = payload.get("agent_id_alvo")
        tipo_tarefa_str        = payload.get("tipo_tarefa", "auditoria")

        try:
            tipo_tarefa = TipoTarefa(tipo_tarefa_str)
        except ValueError:
            tipo_tarefa = TipoTarefa.AUDITORIA

        decision = rotear(
            tipo_tarefa=tipo_tarefa,
            score_risco=score_risco,
            tipologias_criticas=tipologias_criticas,
            probabilidade_autuacao=probabilidade_autuacao,
            num_notas=len(notas),
            agent_id=agent_id_alvo,
        )

        self.log(
            "roteamento_decidido",
            modelo=decision.modelo.value,
            motivo=decision.motivo,
            upgrade=decision.upgrade_aplicado,
            downgrade=decision.downgrade_aplicado,
        )

        stats = get_stats()
        output = {
            "modelo_recomendado": decision.modelo.value,
            "tipo_tarefa":        decision.tipo_tarefa.value,
            "motivo":             decision.motivo,
            "upgrade_aplicado":   decision.upgrade_aplicado,
            "downgrade_aplicado": decision.downgrade_aplicado,
            "stats_sessao":       stats,
        }
        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output=output,
            confidence=1.0,
        )


# ── API Pública — uso direto pelos outros agentes ─────────────────────────────

async def call_otimizado(
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    tipo_tarefa: TipoTarefa = TipoTarefa.AUDITORIA,
    score_risco: float = 0.0,
    tipologias_criticas: int = 0,
    probabilidade_autuacao: float = 0.0,
    num_notas: int = 0,
    agent_id: Optional[str] = None,
) -> tuple[str, RotingDecision]:
    """Chama o modelo Claude mais econômico para a tarefa.

    Retorna (resposta_texto, decisao_roteamento) para que o chamador
    possa registrar o uso real de tokens com `registrar_uso()`.

    Uso típico em um agente:
        resp, dec = await call_otimizado(
            prompt, SYSTEM,
            tipo_tarefa=TipoTarefa.AUDITORIA,
            score_risco=score_info["score"],
            max_tokens=2048,
            agent_id=self.agent_id,
        )
        tokens_in  = estimar_tokens(prompt + SYSTEM)
        tokens_out = estimar_tokens(resp)
        registrar_uso(dec.modelo, tokens_in, tokens_out, dec)
    """
    decision = rotear(
        tipo_tarefa=tipo_tarefa,
        score_risco=score_risco,
        tipologias_criticas=tipologias_criticas,
        probabilidade_autuacao=probabilidade_autuacao,
        num_notas=num_notas,
        agent_id=agent_id,
    )

    logger.info(
        "call_otimizado",
        modelo=decision.modelo.value,
        motivo=decision.motivo,
        agent_id=agent_id or "direto",
    )

    resp = await call_model(
        model_type=decision.modelo,
        prompt=prompt,
        system=system,
        max_tokens=max_tokens,
    )

    # Auto-registro de tokens estimados
    tokens_in  = estimar_tokens(prompt + system)
    tokens_out = estimar_tokens(resp)
    registrar_uso(decision.modelo, tokens_in, tokens_out, decision)

    return resp, decision


async def relatorio_custo() -> dict:
    """Retorna relatório completo de uso e custo da sessão atual."""
    stats = get_stats()

    # Custo projetado mensal (assumindo mesma taxa por 30 dias)
    custo_sessao = stats.get("custo_total_usd", 0)
    stats["projecao_mensal_usd"] = round(custo_sessao * 30, 4)

    return {
        "agente":  "A-Token @Token",
        "relatorio": stats,
    }
