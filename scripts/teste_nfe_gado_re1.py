"""
Teste de NFE-Gado 2026 com RE-1 aplicada (VENDA -> COMPRA quando DEST + rural).

Identifica posicao a partir do nome do arquivo:
    *_DEST.pdf  -> produtor e DESTINATARIO  -> elegivel RE-1 (VENDA vira COMPRA)
    *_REM.pdf   -> produtor e REMETENTE     -> VENDA normal
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nfa_extractor.domain.extractor import extrair_notas
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1


def posicao_do_arquivo(nome: str) -> str:
    """DEST -> DESTINATARIO | REM -> REMETENTE."""
    s = nome.upper()
    if " DEST" in s or s.endswith(" DEST.PDF") or "DEST.PDF" in s:
        return "DESTINATARIO"
    if " REM" in s or s.endswith(" REM.PDF") or "REM.PDF" in s:
        return "REMETENTE"
    return "DESCONHECIDO"


def main(pasta: Path) -> None:
    pdfs = sorted(pasta.glob("*.pdf"))
    print(f"\n=== TESTE NFE-Gado 2026 + RE-1 — {len(pdfs)} PDFs ===\n")

    todas_notas_dict: list[dict] = []
    erros: list[str] = []

    t0 = time.time()
    for pdf in pdfs:
        posicao = posicao_do_arquivo(pdf.name)
        try:
            notas, contribuinte, _ = extrair_notas(str(pdf))
            for n in notas:
                d = n.model_dump()
                d["posicao"] = posicao
                d["atividade"] = "bovino"          # contexto: NFE-Gado
                d["tipo_doc"]  = "nfa-e"
                d["pdf_origem"] = pdf.name
                d["contribuinte"] = contribuinte
                todas_notas_dict.append(d)
        except Exception as e:
            erros.append(f"{pdf.name}: {e}")

    # Aplica RE-1
    classificadas = [aplicar_regra_especial_1(n) for n in todas_notas_dict]

    # Agrega por natureza_exibicao
    agregado: dict[str, dict] = {}
    for n in classificadas:
        cat = n.get("natureza_exibicao", "OUTRAS")
        a = agregado.setdefault(cat, {"notas": 0, "valor": 0.0, "cabecas": 0.0})
        a["notas"] += 1
        a["valor"] += float(n.get("valor_total", 0))
        a["cabecas"] += float(n.get("quantidade_total", 0))

    print(f"Tempo total: {time.time() - t0:.1f}s | {len(classificadas)} notas processadas | erros: {len(erros)}\n")
    print(f"{'natureza_exibicao':<22} {'notas':>6} {'cabecas':>12} {'valor (R$)':>20}")
    print("-" * 65)
    for cat in sorted(agregado, key=lambda c: -agregado[c]["valor"]):
        a = agregado[cat]
        print(f"{cat:<22} {a['notas']:>6} {a['cabecas']:>12,.1f} {a['valor']:>20,.2f}")
    print("-" * 65)
    total_valor = sum(a["valor"] for a in agregado.values())
    total_cab   = sum(a["cabecas"] for a in agregado.values())
    print(f"{'TOTAL':<22} {len(classificadas):>6} {total_cab:>12,.1f} {total_valor:>20,.2f}")

    # Verifica a regra RE-1
    re1_aplicadas = [n for n in classificadas if n.get("regra_aplicada") == "REGRA_ESPECIAL_1"]
    valor_re1 = sum(float(n["valor_total"]) for n in re1_aplicadas)
    print()
    print(f"=== RE-1 (VENDA -> COMPRA rural) ===")
    print(f"  Notas reclassificadas:  {len(re1_aplicadas)}")
    print(f"  Valor reclassificado:   R$ {valor_re1:,.2f}")
    print(f"  Efeito IRPF:            SUBTRAI da receita rural (despesa dedutivel)")
    alertas_500k = [n for n in re1_aplicadas if any("> R$500k" in a for a in n.get("alertas_re1", []))]
    if alertas_500k:
        print(f"  ALERTAS > R$500k:       {len(alertas_500k)} notas (revisao manual obrigatoria)")

    # Top compradores (DESTINATARIO em VENDA reclassificada)
    print()
    print("=== TOP 5 PRODUTORES POR VOLUME DE COMPRA (RE-1) ===")
    por_contrib: dict[str, dict] = {}
    for n in re1_aplicadas:
        c = n.get("contribuinte", "?")
        d = por_contrib.setdefault(c, {"notas": 0, "valor": 0.0, "cabecas": 0.0})
        d["notas"] += 1
        d["valor"] += float(n.get("valor_total", 0))
        d["cabecas"] += float(n.get("quantidade_total", 0))
    top5 = sorted(por_contrib.items(), key=lambda kv: -kv[1]["valor"])[:5]
    for nome, d in top5:
        print(f"  {nome[:40]:<40}  {d['notas']:>4} notas  {d['cabecas']:>8,.0f} cab  R$ {d['valor']:>14,.2f}")

    out = ROOT / "out" / f"teste_re1_{int(time.time())}.json"
    out.write_text(
        json.dumps({
            "agregado": agregado,
            "re1_qtd": len(re1_aplicadas),
            "re1_valor": valor_re1,
            "top_compradores": [{"nome": n, **d} for n, d in top5],
        }, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n>> JSON: {out}")


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pasta or not pasta.exists():
        print("ERRO: passe a pasta com PDFs como argumento")
        sys.exit(1)
    main(pasta)
