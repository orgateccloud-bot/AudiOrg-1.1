"""scripts/gerar_laudo_forense_hard.py

Gera laudos individuais no **modelo simplificado oficial** (HTML/Chrome)
de `api.services.auditoria_cruzada_pdf.gerar_pdf_auditoria_cruzada`, mas
com os achados endurecidos T-01..T-08 + AN-02..AN-17 injetados no schema
`auditoria_v2.json`.

Pipeline:
  1. Lê outputs/<slug>/auditoria_v2.json (base do template oficial)
  2. Carrega ANALISE_FORENSE_HARD + ANOMALIAS_AN18
  3. Converte cada achado endurecido para o schema Achado do template
  4. Substitui achados_criticos / achados_medios / pontos_atencao
  5. Atualiza severidades
  6. Chama gerar_pdf_auditoria_cruzada(modo="simplificado")

Saída:
  reports_nfa/forense_individual/LAUDO_FORENSE_HARD_<slug>_<data>.pdf
"""
from __future__ import annotations

import io
import json
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.services.auditoria_cruzada_pdf import gerar_pdf_auditoria_cruzada

DATA = datetime.now().strftime("%Y-%m-%d")
DEST = RAIZ / "reports_nfa" / "forense_individual"
DEST.mkdir(parents=True, exist_ok=True)

def _pick_latest(prefix: str) -> Path:
    cand = sorted((RAIZ / "reports_nfa").glob(f"{prefix}_*.json"))
    if not cand:
        return RAIZ / "reports_nfa" / f"{prefix}_{DATA}.json"
    return cand[-1]

ARQ_HARD = _pick_latest("ANALISE_FORENSE_HARD")
ARQ_AN18 = _pick_latest("ANOMALIAS_AN18")


# ── Formatadores ─────────────────────────────────────────────────────────

def fmt_brl(v) -> str:
    if v is None: return "—"
    if isinstance(v, str):
        try: v = Decimal(v)
        except Exception: return v
    s = f"{Decimal(str(v)):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_data_br(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


def fmt_pct(p) -> str:
    if isinstance(p, (int, float)):
        return f"{p:.2f}%".replace(".", ",")
    return str(p)


# ── Conversores Achado endurecido → Achado schema v2 ─────────────────────

def conv_t01(achados_t01: list[dict]) -> list[dict]:
    """T-01 endurecido → achados C-XX no schema oficial."""
    out = []
    crits = [a for a in achados_t01 if a["tipo"] == "CRITICO"]
    if crits:
        linhas = [[
            a["nfa"], fmt_data_br(a["data"]),
            fmt_brl(a["valor"]), fmt_pct(a["pct"]),
            (a.get("destinatario") or "—")[:35],
            a.get("cpf", "—"),
        ] for a in crits]
        out.append({
            "codigo": "C-T01",
            "titulo": f"T-01 Concentração de nota individual — {len(crits)} crítico(s)",
            "descricao": (
                f"<b>Critério endurecido:</b> nota individual ≥ 7% da receita anual. "
                f"{len(crits)} nota(s) com concentração crítica detectada(s) no "
                "exercício. Cada operação singular de grande monta sinaliza "
                "AN-13 (concentração atípica) e demanda comprovação de capacidade "
                "do imóvel rural do destinatário e cruzamento com extrato bancário."),
            "severidade": "CRITICO",
            "porque_critico": (
                "Concentração em evento único pode mascarar AN-18 (caixa dois) "
                "quando associada a contraparte recorrente; magnitude exige "
                "comprovação de capacidade produtiva (SiCAR) e fluxo financeiro."),
            "cruzamentos": [
                "GTA AGRODEFESA-GO de cada NFA-e listada",
                "Extrato bancário casado com os valores totais",
                "Capacidade do imóvel rural do destinatário (SiCAR/CAR)",
                "Vínculo familiar/societário (JUCEG/RFB) do destinatário",
            ],
            "tabela_cabecalhos": ["NFA-e", "Data", "Valor", "% receita",
                                    "Destinatário", "CPF"],
            "tabela_linhas": linhas,
            "tabela_totais": [],
        })
    return out


def conv_t02(achados_t02: list[dict]) -> list[dict]:
    """T-02 endurecido (4 subtipos) → achados C-XX."""
    if not achados_t02: return []
    linhas = [[
        a["tipo"].replace("CRITICO_", ""),
        (a.get("destinatario") or "—")[:30],
        a.get("cpf", "—"),
        str(a["qtd_notas"]),
        fmt_brl(a["valor_total"]),
        a.get("data") or a.get("periodo") or "—",
    ] for a in achados_t02[:25]]
    from collections import Counter
    cnt = Counter(a["tipo"] for a in achados_t02)
    dist = ", ".join(f"{k.replace('CRITICO_','')}={v}" for k, v in cnt.items())
    return [{
        "codigo": "C-T02",
        "titulo": f"T-02 Smurfing / Fragmentação fiscal — {len(achados_t02)} achado(s)",
        "descricao": (
            "<b>Critérios endurecidos (4 subtipos):</b> "
            "<b>A)</b> 3+ notas idênticas mesmo dia &nbsp;|&nbsp; "
            "<b>B)</b> 4+ notas em 7d com 2+ valores iguais &nbsp;|&nbsp; "
            "<b>C)</b> 2+ notas mesma data + mesma contraparte &nbsp;|&nbsp; "
            "<b>D)</b> 3+ notas mesma contraparte em 30d, soma ≥ R$ 100k. "
            f"<br/><b>Distribuição:</b> {dist}. "
            "Padrão AN-01 (Eixo I)."),
        "severidade": "CRITICO",
        "porque_critico": (
            "Hipóteses: (i) manter cada nota abaixo de limiar de triagem; "
            "(ii) uso de 'laranja'; (iii) lavagem de gado; (iv) elusão "
            "de regimes especiais (Funrural retido pelo adquirente)."),
        "cruzamentos": [
            "GTAs AGRODEFESA-GO de todas as notas do dia/janela",
            "Extrato bancário do contribuinte (PIX/depósitos casados)",
            "CAEPF do destinatário recorrente",
            "Vínculo familiar/societário (JUCEG/RFB)",
        ],
        "tabela_cabecalhos": ["Sub", "Destinatário", "CPF", "Qtd",
                                "Valor total", "Janela"],
        "tabela_linhas": linhas,
        "tabela_totais": [],
    }]


def conv_t03(t03: dict) -> list[dict]:
    """T-03 NOVO → achados C-XX."""
    if not t03: return []
    achados = t03.get("achados") or []
    if not achados: return []
    out = []
    top1 = next((a for a in achados if a.get("subtipo") == "TOP1"), None)
    top3 = next((a for a in achados if a.get("subtipo") == "TOP3"), None)
    if top1:
        rank = t03.get("ranking_top5") or []
        linhas = [[
            str(i+1), (r.get("nome") or "—")[:35], r.get("cpf","—"),
            str(r.get("qtd",0)), fmt_brl(r.get("valor",0)), fmt_pct(r.get("pct",0)),
        ] for i, r in enumerate(rank[:5])]
        out.append({
            "codigo": "C-T03",
            "titulo": (
                f"T-03 Captura monopsônica — TOP1 concentra "
                f"{top1.get('pct', 0):.1f}% ({top1.get('tipo')})"),
            "descricao": (
                f"<b>{top1.get('destinatario','—')}</b> ({top1.get('cpf','—')}) "
                f"concentra <b>{top1.get('pct',0):.1f}%</b> da receita anual — "
                f"{fmt_brl(top1.get('valor',0))} em {top1.get('qtd',0)} nota(s). "
                "Critério: ≥30% = CRÍTICO; ≥20% = ATENÇÃO. Detecta AN-13 "
                "(concentração atípica) e indicia AN-05 (laranja) ou AN-07 "
                "(intermediação)."),
            "severidade": top1.get("tipo", "ATENCAO"),
            "porque_critico": (
                "Captura monopsônica caracteriza dependência operacional do "
                "produtor face a 1 único comprador, padrão atípico em pecuária "
                "extensiva e sugestivo de venda casada/contratada."),
            "cruzamentos": [
                "CAEPF do destinatário concentrado",
                "Vínculo societário/familiar (JUCEG/RFB)",
                "Histórico bancário do destinatário",
                "Eventos de leilão registrados no exercício",
            ],
            "tabela_cabecalhos": ["#", "Destinatário", "CPF", "Qtd",
                                    "Valor", "% receita"],
            "tabela_linhas": linhas,
            "tabela_totais": [],
        })
    if top3:
        out.append({
            "codigo": "C-T03B",
            "titulo": f"T-03 TOP-3 concentra {top3.get('pct',0):.1f}% da receita",
            "descricao": (
                f"Os 3 maiores compradores absorvem <b>{top3.get('pct',0):.1f}%</b> "
                f"({fmt_brl(top3.get('valor',0))}) — indicativo de Pareto "
                "fortemente comprimido e exposição a 3 contrapartes."),
            "severidade": "CRITICO",
            "porque_critico": (
                "Cadeia comercial restrita a 3 compradores eleva risco operacional, "
                "favorece colusão de preços e dificulta verificação de mercado."),
            "cruzamentos": [
                "CAEPF dos 3 destinatários principais",
                "Cruzamento societário entre destinatários (JUCEG)",
            ],
            "tabela_cabecalhos": ["Destinatário", "% receita"],
            "tabela_linhas": [[d.get("nome","—"), fmt_pct(d.get("pct",0))]
                              for d in top3.get("destinatarios", [])],
            "tabela_totais": [],
        })
    return out


def conv_t04(t04: dict) -> list[dict]:
    """T-04 endurecido → achado A-XX (alto) ou AT-XX (atenção)."""
    if not t04: return []
    tipo = t04.get("tipo")
    sev = "ALTO" if tipo == "CRITICO" else "ATENCAO"
    recorr = t04.get("recorrentes", [])
    linhas = [[
        r.get("nome","—")[:35], r.get("cpf","—"),
        str(r.get("qtd",0)), fmt_brl(r.get("valor",0)),
    ] for r in recorr[:12]]
    return [{
        "codigo": "A-T04",
        "titulo": f"T-04 Concentração em PFs com perfil de revenda — {t04.get('pct_pf',0):.1f}%",
        "descricao": (
            f"<b>{t04.get('qtd_vendas_pf',0)}</b> de "
            f"<b>{t04.get('qtd_vendas',0)}</b> vendas diretas para PF "
            f"({t04.get('pct_pf',0):.1f}%). "
            f"<b>{len(recorr)}</b> PFs aparecem com 3+ aquisições. "
            "Critério endurecido: ≥85% + recorrência = CRÍTICO; ≥70% = ATENÇÃO."),
        "severidade": sev,
        "porque_critico": (
            "PF sem CAEPF + 3+ aquisições = intermediação não declarada "
            "(AN-07) ou potencial laranja (AN-05). Cada PF deve ter atividade "
            "rural declarada na RFB."),
        "cruzamentos": [
            "CAEPF de cada PF recorrente (Receita Federal)",
            "GTAs AGRODEFESA-GO em nome dos PFs",
            "Capacidade do imóvel rural (SiCAR) dos PFs",
        ],
        "tabela_cabecalhos": ["Destinatário PF", "CPF", "Notas", "Valor"],
        "tabela_linhas": linhas,
        "tabela_totais": [],
    }]


def conv_an02_03(an02: list[dict], an03: list[dict]) -> list[dict]:
    out = []
    if an02:
        crits = [a for a in an02 if a["tipo"] == "CRITICO"]
        linhas = [[
            a["nfa"], fmt_data_br(a["data"]),
            fmt_brl(a["rs_por_cabeca"]),
            str(a["cabecas"]), fmt_brl(a["valor"]),
            (a.get("destinatario","—"))[:25],
        ] for a in an02[:15]]
        out.append({
            "codigo": "C-AN02" if crits else "A-AN02",
            "titulo": f"AN-02 Subfaturamento (Eixo I) — {len(an02)} nota(s)",
            "descricao": (
                "R$/cabeça abaixo da pauta SEFAZ-GO. CRÍTICO se < R$ 1.000/cab; "
                "ATENÇÃO se R$ 1.000-1.500/cab. Pauta mínima SEFAZ-GO: "
                "R$ 1.385/cab (bezerra fêmea ≤ 12m)."),
            "severidade": "CRITICO" if crits else "ATENCAO",
            "porque_critico": (
                "Subfaturamento omite base de Funrural, IRPF Rural e reduz ICMS "
                "do estado-destino. Caracteriza dolo quando reiterado."),
            "cruzamentos": [
                "Pauta SEFAZ-GO vigente na data da operação",
                "GTA AGRODEFESA-GO (categoria/peso do animal)",
                "Extrato bancário (recebimento real vs declarado)",
            ],
            "tabela_cabecalhos": ["NFA-e", "Data", "R$/cab", "Cab",
                                    "Valor", "Destinatário"],
            "tabela_linhas": linhas,
            "tabela_totais": [],
        })
    if an03:
        crits = [a for a in an03 if a["tipo"] == "CRITICO"]
        linhas = [[
            a["nfa"], fmt_data_br(a["data"]),
            fmt_brl(a["rs_por_cabeca"]),
            str(a["cabecas"]), fmt_brl(a["valor"]),
            (a.get("remetente","—"))[:30],
        ] for a in an03[:15]]
        out.append({
            "codigo": "C-AN03" if crits else "A-AN03",
            "titulo": f"AN-03 Superfaturamento de compras (Eixo I) — {len(an03)} compra(s)",
            "descricao": (
                "R$/cabeça acima da pauta SEFAZ-GO máxima (R$ 8.500/cab "
                "touro reprodutor). CRÍTICO > R$ 20.000/cab; ATENÇÃO "
                "R$ 12.000-20.000/cab."),
            "severidade": "CRITICO" if crits else "ATENCAO",
            "porque_critico": (
                "Compra inflada caracteriza superfaturamento reverso — "
                "infla F6 (despesa) e reduz F5 (lucro tributável)."),
            "cruzamentos": [
                "Pauta SEFAZ-GO vigente",
                "Comprovação da finalidade (touro, matriz especial?)",
                "Extrato bancário (pagamento real)",
            ],
            "tabela_cabecalhos": ["NFA-e", "Data", "R$/cab", "Cab",
                                    "Valor", "Remetente"],
            "tabela_linhas": linhas,
            "tabela_totais": [],
        })
    return out


def conv_an08(an08: list[dict]) -> list[dict]:
    if not an08: return []
    crit = any(a["tipo"] == "CRITICO" for a in an08)
    linhas = [[
        (a.get("destinatario","—"))[:35],
        a.get("cpf","—"),
        " + ".join(a.get("sobrenomes_raros") or a.get("sobrenomes_comuns", [])),
        str(a.get("qtd_notas",0)),
        fmt_brl(a.get("valor_total",0)),
    ] for a in an08]
    return [{
        "codigo": "C-AN08" if crit else "A-AN08",
        "titulo": f"AN-08 Transferência intrafamiliar (Eixo II) — {len(an08)} destinatário(s)",
        "descricao": (
            "Destinatário compartilha sobrenome RARO com o contribuinte "
            "(sobrenomes ultra-comuns SILVA/SANTOS excluídos). Indica venda "
            "disfarçada entre familiares — burla potencial a ITCMD/ITBI."),
        "severidade": "CRITICO" if crit else "ATENCAO",
        "porque_critico": (
            "Transferências familiares simuladas como venda burlam imposto "
            "sobre doação (ITCMD) e podem caracterizar planejamento abusivo."),
        "cruzamentos": [
            "Certidão de relacionamento (cartório/Receita)",
            "Extrato bancário (verificar pagamento real entre as partes)",
            "Imposto sobre doação (ITCMD) recolhido no exercício",
        ],
        "tabela_cabecalhos": ["Destinatário", "CPF", "Sobrenomes", "Notas", "Valor"],
        "tabela_linhas": linhas,
        "tabela_totais": [],
    }]


def conv_an11(an11: list[dict]) -> list[dict]:
    if not an11: return []
    crit = any(a["tipo"] == "CRITICO" for a in an11)
    linhas = [[
        a["mes"], fmt_pct(a["pct"]),
        fmt_brl(a["valor"]), str(a["qtd_notas"]),
    ] for a in an11]
    return [{
        "codigo": "A-AN11",
        "titulo": f"AN-11 Sazonalidade incompatível (Eixo III)",
        "descricao": (
            "Ciclo pecuário tipicamente distribui receita ao longo de 6-9 meses. "
            "Concentração ≥50% em 1 mês = CRÍTICO; ≥30% = ATENÇÃO. Pode indicar "
            "operação sazonal atípica ou ciclo pontual de descapitalização."),
        "severidade": "ALTO" if crit else "ATENCAO",
        "porque_critico": (
            "Concentração temporal isolada é incompatível com ciclo pecuário "
            "padrão e pode mascarar evento de descapitalização total do plantel."),
        "cruzamentos": [
            "Evolução mensal do estoque (LCDPR)",
            "GTAs AGRODEFESA-GO emitidas no mês",
            "Capacidade do imóvel rural ao longo do ano",
        ],
        "tabela_cabecalhos": ["Mês", "% receita", "Valor", "Qtd notas"],
        "tabela_linhas": linhas,
        "tabela_totais": [],
    }]


def conv_an14(an14: list[dict]) -> list[dict]:
    if not an14: return []
    linhas = [[
        str(a["dias_entre"]),
        f"{fmt_data_br(a['compra_data'])} · {a['compra_remetente'][:22]}",
        f"{fmt_data_br(a['venda_data'])} · {a['venda_destinatario'][:22]}",
        str(a["venda_cabecas"]),
        fmt_brl(a["venda_valor"]),
    ] for a in an14[:15]]
    return [{
        "codigo": "A-AN14",
        "titulo": f"AN-14 Ciclo operacional implausível (Eixo IV) — {len(an14)} ocorrência(s)",
        "descricao": (
            "Compra (PDF DEST) e revenda (PDF REM) do mesmo lote em janela "
            "&lt; 60 dias — incompatível com ciclo de recria/engorda. Indício "
            "de AN-17 (cascata) ou AN-16 (carrossel)."),
        "severidade": "ATENCAO",
        "porque_critico": (
            "Ciclo pecuário formal (recria 8-12m, engorda 4-6m) torna inviável "
            "valorização em <60d. Padrão típico de trader/intermediário não "
            "declarado."),
        "cruzamentos": [
            "GTA AGRODEFESA-GO entrada e saída (verificar mesma identificação)",
            "Notas de despesa (alimentação, manejo) no intervalo",
            "CAEPF do contribuinte (atividade pecuária real?)",
        ],
        "tabela_cabecalhos": ["Dias", "Compra (Remetente)",
                                "Venda (Destinatário)", "Cab", "Valor venda"],
        "tabela_linhas": linhas,
        "tabela_totais": [],
    }]


def conv_an17(cascatas: list[dict]) -> list[dict]:
    if not cascatas: return []
    linhas = [[
        c.get("b_nome","—")[:30],
        c.get("c_nome","—")[:30],
        fmt_data_br(c["a_para_b_data"]),
        fmt_data_br(c["b_para_c_data"]),
        str(c["dias_entre"]),
    ] for c in cascatas[:15]]
    return [{
        "codigo": "C-AN17",
        "titulo": f"AN-17 Emissão em cascata (Eixo V) — {len(cascatas)} cadeia(s)",
        "descricao": (
            "Gado deste cliente (A) foi vendido a outro cliente da carteira (B) "
            "e revendido a um terceiro (C) dentro de 60 dias. Identifica B como "
            "possível <b>trader intermediário</b> (não produtor rural real). "
            "Padrão Eixo V — esquema estruturado de circulação de gado."),
        "severidade": "ALTO",
        "porque_critico": (
            "Cascatas A→B→C de curta duração caracterizam B como interposta "
            "pessoa (AN-05) ou intermediário não declarado (AN-07), gerando "
            "créditos fictícios de Funrural e elusão de IRPF Rural."),
        "cruzamentos": [
            "GTA AGRODEFESA-GO (rastrear identificação do gado entre as 3 partes)",
            "CAEPF do cliente B (atividade rural real?)",
            "Extrato bancário do cliente B (margem real da operação)",
            "Notas de despesa de B no período (alimentação/manejo)",
        ],
        "tabela_cabecalhos": ["B (intermediário)", "C (final)",
                                "Data A→B", "Data B→C", "Dias"],
        "tabela_linhas": linhas,
        "tabela_totais": [],
    }]


# ── Orquestração ─────────────────────────────────────────────────────────

def montar_resultado_endurecido(base_v2: dict, fh: dict, fan: dict,
                                  cascatas: list[dict]) -> dict:
    """Substitui achados do auditoria_v2 com os achados endurecidos."""
    r = deepcopy(base_v2)

    criticos = []
    medios = []
    atencao = []

    # T-01 (CRITICO direto)
    for a in conv_t01(fh.get("t01") or []):
        (criticos if a["severidade"] == "CRITICO" else atencao).append(a)
    # T-02 (CRITICO)
    criticos += conv_t02(fh.get("t02") or [])
    # T-03 (CRITICO ou ATENCAO)
    for a in conv_t03(fh.get("t03") or {}):
        if a["severidade"] == "CRITICO": criticos.append(a)
        elif a["severidade"] == "ALTO": medios.append(a)
        else: atencao.append(a)
    # T-04 (ALTO ou ATENCAO)
    for a in conv_t04(fh.get("t04") or {}):
        if a["severidade"] == "ALTO": medios.append(a)
        else: atencao.append(a)
    # AN-02/03
    for a in conv_an02_03(fan.get("an02", []), fan.get("an03", [])):
        if a["severidade"] == "CRITICO": criticos.append(a)
        else: atencao.append(a)
    # AN-08
    for a in conv_an08(fan.get("an08", [])):
        if a["severidade"] == "CRITICO": criticos.append(a)
        else: atencao.append(a)
    # AN-11
    for a in conv_an11(fan.get("an11", [])):
        if a["severidade"] == "ALTO": medios.append(a)
        else: atencao.append(a)
    # AN-14 (sempre ATENCAO)
    atencao += conv_an14(fan.get("an14", []))
    # AN-17 (ALTO)
    medios += conv_an17(cascatas)

    # Preserva M-01 (LCDPR) e M-02 (Funrural) do base_v2 — sempre úteis
    base_medios = [m for m in (base_v2.get("achados_medios") or [])
                    if m["codigo"] in ("M-01", "M-02")]
    medios = base_medios + medios

    r["achados_criticos"] = criticos
    r["achados_medios"] = medios
    r["pontos_atencao"] = atencao
    r["severidades"] = {
        "CRITICO": sum(1 for a in criticos if a["severidade"] == "CRITICO"),
        "ALTO": sum(1 for a in criticos + medios if a["severidade"] == "ALTO"),
        "MEDIO": sum(1 for a in medios if a["severidade"] == "MEDIO"),
        "ATENCAO": sum(1 for a in atencao if a["severidade"] == "ATENCAO"),
        "CONFORME": 0,
    }
    # Reset hash (não é mais o hash original)
    r["sistema"] = "OrgAudi 1.1 — Bateria Endurecida T-01..T-08 + AN-02..AN-17"
    r["timestamp"] = datetime.now().isoformat()

    return r


def main() -> None:
    if not ARQ_HARD.exists() or not ARQ_AN18.exists():
        print(f"[ERRO] JSONs ausentes:\n  {ARQ_HARD}\n  {ARQ_AN18}")
        return

    hard = json.loads(ARQ_HARD.read_text(encoding="utf-8"))
    an18 = json.loads(ARQ_AN18.read_text(encoding="utf-8"))
    hard_por_slug = {h["slug"]: h for h in hard}
    an_por_slug = {a["slug"]: a for a in an18["por_cliente"]}

    cascatas_por_slug = {}
    cpf_para_slug = {a.get("contribuinte_cpf"): a["slug"]
                      for a in an18["por_cliente"] if a.get("contribuinte_cpf")}
    for c in an18.get("an17_cascata", []):
        slug_a = cpf_para_slug.get(c["a_cpf"])
        if slug_a:
            cascatas_por_slug.setdefault(slug_a, []).append(c)

    print(f"{'CLIENTE':45s} {'STATUS':>10s}  {'TAMANHO'}")
    print("=" * 100)
    gerados = []
    for slug in hard_por_slug:
        fh = hard_por_slug[slug]
        if fh.get("qtd_notas", 0) == 0:
            print(f"{slug:45s} {'SKIP':>10s}  (0 notas)")
            continue
        base_path = RAIZ / "outputs" / slug / "auditoria_v2.json"
        if not base_path.exists():
            print(f"{slug:45s} {'SEM_BASE':>10s}  (gerar auditoria_v2 primeiro)")
            continue
        base_v2 = json.loads(base_path.read_text(encoding="utf-8"))
        fan = an_por_slug.get(slug, {})
        cascatas = cascatas_por_slug.get(slug, [])

        try:
            resultado = montar_resultado_endurecido(base_v2, fh, fan, cascatas)
            pdf_bytes = gerar_pdf_auditoria_cruzada(resultado, modo="simplificado")
            arq = DEST / f"LAUDO_FORENSE_HARD_{slug}_{DATA}.pdf"
            arq.write_bytes(pdf_bytes)
            gerados.append(arq)
            print(f"{slug:45s} {'OK':>10s}  {len(pdf_bytes)/1024:.1f} KB")
        except Exception as e:
            print(f"{slug:45s} {'ERRO':>10s}  {e}")

    print(f"\n[OK] {len(gerados)} PDFs gerados em {DEST}")


if __name__ == "__main__":
    main()
