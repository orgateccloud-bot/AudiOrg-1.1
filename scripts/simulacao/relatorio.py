"""
Geração de outputs (4 JSONs + 1 markdown) a partir dos resultados
das simulações individual e consolidada.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_usd(v: float) -> str:
    return f"USD {v:,.4f}"


def salvar_json(path: Path, dados: Any) -> None:
    path.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def agregar_por_agente(simulacoes: list[dict]) -> dict[str, dict]:
    """Soma chamadas/tokens/custo por agent_id, qualquer simulação."""
    por_agente: dict[str, dict] = defaultdict(lambda: {
        "chamadas": 0, "tokens_in": 0, "tokens_out": 0,
        "custo_usd": 0.0, "modelos": defaultdict(int),
    })
    for sim in simulacoes:
        for c in sim.get("chamadas", []):
            aid = c.get("agent_id", "?")
            d = por_agente[aid]
            d["chamadas"] += 1
            d["tokens_in"] += c.get("tokens_in", 0)
            d["tokens_out"] += c.get("tokens_out", 0)
            d["custo_usd"] += c.get("custo_usd", 0.0)
            d["modelos"][c.get("modelo", "?")] += 1

    out: dict[str, dict] = {}
    for aid, d in por_agente.items():
        total_modelos = sum(d["modelos"].values()) or 1
        modelo_predom = max(d["modelos"], key=d["modelos"].get)
        out[aid] = {
            "chamadas":            d["chamadas"],
            "tokens_in":           d["tokens_in"],
            "tokens_out":          d["tokens_out"],
            "custo_usd":           round(d["custo_usd"], 6),
            "modelo_predominante": modelo_predom,
            "%_haiku":             round(d["modelos"].get("haiku", 0) / total_modelos * 100, 1),
            "%_sonnet":            round(d["modelos"].get("sonnet", 0) / total_modelos * 100, 1),
            "%_opus":              round(d["modelos"].get("opus", 0) / total_modelos * 100, 1),
        }
    return dict(sorted(out.items()))


def comparativo_economia(simulacoes: list[dict]) -> dict:
    atual = sum(s["totais"]["custo_usd"] for s in simulacoes if s.get("totais"))
    base = sum(s["totais"]["custo_baseline_sonnet"] for s in simulacoes if s.get("totais"))
    economia = base - atual
    pct = (economia / base * 100) if base > 0 else 0

    chamadas_modelo: dict[str, int] = defaultdict(int)
    for s in simulacoes:
        for c in s.get("chamadas", []):
            chamadas_modelo[c.get("modelo", "?")] += 1
    total_chamadas = sum(chamadas_modelo.values()) or 1
    distrib = {m: round(chamadas_modelo[m] / total_chamadas * 100, 1)
               for m in ("haiku", "sonnet", "opus")}

    return {
        "atual_usd":              round(atual, 4),
        "baseline_sonnet_usd":    round(base, 4),
        "economia_usd":           round(economia, 4),
        "economia_pct":           round(pct, 2),
        "distribuicao_modelos":   distrib,
        "total_chamadas":         total_chamadas,
        "projecao_1000_pdfs":     {
            "atual":     round(atual * 1000 / max(1, len(simulacoes)), 2),
            "baseline":  round(base * 1000 / max(1, len(simulacoes)), 2),
            "economia":  round(economia * 1000 / max(1, len(simulacoes)), 2),
        },
    }


def gerar_markdown(
    out_dir: Path,
    individual: list[dict],
    consolidado: list[dict],
    por_agente: dict,
    economia: dict,
    gt_match: dict,
    pdfs_vazios: list[str],
    pipeline_label: str,
    n_total_pdfs: int,
) -> Path:
    L: list[str] = []
    L.append("# Simulação NFE-Gado 2026 — Consumo de Tokens\n\n")
    L.append(f"**Pipeline:** `{pipeline_label}` ")
    L.append(f"· **PDFs:** {n_total_pdfs} ")
    L.append(f"· **Análises individuais:** {len(individual)} ")
    L.append(f"· **Análises consolidadas:** {len(consolidado)}\n\n")

    # Resumo Executivo
    L.append("## Resumo Executivo\n\n")
    L.append("| Métrica | Valor |\n|---|--:|\n")
    L.append(f"| Custo total (mock) | {fmt_usd(economia['atual_usd'])} |\n")
    L.append(f"| Baseline tudo-Sonnet | {fmt_usd(economia['baseline_sonnet_usd'])} |\n")
    L.append(f"| **Economia absoluta** | {fmt_usd(economia['economia_usd'])} |\n")
    L.append(f"| **Economia %** | **{economia['economia_pct']}%** |\n")
    L.append(f"| Mix de modelos (Haiku/Sonnet/Opus) | "
             f"{economia['distribuicao_modelos']['haiku']}% / "
             f"{economia['distribuicao_modelos']['sonnet']}% / "
             f"{economia['distribuicao_modelos']['opus']}% |\n")
    L.append(f"| Total de chamadas Claude | {economia['total_chamadas']} |\n")
    L.append(f"| PDFs vazios (sem extração) | {len(pdfs_vazios)} |\n\n")

    # Tabela 1 — Por PDF individual
    L.append(f"## Tabela 1 — Consumo por PDF Individual ({len(individual)})\n\n")
    L.append("| PDF | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Economia % |\n")
    L.append("|---|--:|--:|--:|--:|--:|--:|\n")
    for s in sorted(individual, key=lambda x: -(x.get("totais") or {}).get("custo_usd", 0)):
        if s["status"] != "OK":
            L.append(f"| {s['pdf']} | — | — | — | — | — | _{s['status']}_ |\n")
            continue
        t = s["totais"]
        L.append(f"| {s['pdf']} | {s['n_notas']} | {s['valor_total']:,.0f} | "
                 f"{t['tokens_in']:,} | {t['tokens_out']:,} | "
                 f"{t['custo_usd']:.4f} | {t['economia_pct']:.1f}% |\n")
    L.append("\n")

    # Tabela 2 — Por Produtor consolidado
    L.append(f"## Tabela 2 — Consumo Consolidado por Produtor ({len(consolidado)})\n\n")
    L.append("| Produtor | PDFs | Notas | Valor (R$) | Tok IN | Tok OUT | Custo (USD) | Eco % |\n")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|\n")
    for s in sorted(consolidado, key=lambda x: -(x.get("totais") or {}).get("custo_usd", 0)):
        if s["status"] != "OK":
            L.append(f"| {s['produtor']} | — | — | — | — | — | — | _{s['status']}_ |\n")
            continue
        t = s["totais"]
        L.append(f"| {s['produtor']} | {len(s['pdfs_origem'])} | {s['n_notas']} | "
                 f"{s['valor_total']:,.0f} | {t['tokens_in']:,} | {t['tokens_out']:,} | "
                 f"{t['custo_usd']:.4f} | {t['economia_pct']:.1f}% |\n")
    L.append("\n")

    # Tabela 3 — Por Agente
    L.append("## Tabela 3 — Consumo por Agente\n\n")
    L.append("| Agent | Chamadas | Modelo predomin. | Tok IN | Tok OUT | Custo (USD) | "
             "%H | %S | %O |\n")
    L.append("|---|--:|---|--:|--:|--:|--:|--:|--:|\n")
    for aid in sorted(por_agente):
        a = por_agente[aid]
        L.append(f"| {aid} | {a['chamadas']} | {a['modelo_predominante']} | "
                 f"{a['tokens_in']:,} | {a['tokens_out']:,} | {a['custo_usd']:.4f} | "
                 f"{a['%_haiku']} | {a['%_sonnet']} | {a['%_opus']} |\n")
    L.append("\n")

    # Tabela 4 — Mix de modelos
    L.append("## Tabela 4 — Mix de Modelos (alvo 80/15/5)\n\n")
    L.append("| Modelo | % chamadas | Custo (USD) |\n|---|--:|--:|\n")
    custo_modelo: dict[str, float] = defaultdict(float)
    for s in (individual + consolidado):
        for c in s.get("chamadas", []):
            custo_modelo[c.get("modelo", "?")] += c.get("custo_usd", 0.0)
    for m in ("haiku", "sonnet", "opus"):
        L.append(f"| {m.upper()} | {economia['distribuicao_modelos'].get(m, 0)}% | "
                 f"{custo_modelo.get(m, 0):.4f} |\n")
    L.append("\n")

    # Tabela 5 — Ground-Truth match
    if gt_match:
        L.append("## Tabela 5 — Comparação com Ground-Truth (RESULTADOS_AUDITORIA.zip)\n\n")
        L.append("| Produtor | Tem GT? | PDF GT | Similaridade |\n|---|---|---|--:|\n")
        for produtor in sorted(gt_match):
            m = gt_match[produtor]
            sim_str = (f"{m['similaridade']:.2%}" if m.get("tem_gt") and "similaridade" in m
                       else "—")
            tem = "✅" if m.get("tem_gt") else "❌"
            gt_pdf = m.get("gt_pdf", m.get("motivo", "—"))
            L.append(f"| {produtor} | {tem} | {gt_pdf} | {sim_str} |\n")
        sims = [m["similaridade"] for m in gt_match.values()
                if m.get("tem_gt") and "similaridade" in m]
        if sims:
            L.append(f"\n**Similaridade média:** {sum(sims)/len(sims):.2%} "
                     f"(min {min(sims):.2%}, max {max(sims):.2%})\n\n")

    # Comparativo
    L.append("## Projeção de Custo\n\n")
    L.append("| Cenário | Atual | Baseline (Sonnet) | Economia |\n|---|--:|--:|--:|\n")
    p = economia["projecao_1000_pdfs"]
    L.append(f"| {len(individual) + len(consolidado)} análises | "
             f"{fmt_usd(economia['atual_usd'])} | {fmt_usd(economia['baseline_sonnet_usd'])} | "
             f"{fmt_usd(economia['economia_usd'])} |\n")
    L.append(f"| 1.000 análises (projeção) | {fmt_usd(p['atual'])} | "
             f"{fmt_usd(p['baseline'])} | {fmt_usd(p['economia'])} |\n\n")

    # Vazios
    if pdfs_vazios:
        L.append(f"## PDFs vazios ({len(pdfs_vazios)})\n\n")
        for nome in pdfs_vazios:
            L.append(f"- {nome}\n")
        L.append("\nObs: extração determinística não encontrou padrões. "
                 "Em modo `--real`, fallback `nfa_parser_ai` seria acionado.\n\n")

    # Detalhes
    L.append("## Detalhes técnicos\n\n")
    L.append("- **Modo:** mock (estimativa via `len(prompt)//4` no prompt real)\n")
    L.append("- **Mix-alvo:** Haiku 80% · Sonnet 15% · Opus 5%\n")
    L.append("- **max_tokens:** calibrado por agente em `MAX_TOKENS_OTIMO`\n")
    L.append("- **Output ratio:** 40% do max_tokens (estimativa típica)\n")
    L.append("- **Prompt cache:** não simulado (modo conservador, custo real seria menor)\n")

    md_path = out_dir / "relatorio.md"
    md_path.write_text("".join(L), encoding="utf-8")
    return md_path
