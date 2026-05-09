"""Simulação determinística do pf-gate sobre o lote real (22 produtores).

Não chama LLM — só roda precalc e bucketa por probabilidade_autuacao para
projetar quanto o pf-gate cortaria do pipeline S1..S7.

Uso:
    python -m horizon_blue_one.tests.test_pf_gate_simulacao
"""
from __future__ import annotations

import asyncio
import time
import unicodedata
from pathlib import Path

PASTA_PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


async def main():
    from horizon_blue_one.core.limiares import (
        PF_GATE_AMPLO,
        PF_GATE_ARQUIVA,
        PF_GATE_REDUZIDO,
    )
    from horizon_blue_one.core.precalc import precalcular
    from horizon_blue_one.nfa_bridge import (
        agrupar_pdfs_por_produtor,
        processar_produtor,
    )

    print(f"\n{'='*78}")
    print("SIMULACAO pf-gate -- Lote real (22 produtores)")
    print(f"  Limiares: arquiva<{PF_GATE_ARQUIVA:.0%} | reduzido<{PF_GATE_REDUZIDO:.0%} | amplo<{PF_GATE_AMPLO:.0%}")
    print(f"{'='*78}\n")

    grupos = agrupar_pdfs_por_produtor(PASTA_PDFS)
    t0 = time.time()
    linhas = []

    for produtor, pdfs in grupos.items():
        payload = processar_produtor(produtor, pdfs, atividade="bovino")
        if not payload:
            continue
        payload = await precalcular(payload)
        pre = payload.get("__precalc__", {})
        xgb = pre.get("xgboost", {})

        score = float(xgb.get("score", 0))
        pf = float(xgb.get("probabilidade_autuacao", 0) or 0)
        n_notas = len(payload.get("notas", []))

        if pf < PF_GATE_ARQUIVA:
            bucket, n_calls = "ARQUIVA", 0
        elif pf < PF_GATE_REDUZIDO:
            bucket, n_calls = "REDUZIDO", 3   # S3+S5+S7
        elif pf < PF_GATE_AMPLO:
            bucket, n_calls = "AMPLO", 5      # S1+S2+S3+S5+S7
        else:
            bucket, n_calls = "FULL", 7       # S1..S7

        linhas.append({
            "produtor": _ascii(produtor),
            "pf": pf, "score": score, "n_notas": n_notas,
            "bucket": bucket, "n_calls": n_calls,
        })

    t_ms = (time.time() - t0) * 1000

    # ── Tabela ────────────────────────────────────────────────────────────────
    print(f"{'PRODUTOR':<22} {'NOTAS':>6} {'SCORE':>6} {'PF':>7} {'BUCKET':<10} {'CALLS':>5}")
    print("-" * 78)
    for L in sorted(linhas, key=lambda x: -x["pf"]):
        print(f"{L['produtor']:<22} {L['n_notas']:>6} {L['score']:>6.1f} "
              f"{L['pf']*100:>6.1f}% {L['bucket']:<10} {L['n_calls']:>5}")

    # ── Resumo por bucket ─────────────────────────────────────────────────────
    print("\n" + "-" * 78)
    by_bucket: dict[str, list] = {}
    for L in linhas:
        by_bucket.setdefault(L["bucket"], []).append(L)

    total_calls_atual = len(linhas) * 7   # baseline: todos rodam S1..S7
    total_calls_gate  = sum(L["n_calls"] for L in linhas)

    print("RESUMO POR BUCKET:")
    for b in ("ARQUIVA", "REDUZIDO", "AMPLO", "FULL"):
        L = by_bucket.get(b, [])
        n = len(L)
        c = sum(x["n_calls"] for x in L)
        pct = n / max(1, len(linhas)) * 100
        print(f"  {b:<10} {n:>3} produtores ({pct:>5.1f}%)  -> {c:>3} chamadas LLM")

    print("-" * 78)
    print(f"Chamadas LLM (atual S1..S7):   {total_calls_atual:>4}")
    print(f"Chamadas LLM (com pf-gate):    {total_calls_gate:>4}")
    economia_calls = (1 - total_calls_gate / max(1, total_calls_atual)) * 100
    print(f"Reducao de chamadas:            {economia_calls:>5.1f}%")

    # Custo aproximado por chamada (mix-alvo 80/15/5):
    #   80% Haiku  ~$0.005
    #   15% Sonnet ~$0.020
    #    5% Opus   ~$0.100
    custo_medio_call = 0.80 * 0.005 + 0.15 * 0.020 + 0.05 * 0.100
    custo_atual = total_calls_atual * custo_medio_call
    custo_gate  = total_calls_gate  * custo_medio_call
    print(f"Custo estimado (atual):        ${custo_atual:.3f}")
    print(f"Custo estimado (com gate):     ${custo_gate:.3f}")
    print(f"Economia:                      ${custo_atual - custo_gate:.3f}")
    print("-" * 78)
    print(f"Tempo simulacao: {t_ms/1000:.1f}s ({len(linhas)} produtores)")


if __name__ == "__main__":
    asyncio.run(main())
