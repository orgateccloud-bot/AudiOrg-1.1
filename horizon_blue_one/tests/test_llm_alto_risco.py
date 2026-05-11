"""Roda agentes LLM S1..S7 sobre produtores ALTO risco identificados pelo precalc.

Uso:
    python -m horizon_blue_one.tests.test_llm_alto_risco

Saida:
    - Console: resumo por produtor + por agente (status/confidence)
    - JSON: reports_nfa/llm_alto_risco_<timestamp>.json
"""
from __future__ import annotations

import asyncio
import json
import time
import unicodedata
from pathlib import Path

PASTA_PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")
PRODUTORES_ALTO_RISCO = ["GERALDO", "FABIO", "ETERVALDO", "CLEITON", "RAUL", "ADELA"]
DESTINO_RELATORIO = Path("reports_nfa")


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


async def auditar_produtor(nome: str, pdfs, orch) -> dict:
    """Executa pipeline LLM completo S1..S7 para um produtor."""
    from horizon_blue_one.core.precalc import precalcular
    from horizon_blue_one.nfa_bridge import processar_produtor

    t0 = time.time()
    payload = processar_produtor(nome, pdfs, atividade="bovino")
    if not payload:
        return {"produtor": nome, "erro": "sem notas extraidas"}

    # Pre-calcula UMA vez aqui — memo cache TTL 5min evita recomputo no orchestrator
    payload = await precalcular(payload)
    pre = payload.get("__precalc__", {})

    resultados = await orch.executar_pipeline(
        payload,
        agentes=["S1", "S2", "S3", "S4", "S5", "S6", "S7"],
        chamar_ceo_no_fim=True,
        paralelo=True,
        early_exit=False,            # forcar LLM mesmo em casos limpos
        max_tokens_orcamento=80_000,
    )
    ms = (time.time() - t0) * 1000
    resumo = {
        "produtor":      nome,
        "latencia_ms":   round(ms),
        "n_notas":       len(payload.get("notas", [])),
        "score_precalc": pre.get("xgboost", {}).get("score"),
        "agentes":       {},
    }
    for aid, r in resultados.items():
        out = r.output if isinstance(r.output, dict) else {"raw": str(r.output)}
        resumo["agentes"][aid] = {
            "status":     r.status,
            "confidence": round(r.confidence, 2),
            "destaque":   out.get("resumo") or out.get("conclusao") or out.get("motivo")
                          or list(out.keys())[:5],
        }
    return resumo


async def main():
    from horizon_blue_one.core.orchestrator import Orchestrator
    from horizon_blue_one.nfa_bridge import agrupar_pdfs_por_produtor

    print(f"\n{'='*78}")
    print("AUDITORIA LLM (S1..S7) -- Produtores ALTO risco")
    print(f"{'='*78}\n")

    grupos = agrupar_pdfs_por_produtor(PASTA_PDFS)
    selecionados = {n: grupos[n] for n in PRODUTORES_ALTO_RISCO if n in grupos}
    print(f"Produtores selecionados: {list(selecionados.keys())}\n")

    orch = Orchestrator()
    relatorios: list[dict] = []
    t_total = time.time()

    for nome, pdfs in selecionados.items():
        print(f"[RUN] {nome}...", flush=True)
        try:
            resumo = await auditar_produtor(nome, pdfs, orch)
        except Exception as exc:
            print(f"  [ERR] {nome}: {exc}")
            relatorios.append({"produtor": nome, "erro": str(exc)})
            continue
        relatorios.append(resumo)

        print(f"  Notas={resumo['n_notas']} score_precalc={resumo['score_precalc']} "
              f"latencia={resumo['latencia_ms']}ms")
        for aid, info in resumo["agentes"].items():
            destaque = info["destaque"]
            if isinstance(destaque, list):
                destaque = ",".join(destaque)
            destaque = _ascii(str(destaque))[:80]
            print(f"    {aid:<14} {info['status']:<10} conf={info['confidence']:<5} {destaque}")
        print()

    t_ms = (time.time() - t_total) * 1000
    print(f"{'-'*78}")
    print(f"Total: {len(relatorios)} produtores em {t_ms/1000:.1f}s")
    print(f"{'-'*78}\n")

    DESTINO_RELATORIO.mkdir(parents=True, exist_ok=True)
    arquivo = DESTINO_RELATORIO / f"llm_alto_risco_{int(time.time())}.json"
    arquivo.write_text(json.dumps(relatorios, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Relatorio salvo: {arquivo}")
    return relatorios


if __name__ == "__main__":
    asyncio.run(main())
