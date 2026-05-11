"""Teste real com PDFs de NFa-e (gado 2026) — auditoria POR PRODUTOR.

Pipeline:
  1. Agrupa PDFs por produtor (usando sufixos REM/DEST do nome do arquivo).
  2. Para cada produtor:
        - Extrai notas via D:\\nfa-repo
        - Aplica posicao correta por arquivo origem (NÃO infere por CPF)
        - Aplica heurística CFOP (extrator nao extrai CFOP)
        - Roda precalc determinístico (RE-1 reclassifica VENDA->COMPRA quando
          produtor é DESTINATARIO + atividade rural)
  3. Imprime relatório agregado: tabela produtor x score x detecções.

Uso:
    python -m horizon_blue_one.tests.test_pdf_real
    pytest horizon_blue_one/tests/test_pdf_real.py -v -s
"""
from __future__ import annotations

import asyncio
import time
import unicodedata
from pathlib import Path

PASTA_PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")


def _ascii(s: str) -> str:
    """Remove acentos para output em consoles cp1252."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


async def main():
    from horizon_blue_one.core.orchestrator import Orchestrator
    from horizon_blue_one.core.precalc import precalcular
    from horizon_blue_one.nfa_bridge import (
        agrupar_pdfs_por_produtor,
        processar_produtor,
    )

    print(f"\n{'='*78}")
    print(f"AUDITORIA POR PRODUTOR -- Pasta: {PASTA_PDFS.name}")
    print(f"{'='*78}\n")

    grupos = agrupar_pdfs_por_produtor(PASTA_PDFS)
    print(f"Produtores detectados: {len(grupos)}")
    print(f"PDFs total: {sum(len(v['REMETENTE']) + len(v['DESTINATARIO']) for v in grupos.values())}\n")

    orch = Orchestrator()
    relatorio: list[dict] = []
    t_total = time.time()

    for produtor, pdfs in grupos.items():
        n_rem = len(pdfs["REMETENTE"])
        n_dst = len(pdfs["DESTINATARIO"])
        t0 = time.time()

        payload = processar_produtor(produtor, pdfs, atividade="bovino")
        if not payload:
            print(f"  [SKIP] {produtor:<20} (sem notas extraidas)")
            continue

        payload = await precalcular(payload)
        pre = payload["__precalc__"]
        ms = (time.time() - t0) * 1000

        notas = payload["notas"]
        n_total = len(notas)
        n_re1 = sum(1 for n in pre.get("notas_re1", []) if n.get("regra_aplicada") == "REGRA_ESPECIAL_1")
        score = pre["xgboost"]["score"]
        nivel = pre["xgboost"]["nivel"]
        det = pre["detectores"]
        flags = []
        if det.get("carrossel"):           flags.append("CARR")
        if det.get("smurfing"):            flags.append("SMRF")
        if det.get("devolucao_posterior"): flags.append("DEVL")
        if det.get("anomalia_temporal"):   flags.append("TEMP")
        if det.get("fornecedor_fantasma"): flags.append(f"FANT:{len(det['fornecedor_fantasma'])}")
        lc = pre["lcdpr"]
        cx = pre["caixa"]
        audit_limpa = orch._audit_limpa(pre)

        relatorio.append({
            "produtor":   produtor,
            "rem":        n_rem,
            "dst":        n_dst,
            "notas":      n_total,
            "re1":        n_re1,
            "score":      score,
            "nivel":      nivel,
            "flags":      ",".join(flags) or "-",
            "lcdpr_div":  lc["divergencia"],
            "saldo_cx":   cx["saldo"],
            "audit_ok":   audit_limpa,
            "lat_ms":     ms,
        })

        print(
            f"  [OK] {produtor:<20} "
            f"REM={n_rem:>2} DST={n_dst:>2} "
            f"notas={n_total:>4} RE1={n_re1:>4} "
            f"score={score:>5.1f}({_ascii(nivel):<7}) "
            f"flags={','.join(flags) or '-':<22} "
            f"{'LIMPA' if audit_limpa else 'LLM  '} "
            f"({ms:>5.0f}ms)"
        )

    t_ms = (time.time() - t_total) * 1000
    print(f"\n{'-'*78}")
    print(f"Total: {len(relatorio)} produtores em {t_ms/1000:.1f}s "
          f"(media {t_ms/max(len(relatorio),1):.0f}ms/produtor)")
    print(f"{'-'*78}\n")

    # Agregados
    total_notas       = sum(r["notas"] for r in relatorio)
    total_re1         = sum(r["re1"] for r in relatorio)
    score_medio       = sum(r["score"] for r in relatorio) / max(len(relatorio), 1)
    suspeitos_alto    = [r for r in relatorio if r["score"] >= 60]
    suspeitos_medio   = [r for r in relatorio if 40 <= r["score"] < 60]
    audits_limpas     = sum(1 for r in relatorio if r["audit_ok"])

    print("AGREGADO GLOBAL:")
    print(f"  Notas processadas..: {total_notas}")
    print(f"  Reclassificadas RE1: {total_re1} (VENDA->COMPRA quando DESTINATARIO + bovino)")
    print(f"  Score medio........: {score_medio:.1f}")
    print(f"  Audits limpas......: {audits_limpas}/{len(relatorio)} (early-exit, sem LLM)")
    print(f"  Risco ALTO   (>=60): {len(suspeitos_alto)}")
    print(f"  Risco MEDIO (40-60): {len(suspeitos_medio)}")
    print()

    if suspeitos_alto:
        print("PRODUTORES DE RISCO ALTO:")
        for r in sorted(suspeitos_alto, key=lambda x: -x["score"]):
            print(f"  {r['produtor']:<20} score={r['score']:>5.1f} flags={r['flags']}")
        print()

    return relatorio


if __name__ == "__main__":
    asyncio.run(main())
