"""
Analise consolidada NFE-Gado 2026 — extracao + classificacao final
combinando POSICAO (DEST/REM) com NATUREZA (VENDA/REMESSA/TRANSFERENCIA).

Categorias finais (perspectiva do produtor):
  COMPRA         = DEST + VENDA          (RE-1: NFA-e rural, dest. = produtor)
  VENDA          = REM  + VENDA          (saida de gado)
  REMESSA        = REM ou DEST + REMESSA (movimentacao sem mudanca de propriedade)
  TRANSFERENCIA  = REM ou DEST + TRANSFERENCIA (entre estabelecimentos do mesmo titular)
  OUTRAS         = qualquer outra
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nfa_extractor.domain.extractor import extrair_notas


def posicao_e_produtor(arquivo: str) -> tuple[str, str]:
    """Extrai (posicao, nome_produtor) do nome do arquivo 'NOME DEST.pdf'."""
    base = arquivo.upper().replace(".PDF", "").strip()
    if base.endswith(" DEST"):
        return "DESTINATARIO", base[:-5].strip()
    if base.endswith(" REM"):
        return "REMETENTE", base[:-4].strip()
    return "DESCONHECIDO", base


def categorizar(posicao: str, natureza: str) -> str:
    """Aplica RE-1 e mapeamento POSICAO+NATUREZA -> categoria final."""
    nat = (natureza or "OUTRAS").upper()
    if nat == "VENDA":
        return "COMPRA" if posicao == "DESTINATARIO" else "VENDA"
    if nat == "REMESSA":
        return "REMESSA"
    if nat == "TRANSFERENCIA":
        return "TRANSFERENCIA"
    return "OUTRAS"


def fmt_brl(v: float) -> str:
    return f"R$ {v:>16,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main(pasta: Path) -> None:
    pdfs = sorted(pasta.glob("*.pdf"))
    print(f"\n=== ANALISE NFE-Gado 2026 — {len(pdfs)} PDFs ===\n")

    # produtor -> categoria -> {notas, cabecas, valor}
    por_produtor: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"notas": 0, "cabecas": 0.0, "valor": 0.0})
    )
    pdfs_vazios: list[str] = []
    erros: list[dict] = []

    t0 = time.time()
    for pdf in pdfs:
        posicao, produtor = posicao_e_produtor(pdf.name)
        try:
            notas, _, _ = extrair_notas(str(pdf))
            if not notas:
                pdfs_vazios.append(pdf.name)
                continue
            for n in notas:
                cat = categorizar(posicao, n.natureza)
                slot = por_produtor[produtor][cat]
                slot["notas"] += 1
                slot["cabecas"] += float(n.quantidade_total)
                slot["valor"] += float(n.valor_total)
        except Exception as e:
            erros.append({"arquivo": pdf.name, "erro": str(e)[:120]})

    elapsed = time.time() - t0

    # === Tabela por produtor ===
    cats = ["VENDA", "COMPRA", "REMESSA", "TRANSFERENCIA", "OUTRAS"]
    header = f"{'PRODUTOR':<18} | " + " | ".join(f"{c:>13}" for c in cats) + f" | {'TOTAL_VALOR':>16}"
    print(header)
    print("-" * len(header))

    consolidado: dict[str, dict] = {c: {"notas": 0, "cabecas": 0.0, "valor": 0.0} for c in cats}
    for produtor in sorted(por_produtor):
        linhas_valor = []
        total_pr = 0.0
        for c in cats:
            v = por_produtor[produtor][c]["valor"]
            total_pr += v
            consolidado[c]["notas"]   += por_produtor[produtor][c]["notas"]
            consolidado[c]["cabecas"] += por_produtor[produtor][c]["cabecas"]
            consolidado[c]["valor"]   += v
            linhas_valor.append(f"{v:>13,.0f}")
        print(f"{produtor:<18} | " + " | ".join(linhas_valor) + f" | {total_pr:>16,.2f}")

    print("-" * len(header))
    consolidado_linhas = [f"{consolidado[c]['valor']:>13,.0f}" for c in cats]
    total_geral = sum(consolidado[c]["valor"] for c in cats)
    print(f"{'TOTAL':<18} | " + " | ".join(consolidado_linhas) + f" | {total_geral:>16,.2f}")

    # === Resumo agregado ===
    print(f"\n=== RESUMO CONSOLIDADO ({len(por_produtor)} produtores · {elapsed:.1f}s) ===\n")
    print(f"{'CATEGORIA':<16} {'NOTAS':>8} {'CABECAS':>14} {'VALOR (R$)':>22}")
    print("-" * 64)
    total_notas = total_cabecas = total_valor = 0
    for c in cats:
        a = consolidado[c]
        total_notas += a["notas"]
        total_cabecas += a["cabecas"]
        total_valor += a["valor"]
        print(f"{c:<16} {a['notas']:>8} {a['cabecas']:>14,.1f} {a['valor']:>22,.2f}")
    print("-" * 64)
    print(f"{'TOTAL':<16} {total_notas:>8} {total_cabecas:>14,.1f} {total_valor:>22,.2f}")

    # === Saldo fiscal rural ===
    receita = consolidado["VENDA"]["valor"]
    despesa = consolidado["COMPRA"]["valor"]
    print(f"\n=== SALDO FISCAL RURAL (perspectiva produtor) ===")
    print(f"  Receita (VENDA)              {fmt_brl(receita)}")
    print(f"  Despesa (COMPRA, via RE-1)   {fmt_brl(despesa)}")
    print(f"  Resultado bruto              {fmt_brl(receita - despesa)}")
    print(f"  REMESSA (sem efeito IRPF)    {fmt_brl(consolidado['REMESSA']['valor'])}")
    print(f"  TRANSFERENCIA (sem efeito)   {fmt_brl(consolidado['TRANSFERENCIA']['valor'])}")

    # === Diagnostico de qualidade ===
    print(f"\n=== DIAGNOSTICO DE QUALIDADE ===")
    print(f"  PDFs processados:        {len(pdfs)}")
    print(f"  PDFs com extracao OK:    {len(pdfs) - len(pdfs_vazios) - len(erros)}")
    print(f"  PDFs vazios (0 notas):   {len(pdfs_vazios)}")
    if pdfs_vazios:
        for p in pdfs_vazios:
            print(f"     - {p}")
    print(f"  PDFs com erro:           {len(erros)}")

    # === Saida JSON ===
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"analise_nfe_gado_{int(time.time())}.json"
    out_file.write_text(
        json.dumps({
            "tempo_s": round(elapsed, 2),
            "consolidado": consolidado,
            "por_produtor": {p: dict(c) for p, c in por_produtor.items()},
            "pdfs_vazios": pdfs_vazios,
            "erros": erros,
            "saldo_fiscal": {
                "receita_venda": receita,
                "despesa_compra": despesa,
                "resultado_bruto": receita - despesa,
            },
        }, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n>> JSON: {out_file}")


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pasta or not pasta.exists():
        print("ERRO: passe a pasta com PDFs como argumento")
        sys.exit(1)
    main(pasta)
