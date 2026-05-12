"""
Simula custo do squad Horizon-Blue com 3 alavancas de otimização:

  1. MIX 80/15/5  (Haiku/Sonnet/Opus)
  2. max_tokens calibrado por agente (MAX_TOKENS_OTIMO)
  3. Prompt caching ephemeral (Anthropic):
     - SYSTEM message reusada entre chamadas (-90% no cost dela)
     - cache hit típico: 60% das chamadas

Comparações:
  Baseline:       tudo Sonnet, max_tokens 4096, sem cache
  Mix-only:       80/15/5 + max_tokens 4096 + sem cache
  Mix+tokens:     80/15/5 + max_tokens calibrado
  Full optimized: 80/15/5 + max_tokens + cache 60% hit
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from horizon_blue_one.core.token_router import (
    _AGENTE_TAREFA,
    _CUSTO_INPUT,
    _CUSTO_OUTPUT,
    MAX_TOKENS_OTIMO,
    ModelType,
    max_tokens_para,
    rotear,
)

# ── Estimativas de tokens (rev 2026-05-09 com 5 alavancas ativas) ────────────
# system: prompt fixo cacheável + compressão (instruções enxutas) → 400 tokens
# user_prompt: JSON minified + nomes curtos (n, v, c em vez de notas, valor) → 1500
# output: ~40% do max_tokens (Claude tipicamente concisa)
# cache_hit: 75% em workload contínuo (várias notas mesma estrutura no batch)
SYSTEM_TOKENS = 400
USER_PROMPT_TOKENS = 1500
OUTPUT_RATIO = 0.40
CACHE_HIT_RATE = 0.75
CACHE_DISCOUNT = 0.10   # cache hit custa 10% do preço normal


def custo_chamada(
    modelo: ModelType,
    out_tokens: int,
    system_tokens: int = SYSTEM_TOKENS,
    user_tokens: int = USER_PROMPT_TOKENS,
    cache_hit_rate: float = 0.0,
) -> float:
    """Calcula custo levando em conta cache do system."""
    sys_cost = system_tokens * _CUSTO_INPUT[modelo] / 1_000_000
    sys_cost_avg = (
        sys_cost * (1 - cache_hit_rate)
        + sys_cost * CACHE_DISCOUNT * cache_hit_rate
    )
    user_cost = user_tokens * _CUSTO_INPUT[modelo] / 1_000_000
    out_cost = out_tokens * _CUSTO_OUTPUT[modelo] / 1_000_000
    return sys_cost_avg + user_cost + out_cost


def simular(
    label: str,
    score: float = 42, tipologias: int = 0, prob_aut: float = 0.15,
    use_mix: bool = True,
    use_max_tokens_otimo: bool = True,
    use_cache: bool = True,
) -> tuple[float, float, dict]:
    """Retorna (custo_total, custo_baseline_sonnet, contador_modelos)."""
    contador: Counter[ModelType] = Counter()
    custo_total = 0.0
    custo_baseline = 0.0

    cache_hit = CACHE_HIT_RATE if use_cache else 0.0

    for aid, tipo in sorted(_AGENTE_TAREFA.items()):
        d = rotear(
            tipo_tarefa=tipo,
            score_risco=score,
            tipologias_criticas=tipologias,
            probabilidade_autuacao=prob_aut,
            num_notas=100,
            agent_id=aid,
        )
        modelo = d.modelo if use_mix else ModelType.SONNET
        out_tokens = (
            int(max_tokens_para(aid) * OUTPUT_RATIO)  # 40% do cap em média
            if use_max_tokens_otimo
            else 800   # padrão antigo
        )
        c = custo_chamada(modelo, out_tokens, cache_hit_rate=cache_hit)
        # Baseline: tudo Sonnet, 800 tokens out, sem cache
        c_base = custo_chamada(ModelType.SONNET, 800, cache_hit_rate=0.0)
        contador[modelo] += 1
        custo_total += c
        custo_baseline += c_base

    economia = (custo_baseline - custo_total) / custo_baseline * 100 if custo_baseline else 0
    print(f"\n=== {label} ===")
    total = sum(contador.values())
    for m in (ModelType.HAIKU, ModelType.SONNET, ModelType.OPUS):
        n = contador.get(m, 0)
        if n:
            print(f"  {m.value.upper():<8} {n:>3} agentes ({n/total*100:>5.1f}%)")
    print(f"  Custo total:        USD {custo_total:>8.4f}")
    print(f"  Baseline (Sonnet):  USD {custo_baseline:>8.4f}")
    print(f"  Economia:           {economia:>5.1f}% {'-' * int(max(0, economia/2))}")
    return custo_total, custo_baseline, contador


def main() -> None:
    print(f"\n{'='*78}")
    print("  SIMULAÇÃO ECONOMIA — 3 alavancas (mix · max_tokens · cache)")
    print(f"{'='*78}")
    print("\nPremissas:")
    print(f"  System tokens (cacheable): {SYSTEM_TOKENS}")
    print(f"  User prompt tokens:        {USER_PROMPT_TOKENS}")
    print(f"  Cache hit rate (típico):   {CACHE_HIT_RATE*100:.0f}%")
    print(f"  Cache hit discount:        {(1-CACHE_DISCOUNT)*100:.0f}%")
    print("  Output médio:              50% do max_tokens calibrado")

    # 4 cenários, mesmo perfil de score (baseline)
    print("\n--- BASELINE (score=42, sem otimizações) ---")
    simular("[0] Tudo Sonnet, max_tokens=800, sem cache",
            use_mix=False, use_max_tokens_otimo=False, use_cache=False)

    print("\n--- ALAVANCAS PROGRESSIVAS ---")
    simular("[1] +Mix 80/15/5",
            use_mix=True, use_max_tokens_otimo=False, use_cache=False)
    simular("[2] +Mix +max_tokens calibrado",
            use_mix=True, use_max_tokens_otimo=True, use_cache=False)
    custo_full, base_full, _ = simular(
            "[3] +Mix +max_tokens +cache (FULL)",
            use_mix=True, use_max_tokens_otimo=True, use_cache=True)

    print("\n--- CENÁRIO CRÍTICO (score=90, 4 tipologias) ---")
    simular("[4] FULL otimizado em score crítico",
            score=90, tipologias=4, prob_aut=0.85,
            use_mix=True, use_max_tokens_otimo=True, use_cache=True)

    # Detalhe do max_tokens por agente
    print("\n--- Calibração max_tokens por agente ---")
    by_size: dict[int, list[str]] = {}
    for aid, mt in sorted(MAX_TOKENS_OTIMO.items()):
        by_size.setdefault(mt, []).append(aid)
    for size in sorted(by_size):
        agentes = ", ".join(by_size[size])
        print(f"  {size:>5} tokens: {agentes}")

    print(f"\n  >> META -50% atingida no cenário [3]: {(1 - custo_full/base_full)*100:.1f}%")


if __name__ == "__main__":
    main()
