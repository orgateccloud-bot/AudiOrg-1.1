"""Calibração contínua — análise de telemetria e recomendações.

F4 do estudo Claude: consome snapshots do `token_router` e do middleware
Prometheus `claude_metrics` para emitir recomendações de:

- **mix observado**: % real de Haiku/Sonnet/Opus vs alvo 90/8/2
- **max_tokens por agente**: agentes com saturação alta (truncamento iminente)
  ou muito baixa (over-allocation)
- **thresholds de escalada**: distribuição real de upgrades/downgrades
  comparada com o esperado

O módulo é puramente analítico — não muta estado. Roda offline ou via job
agendado para emitir relatórios periódicos (semanal/mensal).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Alvos de calibração (rev 2026-05-12) ──────────────────────────────────────
# Mix-alvo da política de roteamento, espelha token_router.py.
MIX_ALVO_PCT: dict[str, float] = {
    "haiku":  0.90,
    "sonnet": 0.08,
    "opus":   0.02,
}

# Tolerância: o mix observado pode desviar em ±X pontos absolutos sem alerta.
TOLERANCIA_MIX_PCT = 0.05  # 5 pontos percentuais

# Bandas de saturação aceitáveis:
#   p95 > 0.95 → truncamento iminente (subir max_tokens)
#   p95 < 0.20 → over-allocation (reduzir max_tokens)
SATURACAO_TRUNCAMENTO = 0.95
SATURACAO_OVER_ALLOC  = 0.20


@dataclass
class Recomendacao:
    """Uma recomendação de ajuste."""
    categoria: str             # "mix" | "max_tokens" | "thresholds"
    severidade: str            # "info" | "atencao" | "critico"
    mensagem:  str
    detalhes:  dict[str, Any] = field(default_factory=dict)


# ── Análise de mix ────────────────────────────────────────────────────────────
def analisar_routing_mix(snapshot: dict[str, Any]) -> list[Recomendacao]:
    """Compara distribuição observada de chamadas com o alvo 90/8/2.

    `snapshot` é o dict devolvido por `token_router.snapshot_stats()` —
    deve conter `chamadas: dict[str, int]`.
    """
    chamadas = snapshot.get("chamadas", {})
    total = sum(chamadas.values())
    if total == 0:
        return [Recomendacao(
            categoria="mix", severidade="info",
            mensagem="Sem chamadas registradas — execute auditorias antes de calibrar.",
        )]

    recs: list[Recomendacao] = []
    for modelo, alvo in MIX_ALVO_PCT.items():
        obs = chamadas.get(modelo, 0) / total
        delta = obs - alvo
        if abs(delta) <= TOLERANCIA_MIX_PCT:
            continue
        sev = "atencao" if abs(delta) < 0.15 else "critico"
        direcao = "acima" if delta > 0 else "abaixo"
        recs.append(Recomendacao(
            categoria="mix", severidade=sev,
            mensagem=(
                f"Modelo {modelo} {direcao} do alvo: "
                f"observado {obs:.1%} vs alvo {alvo:.0%} (Δ {delta:+.1%})"
            ),
            detalhes={"modelo": modelo, "observado": round(obs, 4),
                      "alvo": alvo, "delta": round(delta, 4)},
        ))
    return recs or [Recomendacao(
        categoria="mix", severidade="info",
        mensagem=f"Mix dentro da tolerância (±{TOLERANCIA_MIX_PCT:.0%}).",
    )]


# ── Análise de saturação ──────────────────────────────────────────────────────
def analisar_saturacao(
    observacoes_por_agente: dict[str, list[float]],
) -> list[Recomendacao]:
    """Detecta agentes com saturação fora da banda saudável.

    `observacoes_por_agente`: {agent_id: [output_tokens/max_tokens, ...]}.
    Tipicamente extraído do histograma Prometheus
    `claude_output_saturation_ratio` agrupado por agente (ou por modelo).
    """
    recs: list[Recomendacao] = []
    for agente, observacoes in observacoes_por_agente.items():
        if not observacoes:
            continue
        # p95 = percentil 95
        ordenadas = sorted(observacoes)
        idx_p95 = max(0, int(len(ordenadas) * 0.95) - 1)
        p95 = ordenadas[idx_p95]
        media = sum(observacoes) / len(observacoes)

        if p95 >= SATURACAO_TRUNCAMENTO:
            recs.append(Recomendacao(
                categoria="max_tokens", severidade="critico",
                mensagem=(
                    f"Agente {agente}: p95 saturação {p95:.0%} ≥ "
                    f"{SATURACAO_TRUNCAMENTO:.0%} — risco de truncamento. "
                    "Considere subir max_tokens."
                ),
                detalhes={"agente": agente, "p95": round(p95, 4),
                          "media": round(media, 4), "n": len(observacoes)},
            ))
        elif media < SATURACAO_OVER_ALLOC:
            recs.append(Recomendacao(
                categoria="max_tokens", severidade="info",
                mensagem=(
                    f"Agente {agente}: média de saturação {media:.0%} < "
                    f"{SATURACAO_OVER_ALLOC:.0%} — over-allocation. "
                    "Considere reduzir max_tokens."
                ),
                detalhes={"agente": agente, "p95": round(p95, 4),
                          "media": round(media, 4), "n": len(observacoes)},
            ))
    return recs or [Recomendacao(
        categoria="max_tokens", severidade="info",
        mensagem="Saturação dentro de bandas saudáveis.",
    )]


# ── Análise de escalada (upgrades/downgrades) ─────────────────────────────────
def analisar_thresholds_escalada(snapshot: dict[str, Any]) -> list[Recomendacao]:
    """Avalia se a taxa de upgrades/downgrades faz sentido vs volume total.

    Heurística: upgrades para Opus deveriam ficar próximos de 2% (alvo Opus).
    Se passa de 5%, threshold de score (85) está baixo demais. Se fica em
    0% mesmo com volume alto, threshold pode estar alto demais.
    """
    chamadas = snapshot.get("chamadas", {})
    upgrades = int(snapshot.get("upgrades", 0))
    downgrades = int(snapshot.get("downgrades", 0))
    total = sum(chamadas.values())
    if total < 50:
        return [Recomendacao(
            categoria="thresholds", severidade="info",
            mensagem=f"Volume baixo ({total} chamadas) — calibração precisa de ≥50 amostras.",
            detalhes={"total": total},
        )]

    recs: list[Recomendacao] = []
    pct_up   = upgrades / total
    pct_down = downgrades / total

    if pct_up > 0.05:
        recs.append(Recomendacao(
            categoria="thresholds", severidade="atencao",
            mensagem=(
                f"Upgrades para Opus em {pct_up:.1%} (alvo ~2%). "
                "Considere subir score_risco mínimo de 85 → 90."
            ),
            detalhes={"upgrades": upgrades, "pct": round(pct_up, 4)},
        ))
    elif pct_up == 0 and total >= 200:
        recs.append(Recomendacao(
            categoria="thresholds", severidade="info",
            mensagem=(
                f"Nenhum upgrade em {total} chamadas. Threshold de score (85) "
                "pode estar alto demais para o portfólio atual."
            ),
            detalhes={"total": total},
        ))

    if pct_down > 0.50:
        recs.append(Recomendacao(
            categoria="thresholds", severidade="info",
            mensagem=(
                f"Downgrades em {pct_down:.1%} — política conservadora vem "
                "ganhando muito. Saúde de custo OK."
            ),
            detalhes={"downgrades": downgrades, "pct": round(pct_down, 4)},
        ))
    return recs or [Recomendacao(
        categoria="thresholds", severidade="info",
        mensagem="Escaladas dentro do esperado.",
    )]


# ── Relatório consolidado ────────────────────────────────────────────────────
def relatorio_calibracao(
    snapshot: dict[str, Any],
    observacoes_por_agente: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Gera relatório consolidado pronto para serializar.

    Retorna estrutura:
      {
        "mix":         [Recomendacao, ...],
        "saturacao":   [Recomendacao, ...],
        "thresholds":  [Recomendacao, ...],
        "resumo": {
          "n_criticos": X,
          "n_atencao":  Y,
          "n_info":     Z,
        }
      }
    """
    obs = observacoes_por_agente or {}
    mix   = analisar_routing_mix(snapshot)
    sat   = analisar_saturacao(obs)
    thr   = analisar_thresholds_escalada(snapshot)

    todas = mix + sat + thr
    resumo = {
        "n_criticos": sum(1 for r in todas if r.severidade == "critico"),
        "n_atencao":  sum(1 for r in todas if r.severidade == "atencao"),
        "n_info":     sum(1 for r in todas if r.severidade == "info"),
    }
    return {
        "mix":        [_rec_dict(r) for r in mix],
        "saturacao":  [_rec_dict(r) for r in sat],
        "thresholds": [_rec_dict(r) for r in thr],
        "resumo":     resumo,
    }


def _rec_dict(r: Recomendacao) -> dict[str, Any]:
    return {
        "categoria":  r.categoria,
        "severidade": r.severidade,
        "mensagem":   r.mensagem,
        "detalhes":   r.detalhes,
    }
