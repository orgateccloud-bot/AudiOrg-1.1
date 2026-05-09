"""
Simulação de Consumo Real de Tokens — Auditoria NFE-Gado 2026.

Roda o squad Horizon-Blue contra os 32 PDFs (32 individual + 16 consolidado)
em modo MOCK (zero custo Claude), medindo tokens reais a partir do prompt
construído por cada agente. Compara com ground-truth (RESULTADOS_AUDITORIA.zip).

Uso:
    python scripts/simulacao_consumo_real.py
    python scripts/simulacao_consumo_real.py --pipeline auditor --limit 3
    python scripts/simulacao_consumo_real.py --pipeline full --limit 5
    python scripts/simulacao_consumo_real.py --ground-truth caminho/zip
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.simulacao.pipeline import (
    PIPELINE_AUDITOR, PIPELINE_FULL,
    extrair_e_classificar, posicao_e_produtor, rodar_squad,
)
from scripts.simulacao.ground_truth import comparar as gt_comparar
from scripts.simulacao.relatorio import (
    agregar_por_agente, comparativo_economia,
    gerar_markdown, salvar_json,
)


def _achar_pasta_nfe() -> Path:
    """Tenta locais comuns onde a pasta NFE_GADO_2026 pode estar."""
    candidatos = [
        Path(r"C:\Users\Veloso\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026"),
        Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026"),
    ]
    for c in candidatos:
        if c.exists():
            return c
    return candidatos[0]  # default mesmo que não exista (erro descritivo depois)


def _achar_zip_gt() -> Path:
    candidatos = [
        Path(r"C:\Users\Veloso\NFE_GADO_2026\RESULTADOS_AUDITORIA.zip"),
        Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\RESULTADOS_AUDITORIA.zip"),
    ]
    for c in candidatos:
        if c.exists():
            return c
    return candidatos[0]


PASTA_DEFAULT = _achar_pasta_nfe()
GT_DEFAULT = _achar_zip_gt()


async def simular_pdf(
    pdf_path: Path, pipeline: list[str], modo: str
) -> dict:
    """Simula 1 PDF: extrai, roda squad, devolve dict completo."""
    t0 = time.time()
    try:
        notas, posicao, produtor = extrair_e_classificar(pdf_path)
    except Exception as exc:
        return {
            "pdf":      pdf_path.name,
            "produtor": "?", "papel": "?", "n_notas": 0,
            "valor_total": 0.0, "status": "ERRO",
            "duracao_s": round(time.time() - t0, 2),
            "erro":      f"{type(exc).__name__}: {str(exc)[:160]}",
            "chamadas": [], "totais": {},
        }

    if not notas:
        return {
            "pdf":      pdf_path.name,
            "produtor": produtor, "papel": posicao, "n_notas": 0,
            "valor_total": 0.0, "status": "VAZIO",
            "duracao_s": round(time.time() - t0, 2),
            "chamadas": [], "totais": {
                "tokens_in": 0, "tokens_out": 0, "custo_usd": 0.0,
                "custo_baseline_sonnet": 0.0, "economia_pct": 0.0,
            },
        }

    valor_total = sum(float(n.get("valor_total", 0)) for n in notas)
    contrib = {
        "nome":      f"{produtor} ({posicao})",
        "cpf_cnpj":  "00000000000",
        "regime":    "PF Rural",
        "uf":        "GO",
        "atividade": "bovino",
    }
    res = await rodar_squad(notas, pipeline, score=42.0, contribuinte=contrib, modo=modo)
    return {
        "pdf":         pdf_path.name,
        "produtor":    produtor,
        "papel":       posicao,
        "n_notas":     len(notas),
        "valor_total": round(valor_total, 2),
        "status":      "OK",
        "duracao_s":   round(time.time() - t0, 2),
        "chamadas":    res["chamadas"],
        "totais":      res["totais"],
        "resultados":  res["resultados"],
    }


async def simular_consolidado(
    produtor: str, pdfs: list[Path], pipeline: list[str], modo: str
) -> dict:
    """Simula 1 produtor: junta DEST + REM, roda squad uma vez."""
    t0 = time.time()
    todas_notas: list[dict] = []
    pdfs_origem: list[str] = []
    for pdf in pdfs:
        try:
            notas, _, _ = extrair_e_classificar(pdf)
            todas_notas.extend(notas)
            pdfs_origem.append(pdf.name)
        except Exception:
            continue

    if not todas_notas:
        return {
            "produtor":    produtor,
            "pdfs_origem": [p.name for p in pdfs],
            "n_notas":     0, "valor_total": 0.0,
            "status":      "VAZIO",
            "duracao_s":   round(time.time() - t0, 2),
            "chamadas":    [], "totais": {},
        }

    valor_total = sum(float(n.get("valor_total", 0)) for n in todas_notas)
    contrib = {
        "nome":      produtor, "cpf_cnpj": "00000000000",
        "regime":    "PF Rural", "uf": "GO", "atividade": "bovino",
    }
    res = await rodar_squad(todas_notas, pipeline, score=42.0, contribuinte=contrib, modo=modo)
    return {
        "produtor":    produtor,
        "pdfs_origem": pdfs_origem,
        "n_notas":     len(todas_notas),
        "valor_total": round(valor_total, 2),
        "status":      "OK",
        "duracao_s":   round(time.time() - t0, 2),
        "chamadas":    res["chamadas"],
        "totais":      res["totais"],
        "resultados":  res["resultados"],
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", choices=["auditor", "full"], default="auditor")
    parser.add_argument("--ground-truth", type=Path, default=GT_DEFAULT)
    parser.add_argument("--limit", type=int, default=0,
                        help="0 = todos. >0 = limita a N PDFs.")
    parser.add_argument("--modo", choices=["mock", "real"], default="mock")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pasta", type=Path, default=PASTA_DEFAULT)
    args = parser.parse_args()

    pipeline = PIPELINE_AUDITOR if args.pipeline == "auditor" else PIPELINE_FULL
    pasta = args.pasta
    if not pasta.exists():
        print(f"ERRO: pasta {pasta} não existe.")
        return 2

    # Out dir
    ts = int(time.time())
    out_dir = args.out or (ROOT / "out" / f"simulacao_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pasta.glob("*.pdf"))
    if args.limit > 0:
        pdfs = pdfs[: args.limit]

    print(f"\n{'='*78}")
    print(f"  SIMULAÇÃO NFE-Gado 2026 — pipeline={args.pipeline} ({len(pipeline)} agentes)")
    print(f"  Modo: {args.modo} | PDFs: {len(pdfs)} | Out: {out_dir}")
    print(f"{'='*78}\n")

    # ── Etapa A: 32 individual ──────────────────────────────────────────────
    print(f"[A/3] Análise individual ({len(pdfs)} PDFs)...")
    individual: list[dict] = []
    for i, pdf in enumerate(pdfs, 1):
        r = await simular_pdf(pdf, pipeline, args.modo)
        individual.append(r)
        status = r["status"]
        custo = r.get("totais", {}).get("custo_usd", 0)
        print(f"  [{i:>2}/{len(pdfs)}] {pdf.name:<32} "
              f"{status:<6} {r['n_notas']:>4} notas  USD {custo:>7.4f}  "
              f"({r['duracao_s']:.1f}s)")

    # ── Etapa B: 16 consolidado por produtor ────────────────────────────────
    print(f"\n[B/3] Análise consolidada por produtor...")
    por_produtor: dict[str, list[Path]] = defaultdict(list)
    for pdf in pdfs:
        _, produtor = posicao_e_produtor(pdf.name)
        por_produtor[produtor].append(pdf)

    consolidado: list[dict] = []
    for i, (produtor, pdfs_prod) in enumerate(sorted(por_produtor.items()), 1):
        r = await simular_consolidado(produtor, pdfs_prod, pipeline, args.modo)
        consolidado.append(r)
        custo = r.get("totais", {}).get("custo_usd", 0)
        print(f"  [{i:>2}/{len(por_produtor)}] {produtor:<14} "
              f"{r['status']:<6} {r['n_notas']:>4} notas  USD {custo:>7.4f}  "
              f"({r['duracao_s']:.1f}s)")

    # ── Etapa C: ground-truth ───────────────────────────────────────────────
    print(f"\n[C/3] Ground-truth (RESULTADOS_AUDITORIA.zip)...")
    gt_match: dict = {}
    if args.ground_truth.exists():
        try:
            gt_match = gt_comparar(consolidado, args.ground_truth)
            sims = [m["similaridade"] for m in gt_match.values()
                    if m.get("tem_gt") and "similaridade" in m]
            if sims:
                print(f"  Similaridade média: {sum(sims)/len(sims):.2%} "
                      f"({len(sims)}/{len(gt_match)} produtores)")
        except Exception as exc:
            print(f"  ! Erro processando ground-truth: {exc}")
    else:
        print(f"  ! ZIP não encontrado: {args.ground_truth}")

    # ── Outputs ─────────────────────────────────────────────────────────────
    print(f"\n[3/3] Gerando outputs em {out_dir}...")
    salvar_json(out_dir / "consumo_individual.json", individual)
    salvar_json(out_dir / "consumo_consolidado.json", consolidado)

    todas = individual + consolidado
    por_agente = agregar_por_agente(todas)
    salvar_json(out_dir / "consumo_por_agente.json", por_agente)

    economia = comparativo_economia(todas)
    salvar_json(out_dir / "comparativo_economia.json", economia)

    if gt_match:
        salvar_json(out_dir / "ground_truth_match.json", gt_match)

    pdfs_vazios = [s["pdf"] for s in individual if s["status"] == "VAZIO"]
    md = gerar_markdown(
        out_dir, individual, consolidado, por_agente, economia, gt_match,
        pdfs_vazios, args.pipeline, len(pdfs),
    )

    print(f"\n  Custo total atual:   USD {economia['atual_usd']:.4f}")
    print(f"  Baseline (Sonnet):   USD {economia['baseline_sonnet_usd']:.4f}")
    print(f"  Economia:            {economia['economia_pct']:.1f}%")
    print(f"  Mix Haiku/Sonnet/Opus: "
          f"{economia['distribuicao_modelos']['haiku']}/"
          f"{economia['distribuicao_modelos']['sonnet']}/"
          f"{economia['distribuicao_modelos']['opus']}%")
    print(f"\n  >> Relatório: {md}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
