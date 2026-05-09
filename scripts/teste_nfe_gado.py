"""
Teste de extração de NFE-Gado 2026 — roda o extrator determinístico
em todos os PDFs de uma pasta e gera um relatório consolidado.

Uso:
    python scripts/teste_nfe_gado.py "C:\\Users\\Veloso\\NFE_GADO_2026\\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026"

Saída:
    - resumo no stdout (1 linha por PDF + agregado)
    - JSON detalhado em out/teste_nfe_gado_<timestamp>.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nfa_extractor.domain.extractor import extrair_notas, resumo_geral


def processar_pasta(pasta: Path) -> dict:
    pdfs = sorted(pasta.glob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF em {pasta}")
        return {}

    print(f"\n=== TESTE NFE-Gado 2026 — {len(pdfs)} PDFs ===\n")
    print(f"{'#':<3} {'arquivo':<35} {'notas':>5} {'venda':>3} {'remessa':>7} {'outras':>6} {'tempo':>7}")
    print("-" * 80)

    total_inicio = time.time()
    todos_resultados: list[dict] = []
    todas_notas: list = []
    erros: list[dict] = []

    for i, pdf in enumerate(pdfs, 1):
        t0 = time.time()
        try:
            notas, contribuinte, _ = extrair_notas(str(pdf))
            todas_notas.extend(notas)
            naturezas = {"VENDA": 0, "REMESSA": 0, "OUTRAS": 0}
            for n in notas:
                naturezas[n.natureza] = naturezas.get(n.natureza, 0) + 1

            valor_total_pdf = sum(n.valor_total for n in notas)
            qtd_total_pdf = sum(n.quantidade_total for n in notas)

            resultado = {
                "arquivo": pdf.name,
                "contribuinte": contribuinte,
                "qtd_notas": len(notas),
                "naturezas": naturezas,
                "valor_total": round(valor_total_pdf, 2),
                "quantidade_total": round(qtd_total_pdf, 2),
                "tempo_s": round(time.time() - t0, 3),
            }
            todos_resultados.append(resultado)
            print(
                f"{i:<3} {pdf.name:<35} "
                f"{len(notas):>5} {naturezas.get('VENDA', 0):>3} "
                f"{naturezas.get('REMESSA', 0):>7} {naturezas.get('OUTRAS', 0):>6} "
                f"{resultado['tempo_s']:>6.2f}s"
            )
        except Exception as e:
            erros.append({"arquivo": pdf.name, "erro": str(e)[:100]})
            print(f"{i:<3} {pdf.name:<35} ERRO: {str(e)[:50]}")

    tempo_total = time.time() - total_inicio
    print("-" * 80)
    print(
        f"TOTAIS: {len(pdfs)} PDFs · {len(todas_notas)} notas extraidas · "
        f"erros: {len(erros)} · tempo total: {tempo_total:.1f}s"
    )

    # Resumo agregado
    if todas_notas:
        resumo = resumo_geral(todas_notas, "Consolidado NFE-Gado 2026")
        print(f"\n=== AGREGADO ===")
        for k, v in resumo.items():
            if isinstance(v, (int, float)):
                if "valor" in k.lower() or "icms" in k.lower():
                    print(f"  {k:<30} R$ {v:>15,.2f}")
                else:
                    print(f"  {k:<30}    {v:>15,.2f}" if isinstance(v, float) else f"  {k:<30}    {v:>15}")
            elif isinstance(v, dict):
                print(f"  {k}:")
                for kk, vv in v.items():
                    print(f"    {kk:<28}    {vv}")

    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"teste_nfe_gado_{int(time.time())}.json"
    out_file.write_text(
        json.dumps(
            {
                "pasta": str(pasta),
                "tempo_total_s": round(tempo_total, 3),
                "resultados_por_pdf": todos_resultados,
                "erros": erros,
                "agregado": resumo if todas_notas else None,
            },
            ensure_ascii=False, indent=2, default=str
        ),
        encoding="utf-8",
    )
    print(f"\n>> JSON detalhado: {out_file}")

    return {
        "total_pdfs": len(pdfs),
        "total_notas": len(todas_notas),
        "erros": len(erros),
        "tempo_s": tempo_total,
    }


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pasta or not pasta.exists():
        print("ERRO: passe a pasta com PDFs como argumento")
        sys.exit(1)
    processar_pasta(pasta)
