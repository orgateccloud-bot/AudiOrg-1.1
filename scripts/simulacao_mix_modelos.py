"""
Simula o mix de modelos do squad Horizon-Blue após reconfiguração 80/15/5.

Roda rotear() para cada um dos 28 agentes em 3 cenários típicos:
  - baseline:    score_risco=42, sem tipologias críticas
  - alerta:      score_risco=70 (acima do threshold de downgrade)
  - critico:     score_risco=90, 4 tipologias críticas (escala para Opus)

Tabela de saída: distribuição por modelo + custo estimado por execução.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from horizon_blue_one.core.token_router import (
    _AGENTE_TAREFA, _CUSTO_INPUT, _CUSTO_OUTPUT, ModelType, rotear,
)


# Tokens médios estimados por agente (in/out) — baseado em prompts típicos
TOKENS_MEDIOS = {
    "in":  3500,   # prompt + system + dados anonimizados
    "out": 800,    # JSON estruturado de retorno
}


def custo_chamada(modelo: ModelType) -> float:
    return (
        TOKENS_MEDIOS["in"]  * _CUSTO_INPUT[modelo] +
        TOKENS_MEDIOS["out"] * _CUSTO_OUTPUT[modelo]
    ) / 1_000_000


def simular(score: float, tipologias: int, prob_aut: float, label: str) -> None:
    print(f"\n=== Cenário: {label} (score={score}, tipologias_criticas={tipologias}, prob_aut={prob_aut}) ===\n")
    contador: Counter[ModelType] = Counter()
    custo_total = 0.0
    custo_se_tudo_sonnet = 0.0
    detalhes: list[tuple[str, str, str]] = []

    for aid, _tipo in sorted(_AGENTE_TAREFA.items()):
        d = rotear(
            tipo_tarefa=_tipo,
            score_risco=score,
            tipologias_criticas=tipologias,
            probabilidade_autuacao=prob_aut,
            num_notas=100,
            agent_id=aid,
        )
        contador[d.modelo] += 1
        custo_total += custo_chamada(d.modelo)
        custo_se_tudo_sonnet += custo_chamada(ModelType.SONNET)
        flag = ""
        if d.upgrade_aplicado:   flag = " [↑Opus]"
        elif d.downgrade_aplicado: flag = " [↓Haiku]"
        detalhes.append((aid, d.modelo.value.upper(), d.motivo[:50] + flag))

    total = sum(contador.values())
    print(f"  {'Modelo':<8} {'Qtd':>5} {'%':>7} {'Custo/exec (USD)':>20}")
    print("  " + "-"*44)
    for m in (ModelType.HAIKU, ModelType.SONNET, ModelType.OPUS):
        n = contador.get(m, 0)
        custo_m = sum(custo_chamada(m) for _ in range(n))
        print(f"  {m.value.upper():<8} {n:>5} {n/total*100:>6.1f}% {custo_m:>20,.6f}")
    print("  " + "-"*44)
    print(f"  {'TOTAL':<8} {total:>5} {'100.0%':>7} {custo_total:>20,.6f}")
    economia = custo_se_tudo_sonnet - custo_total
    pct = economia / custo_se_tudo_sonnet * 100 if custo_se_tudo_sonnet else 0
    print(f"\n  Custo se TUDO Sonnet:   USD {custo_se_tudo_sonnet:,.6f}")
    print(f"  Economia vs Sonnet:     USD {economia:,.6f}  ({pct:.1f}%)")

    # Detalhes condensados
    print(f"\n  Distribuição agentes:")
    by_modelo: dict[ModelType, list[str]] = {}
    for aid, mod, _ in detalhes:
        m = ModelType(mod.lower())
        by_modelo.setdefault(m, []).append(aid)
    for m in (ModelType.HAIKU, ModelType.SONNET, ModelType.OPUS):
        ag = by_modelo.get(m, [])
        if ag:
            print(f"    {m.value.upper():<8} -> {', '.join(ag)}")


def main() -> None:
    print(f"\n{'='*78}")
    print(f"  SIMULAÇÃO DE MIX 80/15/5 — Horizon-Blue ({len(_AGENTE_TAREFA)} agentes)")
    print(f"{'='*78}")
    print(f"\nTokens médios assumidos: in={TOKENS_MEDIOS['in']}  out={TOKENS_MEDIOS['out']}")
    print(f"Preços Anthropic 2026 (USD/MTok):")
    print(f"  Haiku  IN ${_CUSTO_INPUT[ModelType.HAIKU]:.2f}  OUT ${_CUSTO_OUTPUT[ModelType.HAIKU]:.2f}")
    print(f"  Sonnet IN ${_CUSTO_INPUT[ModelType.SONNET]:.2f}  OUT ${_CUSTO_OUTPUT[ModelType.SONNET]:.2f}")
    print(f"  Opus   IN ${_CUSTO_INPUT[ModelType.OPUS]:.2f}  OUT ${_CUSTO_OUTPUT[ModelType.OPUS]:.2f}")

    simular(score=42, tipologias=0, prob_aut=0.15, label="baseline operação normal")
    simular(score=70, tipologias=1, prob_aut=0.30, label="alerta moderado")
    simular(score=90, tipologias=4, prob_aut=0.85, label="crítico — escalada Opus")


if __name__ == "__main__":
    main()
