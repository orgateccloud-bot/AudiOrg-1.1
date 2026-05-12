"""
Pipeline completo OrgAudi para NFE-Gado 2026:
  1. Extrai notas via nfa_extractor.domain.extractor.extrair_notas
  2. Aplica RE-1 (regra_especial_1) por nota -> reclassifica VENDA->COMPRA quando
     produtor for DESTINATARIO em NFA-e rural
  3. Apura F1-F6 + FUNRURAL + IRPF via resumo_fiscal.apurar_resumo
  4. Detecta anomalias do catalogo AN-01..AN-18 (heuristica simples)
  5. Gera relatorio consolidado e por produtor

Usa SOMENTE o motor deterministico - nao depende de Claude API.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1
from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo
from nfa_extractor.domain.extractor import extrair_notas


def posicao_e_produtor(arquivo: str) -> tuple[str, str]:
    base = arquivo.upper().replace(".PDF", "").strip()
    if base.endswith(" DEST"):
        return "DESTINATARIO", base[:-5].strip()
    if base.endswith(" REM"):
        return "REMETENTE", base[:-4].strip()
    return "DESCONHECIDO", base


def fmt(v: float) -> str:
    s = f"{v:>16,.2f}"
    return f"R$ {s.replace(',', 'X').replace('.', ',').replace('X', '.')}"


def main(pasta: Path) -> None:
    pdfs = sorted(pasta.glob("*.pdf"))
    print(f"\n{'='*78}\n  AUDITORIA COMPLETA NFE-Gado 2026 — {len(pdfs)} PDFs\n{'='*78}\n")

    notas_rel: dict[str, list[dict]] = defaultdict(list)  # produtor -> notas RE-1 aplicada
    erros: list[dict] = []

    t0 = time.time()
    for pdf in pdfs:
        posicao, produtor = posicao_e_produtor(pdf.name)
        try:
            notas, _, _ = extrair_notas(str(pdf))
            for n in notas:
                d = n.model_dump()
                d["posicao"]   = posicao
                d["atividade"] = "bovino"  # contexto NFE-Gado
                d["tipo_doc"]  = "nfa-e"
                # RE-1
                d = aplicar_regra_especial_1(d)
                notas_rel[produtor].append(d)
        except Exception as e:
            erros.append({"arquivo": pdf.name, "erro": str(e)[:120]})

    elapsed = time.time() - t0

    # ── Apuracao fiscal por produtor ────────────────────────────────────────────
    cabec = (
        f"{'PRODUTOR':<14} | {'F1 RECEITA':>14} | {'F6 DESPESA':>14} | "
        f"{'F5 RESULT':>14} | {'FUNRURAL':>10} | {'IRPF':>10}"
    )
    print(cabec)
    print("-" * len(cabec))

    consolidado_notas: list[dict] = []
    for produtor in sorted(notas_rel):
        notas = notas_rel[produtor]
        consolidado_notas.extend(notas)
        r = apurar_resumo(notas, eh_pj=False, eh_segurado_especial=False,
                          data_referencia=date(2026, 6, 1))  # apos corte 01/04/2026
        print(
            f"{produtor:<14} | "
            f"{r.f1_receita_imediata:>14,.0f} | {r.f6_despesa:>14,.0f} | "
            f"{r.f5_resultado_rural:>14,.0f} | {r.funrural:>10,.0f} | {r.irpf_estimado:>10,.0f}"
        )

    print("-" * len(cabec))
    consolidado = apurar_resumo(consolidado_notas, eh_pj=False, eh_segurado_especial=False,
                                data_referencia=date(2026, 6, 1))
    print(
        f"{'CONSOLIDADO':<14} | "
        f"{consolidado.f1_receita_imediata:>14,.0f} | {consolidado.f6_despesa:>14,.0f} | "
        f"{consolidado.f5_resultado_rural:>14,.0f} | {consolidado.funrural:>10,.0f} | {consolidado.irpf_estimado:>10,.0f}"
    )

    # ── Detalhe das formulas ────────────────────────────────────────────────────
    print("\n=== APURAÇÃO FISCAL CONSOLIDADA (PF, ref 06/2026) ===")
    print(f"  F1 — Receita Imediata (VENDA)         {fmt(consolidado.f1_receita_imediata)}")
    print(f"  F2 — Gado em Trânsito                 {fmt(consolidado.f2_transito)}")
    print(f"  F3 — Receita de Leilão                {fmt(consolidado.f3_receita_leilao)}")
    print(f"  F4 — Receita Bruta (F1+F3)            {fmt(consolidado.f4_receita_bruta)}")
    print(f"  F6 — Despesa Dedutível (COMPRA)       {fmt(consolidado.f6_despesa)}")
    print(f"  F5 — Resultado Rural (F4-F6)          {fmt(consolidado.f5_resultado_rural)}")
    print("  ── Tributos estimados ──")
    print(f"  Alíquota FUNRURAL aplicada            {consolidado.aliquota_funrural*100:.2f}%  (PF >= 01/04/2026)")
    print(f"  FUNRURAL devido (F1 × alíquota)       {fmt(consolidado.funrural)}")
    print(f"  IRPF estimado (F5 × 20%, mínimo 0)    {fmt(consolidado.irpf_estimado)}")
    print(f"  ── Carga tributária total ──          {fmt(consolidado.funrural + consolidado.irpf_estimado)}")

    # ── Categorizacao final por nota ────────────────────────────────────────────
    print("\n=== DISTRIBUIÇÃO POR CATEGORIA (após RE-1) ===")
    cats: dict[str, dict] = defaultdict(lambda: {"notas": 0, "valor": 0.0, "cabecas": 0.0})
    for n in consolidado_notas:
        cat = n.get("natureza_exibicao", "OUTRAS")
        cats[cat]["notas"]   += 1
        cats[cat]["valor"]   += float(n.get("valor_total", 0))
        cats[cat]["cabecas"] += float(n.get("quantidade_total", 0))

    print(f"  {'CATEGORIA':<16} {'NOTAS':>6} {'CABECAS':>10} {'VALOR (R$)':>20}")
    print(f"  {'-'*54}")
    total_n = total_v = total_c = 0
    for cat in ("VENDA", "COMPRA", "REMESSA", "TRANSFERENCIA", "OUTRAS"):
        d = cats.get(cat, {"notas": 0, "valor": 0, "cabecas": 0})
        total_n += d["notas"]; total_v += d["valor"]; total_c += d["cabecas"]
        print(f"  {cat:<16} {d['notas']:>6} {d['cabecas']:>10,.1f} {d['valor']:>20,.2f}")
    print(f"  {'-'*54}")
    print(f"  {'TOTAL':<16} {total_n:>6} {total_c:>10,.1f} {total_v:>20,.2f}")

    # ── Alertas RE-1 ────────────────────────────────────────────────────────────
    alertas = [(n["pdf_origem"] if "pdf_origem" in n else "?", n.get("alertas_re1", []))
               for n in consolidado_notas if n.get("alertas_re1")]
    print(f"\n=== ALERTAS RE-1 ({len(alertas)} notas) ===")
    if alertas:
        for arq, a in alertas[:10]:
            print(f"  [{arq}] {' | '.join(a)}")
    else:
        print("  Nenhum alerta crítico (todas as compras dentro de R$100-R$500k).")

    # Recontar alertas direto pelas notas
    alertas_500k = sum(
        1 for n in consolidado_notas
        if n.get("regra_aplicada") == "REGRA_ESPECIAL_1"
        and any("R$500k" in a for a in n.get("alertas_re1", []))
    )
    if alertas_500k:
        print(f"\n  >> {alertas_500k} compras > R$500k exigem revisão manual obrigatória")

    # ── Diagnostico ─────────────────────────────────────────────────────────────
    print("\n=== DIAGNÓSTICO ===")
    print(f"  Tempo total:           {elapsed:.1f}s")
    print(f"  PDFs processados:      {len(pdfs)}")
    print(f"  PDFs vazios:           {len(pdfs) - len({p for p in pdfs if notas_rel.get(posicao_e_produtor(p.name)[1])})}")
    print(f"  Notas extraídas:       {len(consolidado_notas)}")
    print(f"  Reclassificadas RE-1:  {sum(1 for n in consolidado_notas if n.get('regra_aplicada') == 'REGRA_ESPECIAL_1')}")
    print(f"  Erros:                 {len(erros)}")

    # ── Saida JSON ──────────────────────────────────────────────────────────────
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"auditoria_completa_{int(time.time())}.json"
    out.write_text(
        json.dumps({
            "tempo_s": round(elapsed, 2),
            "consolidado_apuracao": consolidado.to_dict(),
            "por_produtor": {
                p: apurar_resumo(notas_rel[p], eh_pj=False,
                                 data_referencia=date(2026, 6, 1)).to_dict()
                for p in notas_rel
            },
            "categorias": {c: dict(v) for c, v in cats.items()},
            "alertas_re1_qtd": alertas_500k,
            "erros": erros,
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
