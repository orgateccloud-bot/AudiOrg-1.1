"""
Pipeline completo OrgAudi + Horizon-Blue-One — testa os 28 agentes contra os
PDFs do NFE-Gado 2026. Usa MOCK do call_model (zero custo Claude) para validar
que cada agente recebe payload, processa e devolve AgentResult contratual.

Etapas:
  1. Extracao deterministica via nfa_extractor (ja validado)
  2. RE-1 (regra_especial_1) reclassifica VENDA -> COMPRA quando elegivel
  3. F1-F6 + FUNRURAL + IRPF via resumo_fiscal.apurar_resumo
  4. Detectores forenses heuristicos (ja deterministicos, sem Claude)
  5. Loop nos 28 agentes Horizon-Blue com payload contextual
  6. Relatorio markdown + JSON + tabela de resultados

Saida:
  out/horizon_full_<ts>.json   — todos os AgentResult
  out/horizon_full_<ts>.md     — relatorio formatado em markdown
"""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from horizon_blue_one.orgaudi.anomalias import CATALOGO
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1
from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo
from nfa_extractor.domain.extractor import extrair_notas


# ── Mock determinístico do Claude — devolve JSON parseável ────────────────────
async def _fake_call_model(model_type, prompt, system="", max_tokens=4096):
    """Resposta MOCK que cobre os formatos esperados pelos 28 agentes.
    Inclui todos os campos de NFAAuditSchema, esocial, itr, planejador, etc."""
    return json.dumps({
        # campos genéricos
        "status": "APROVADO",
        "confidence": 0.85,
        "decisao": "APROVADO",
        "score": 42,
        "score_risco": 42,
        "tipologias": [],
        "tipologias_criticas": [],
        "anomalias": [],
        "anomalias_detectadas": [],
        "achados": [],
        "alertas": [],
        "recomendacoes": ["Mock — pipeline determinístico"],
        "justificativa": "Mock determinístico (sem Claude).",
        "resumo": "Sem indícios críticos no modo mock.",
        "categoria": "BAIXO",
        "severidade": "BAIXA",

        # NFAAuditSchema (A-08)
        "f1_receita_imediata":    33521211.62,
        "f2_transito":            0.0,
        "f4_receita_bruta":       33521211.62,
        "f6_despesa":             29976365.32,
        "f5_resultado_rural":     3544846.30,
        "funrural":               546395.55,
        "aliquota_funrural":      0.0163,
        "irpf_estimado":          708969.26,
        "total_notas":            1704,
        "notas_re1_aplicada":     453,
        "probabilidade_autuacao": 0.15,
        "desvio_mercado_cepea":   0.05,
        "recomendacao_geral":     "Manter regime PF rural; revisar 1 compra > R$500k.",
        "proximos_passos":        ["Revisar nota crítica", "Conferir CFOPs", "Validar GTAs"],

        # Planejador-Tributário (A-11)
        "regime_recomendado":     "PF Rural",
        "economia_estimada":      0.0,
        "comparativo":            {"PF_Rural": 1255364, "PJ_Real": 1850000, "PJ_Presumido": 1620000},
        "tributos_estimados":     {"funrural": 546395, "irpf": 708969},

        # C-Suite (A-18)
        "kpis":                   {"receita": 33521211.62, "lucro_bruto": 3544846.30, "margem_pct": 10.6},
        "narrativa_executiva":    "Carteira saudável; mix venda/compra equilibrado.",

        # eSocial (A-20)
        "eventos_pendentes":      [],
        "compliance_score":       0.95,

        # ITR (A-22)
        "itr_devido":             0.0,
        "isencao_itr":            False,
        "diagnostico_itr":        "ITR não apurado neste mock.",

        # Anomalias (A-23)
        "shap_values":            {},
        "drivers_top":            [],

        # Geral
        "deducoes_encontradas":   [],
        "previsao_caixa":         {"30d": 0, "60d": 0, "90d": 0},
    }, ensure_ascii=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def posicao_e_produtor(arquivo: str) -> tuple[str, str]:
    base = arquivo.upper().replace(".PDF", "").strip()
    if base.endswith(" DEST"): return "DESTINATARIO", base[:-5].strip()
    if base.endswith(" REM"):  return "REMETENTE",    base[:-4].strip()
    return "DESCONHECIDO", base


def fmt(v: float) -> str:
    s = f"{v:>16,.2f}"
    return f"R$ {s.replace(',', 'X').replace('.', ',').replace('X', '.')}"


# ── Lista dos 28 agentes (id -> classe) ───────────────────────────────────────
AGENTES = [
    ("a00_ceo",                         "Agent00CEO"),
    ("a01_junior",                      "Agent01Junior"),
    ("a02_protetor",                    "Agent02Protetor"),
    ("a03_zerotrust",                   "Agent03ZeroTrust"),
    ("a04_vigilante",                   "Agent04Vigilante"),
    ("a05_engenheiro_erp",              "Agent05EngenheiroErp"),
    ("a06_extrator",                    "Agent06Extrator"),
    ("a07_auditoria_assurance",         "Agent07AuditoriaAssurance"),
    ("a08_auditor_nfa",                 "Agent08AuditorNfa"),
    ("a09_auditor_ti",                  "Agent09AuditorTi"),
    ("a10_auditor_patrimonio",          "Agent10AuditorPatrimonio"),
    ("a11_planejador_tributario",       "Agent11PlanejadorTributario"),
    ("a12_descobridor_deducoes",        "Agent12DescobridorDeducoes"),
    ("a13_monitor_conformidade",        "Agent13MonitorConformidade"),
    ("a14_avaliador_risco",             "Agent14AvaliadorRisco"),
    ("a15_juridico_ext",                "Agent15JuridicoExt"),
    ("a16_lgpd",                        "Agent16Lgpd"),
    ("a17_previsor_caixa",              "Agent17PrevisorCaixa"),
    ("a18_analista_csuite",             "Agent18AnalistaCsuite"),
    ("a19_contabilista_ia",             "Agent19ContabilistaIa"),
    ("a20_esocial_ia",                  "Agent20EsocialIa"),
    ("a21_auditor_icms",                "Agent21AuditorIcms"),
    ("a22_auditor_itr",                 "Agent22AuditorItr"),
    ("a23_analista_anomalias",          "Agent23AnalistaAnomalias"),
    ("a24_classificador_cfop",          "Agent24ClassificadorCfop"),
    ("a25_auditor_lcdpr",               "Agent25AuditorLcdpr"),
    ("a26_auditor_biologicos",          "Agent26AuditorBiologicos"),
    ("a27_epsilon_forensic",            "Agent27Epsilon"),
]


def descobrir_classe(modulo) -> type | None:
    """Encontra subclasse de BaseAgent no módulo."""
    from horizon_blue_one.agents.base_agent import BaseAgent
    for nome in dir(modulo):
        obj = getattr(modulo, nome)
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent:
            return obj
    return None


async def rodar_agente(modulo_nome: str, payload: dict) -> dict:
    """Importa o modulo, instancia e roda o agente, capturando metricas."""
    inicio = time.time()
    try:
        mod = importlib.import_module(f"horizon_blue_one.agents.{modulo_nome}")
        Cls = descobrir_classe(mod)
        if not Cls:
            return {"erro": "BaseAgent subclass nao encontrada"}
        ag = Cls()
        result = await ag.process(payload)
        return {
            "agent_id":   result.agent_id,
            "status":     result.status,
            "confidence": result.confidence,
            "audit_hash": (result.audit_hash or "")[:12],
            "tempo_ms":   round((time.time() - inicio) * 1000, 1),
            "out_keys":   list(result.output.keys()) if isinstance(result.output, dict) else [],
        }
    except Exception as e:
        return {
            "erro":     f"{type(e).__name__}: {str(e)[:120]}",
            "tempo_ms": round((time.time() - inicio) * 1000, 1),
        }


async def main(pasta: Path) -> None:
    print(f"\n{'='*78}\n  HORIZON-BLUE-ONE FULL PIPELINE — NFE-Gado 2026\n{'='*78}\n")

    # ─── 1. Extracao + RE-1 ────────────────────────────────────────────────
    pdfs = sorted(pasta.glob("*.pdf"))
    print(f"[1/5] Extraindo {len(pdfs)} PDFs com nfa_extractor...")
    notas_dict: list[dict] = []
    erros_pdf: list[dict] = []
    t0 = time.time()
    for pdf in pdfs:
        posicao, produtor = posicao_e_produtor(pdf.name)
        try:
            notas, _contribuinte, _ = extrair_notas(str(pdf))
            for n in notas:
                d = n.model_dump()
                d.update(posicao=posicao, atividade="bovino", tipo_doc="nfa-e",
                         produtor=produtor, pdf_origem=pdf.name)
                d = aplicar_regra_especial_1(d)
                notas_dict.append(d)
        except Exception as e:
            erros_pdf.append({"arquivo": pdf.name, "erro": str(e)[:120]})
    t_ext = time.time() - t0
    print(f"      OK -> {len(notas_dict)} notas em {t_ext:.1f}s\n")

    # ─── 2. Apuracao fiscal F1-F6 ──────────────────────────────────────────
    print("[2/5] Apurando F1-F6 + FUNRURAL + IRPF (PF, ref 06/2026)...")
    fiscal = apurar_resumo(notas_dict, eh_pj=False, data_referencia=date(2026, 6, 1))
    print(f"      F1={fmt(fiscal.f1_receita_imediata)} F6={fmt(fiscal.f6_despesa)}")
    print(f"      F5={fmt(fiscal.f5_resultado_rural)} FUNRURAL={fmt(fiscal.funrural)} IRPF={fmt(fiscal.irpf_estimado)}\n")

    # ─── 3. Categorias finais ──────────────────────────────────────────────
    cats: dict[str, dict] = defaultdict(lambda: {"notas": 0, "valor": 0.0, "cabecas": 0.0})
    for n in notas_dict:
        c = n.get("natureza_exibicao", "OUTRAS")
        cats[c]["notas"] += 1
        cats[c]["valor"] += float(n.get("valor_total", 0))
        cats[c]["cabecas"] += float(n.get("quantidade_total", 0))

    # ─── 4. Detectores forenses determinísticos ────────────────────────────
    print("[3/5] Detectores forenses heuristicos (deterministicos)...")
    from horizon_blue_one.agents.detectores_forenses import (
        detectar_anomalia_temporal,
        detectar_carrossel,
        detectar_devolucao_posterior,
        detectar_fornecedor_fantasma,
        detectar_smurfing,
    )
    det = {
        "carrossel":            detectar_carrossel(notas_dict),
        "smurfing":             detectar_smurfing(notas_dict),
        "fornecedor_fantasma":  detectar_fornecedor_fantasma(notas_dict),
        "devolucao_posterior":  detectar_devolucao_posterior(notas_dict),
        "anomalia_temporal":    detectar_anomalia_temporal(notas_dict),
    }
    for k, v in det.items():
        n_alertas = len(v) if isinstance(v, list) else (1 if v else 0)
        print(f"      {k:<16} -> {n_alertas} alerta(s)")
    print()

    # ─── 5. Rodar 28 agentes com mock do Claude ────────────────────────────
    print("[4/5] Executando 28 agentes Horizon-Blue (Claude MOCKED)...")
    contribuinte_dict = {
        "nome":     "Consolidado NFE-Gado 2026",
        "cpf_cnpj": "00000000000",
        "regime":   "PF Rural",
        "uf":       "GO",
        "atividade": "bovino",
    }
    payload_base = {
        "notas":                  notas_dict,
        "notas_classificadas":    notas_dict,
        "contribuinte":           contribuinte_dict,
        "is_pj":                  False,
        "score_risco":            42,
        "score_origem":           "F1-F6 deterministico",
        "valor_total":            fiscal.f1_receita_imediata,
        "tipologias_criticas":    0,
        "probabilidade_autuacao": 0.15,
        "regime_atual":           "PF Rural",
        "receita_bruta":          fiscal.f1_receita_imediata,
        "periodo":                "2025",
        "detectores_pre":         det,
        "score_info":             {"score": 42, "categoria": "BAIXO", "shap_values": {}},
        "shap_values":            {},
        "resultados_agentes":     {},
        "entidades":              [],
        "esocial_data":           {"folha": [], "eventos": []},
        "itr_data":               {"area_total": 0, "vtn": 0, "valor_imposto": 0},
        "lcdpr_data":             {"livro_caixa": []},
        "dados_erp":              {"contas": [], "movimentos": []},
        "sistema_erp":            "generico",
        "formato":                "nfa-e",
        "texto_nfa":              "amostra de NFA",
        "tipo_analise":           "auditoria",
        "contexto":               "Auditoria carteira NFE-Gado 2026",
        "requisicao_id":          "nfe-gado-2026",
    }

    resultados: list[dict] = []
    with patch("horizon_blue_one.core.model_adapter.call_model", side_effect=_fake_call_model):
        for mod_nome, _cls_nome in AGENTES:
            r = await rodar_agente(mod_nome, payload_base)
            resultados.append({"modulo": mod_nome, **r})
            ok = "OK" if not r.get("erro") else "ERRO"
            print(f"      [{ok:<4}] {r.get('agent_id','?'):<6} "
                  f"{r.get('status','?'):<10} conf={r.get('confidence', 0):.2f} "
                  f"{r.get('tempo_ms', 0):>6.1f}ms"
                  + (f"  {r['erro']}" if r.get('erro') else ""))

    ok = sum(1 for r in resultados if not r.get("erro"))
    print(f"\n      {ok}/{len(AGENTES)} agentes contractuais OK\n")

    # ─── 6. Relatorio Markdown ─────────────────────────────────────────────
    print("[5/5] Gerando relatorio markdown + JSON...")
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    ts = int(time.time())
    md_path = out_dir / f"horizon_full_{ts}.md"
    json_path = out_dir / f"horizon_full_{ts}.json"

    md = []
    md.append("# Relatório Horizon-Blue Full — NFE-Gado 2026\n")
    md.append(f"**Geração:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append(f"**Pasta:** `{pasta}`\n")
    md.append(f"**PDFs processados:** {len(pdfs)}  ·  **Notas extraídas:** {len(notas_dict)}\n")
    md.append(f"**Tempo extração:** {t_ext:.1f}s  ·  **Erros PDF:** {len(erros_pdf)}\n\n")

    md.append("## 1. Apuração Fiscal Rural (F1-F6, PF ref 06/2026)\n")
    md.append("| Métrica | Valor |\n|---|--:|\n")
    md.append(f"| F1 — Receita Imediata (VENDA) | {fmt(fiscal.f1_receita_imediata)} |\n")
    md.append(f"| F2 — Gado em Trânsito | {fmt(fiscal.f2_transito)} |\n")
    md.append(f"| F3 — Receita de Leilão | {fmt(fiscal.f3_receita_leilao)} |\n")
    md.append(f"| F4 — Receita Bruta (F1+F3) | {fmt(fiscal.f4_receita_bruta)} |\n")
    md.append(f"| F6 — Despesa Dedutível (COMPRA) | {fmt(fiscal.f6_despesa)} |\n")
    md.append(f"| F5 — Resultado Rural (F4-F6) | **{fmt(fiscal.f5_resultado_rural)}** |\n")
    md.append(f"| Alíquota FUNRURAL | {fiscal.aliquota_funrural*100:.2f}% |\n")
    md.append(f"| FUNRURAL devido | **{fmt(fiscal.funrural)}** |\n")
    md.append(f"| IRPF estimado (20% s/F5) | **{fmt(fiscal.irpf_estimado)}** |\n")
    md.append(f"| Carga tributária total | **{fmt(fiscal.funrural + fiscal.irpf_estimado)}** |\n\n")

    md.append("## 2. Distribuição por Categoria (após RE-1)\n")
    md.append("| Categoria | Notas | Cabeças | Valor (R$) |\n|---|--:|--:|--:|\n")
    for c in ("VENDA", "COMPRA", "REMESSA", "TRANSFERENCIA", "OUTRAS"):
        d = cats.get(c, {"notas": 0, "valor": 0, "cabecas": 0})
        md.append(f"| {c} | {d['notas']} | {d['cabecas']:,.1f} | {d['valor']:,.2f} |\n")
    total_n = sum(d['notas']   for d in cats.values())
    total_v = sum(d['valor']   for d in cats.values())
    total_c = sum(d['cabecas'] for d in cats.values())
    md.append(f"| **TOTAL** | **{total_n}** | **{total_c:,.1f}** | **{total_v:,.2f}** |\n\n")

    md.append("## 3. Detectores Forenses (heurísticos)\n")
    md.append("| Detector | Alertas |\n|---|--:|\n")
    for k, v in det.items():
        n = len(v) if isinstance(v, list) else (1 if v else 0)
        md.append(f"| {k} | {n} |\n")
    md.append("\n")

    md.append("## 4. Execução dos 28 Agentes Horizon-Blue\n")
    md.append("> Claude API foi mockada (sem custo). Status reflete contrato cumprido pelo agente.\n\n")
    md.append("| Agent | Status | Confiança | Tempo (ms) | Output keys |\n|---|---|--:|--:|---|\n")
    for r in resultados:
        if r.get("erro"):
            md.append(f"| {r['modulo']} | ❌ {r['erro'][:60]} | — | {r.get('tempo_ms', 0):.1f} | — |\n")
        else:
            keys = ", ".join((r.get("out_keys") or [])[:5])
            md.append(f"| {r['agent_id']} | ✅ {r['status']} | {r['confidence']:.2f} | {r['tempo_ms']:.1f} | `{keys}` |\n")
    md.append("\n")

    # Catálogo de tipologias
    md.append("## 5. Catálogo de Tipologias (referência AN-01..AN-18)\n")
    md.append("| Código | Nome | Eixo | Severidade |\n|---|---|---|---|\n")
    for cod in sorted(CATALOGO):
        t = CATALOGO[cod]
        md.append(f"| {t.codigo} | {t.nome} | {t.eixo} | {t.severidade} |\n")
    md.append("\n")

    # ─── Fluxograma Mermaid ────────────────────────────────────────────────
    md.append("## 6. Fluxograma do Pipeline\n\n")
    md.append("```mermaid\n")
    md.append("""flowchart TD
    PDF[📄 PDFs NFE-Gado] --> EXT[nfa_extractor.extrair_notas<br/>pdfplumber + regex]
    EXT --> RE1[RE-1 regra_especial_1<br/>VENDA→COMPRA se DEST + rural]
    RE1 --> CAT{Categorização<br/>VENDA · COMPRA · REMESSA<br/>TRANSFERENCIA · OUTRAS}
    CAT --> F16[apurar_resumo<br/>F1-F6 + FUNRURAL + IRPF]

    RE1 --> DET[Detectores Forenses<br/>smurfing · outliers · circularidade<br/>intrafamiliar · inversão temporal]

    DET --> A_TOKEN[A-Token @Token<br/>Roteador Haiku/Sonnet/Opus]

    A_TOKEN --> SCORE{Score Risco}
    SCORE -->|<25| HAIKU[A-01 A-06 A-13 A-16 A-24<br/>Haiku $0.80/$4.00 MTok]
    SCORE -->|25-85| SONNET[A-07 a A-26<br/>Sonnet $3.00/$15.00 MTok]
    SCORE -->|≥85 ou crítico| OPUS[A-27 A-00<br/>Opus $15.00/$75.00 MTok]

    HAIKU --> AGREGADOR[A-13 Monitor Conformidade<br/>+ A-23 Análise Anomalias]
    SONNET --> AGREGADOR
    OPUS --> AGREGADOR

    AGREGADOR --> A18[A-18 Analista C-Suite<br/>resumo executivo]
    A18 --> A00[A-00 CEO<br/>decisão final]
    A00 --> RELATORIO[📊 Relatório PDF + Excel<br/>pdf_engine + xlsx_export]

    style PDF fill:#1e3a8a,color:#fff
    style RE1 fill:#7c2d12,color:#fff
    style F16 fill:#166534,color:#fff
    style A_TOKEN fill:#581c87,color:#fff
    style A00 fill:#9f1239,color:#fff
    style RELATORIO fill:#0f766e,color:#fff
""")
    md.append("```\n")

    md_path.write_text("".join(md), encoding="utf-8")
    json_path.write_text(json.dumps({
        "tempo_ext_s": t_ext,
        "erros_pdf": erros_pdf,
        "fiscal": fiscal.to_dict(),
        "categorias": {c: dict(v) for c, v in cats.items()},
        "detectores": {k: (v if isinstance(v, (int, float, str, bool)) else len(v) if isinstance(v, list) else str(v)) for k, v in det.items()},
        "agentes": resultados,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\n>> Relatório:  {md_path}")
    print(f">> JSON:       {json_path}")


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pasta or not pasta.exists():
        print("ERRO: passe a pasta com PDFs como argumento")
        sys.exit(1)
    asyncio.run(main(pasta))
