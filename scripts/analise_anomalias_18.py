"""scripts/analise_anomalias_18.py

Detectores complementares cobrindo o catálogo AN-01..AN-18 do skill_rural.
Foco aqui: anomalias **automatizáveis** sem APIs externas, que NÃO eram
cobertas por analise_forense_completa.py (T-01..T-08).

  • AN-02  Subfaturamento     — R$/cabeça fora da faixa pauta SEFAZ-GO
  • AN-03  Superfaturamento   — compras com R$/cabeça > 1.5× máx pauta
  • AN-08  Intrafamiliar      — destinatário com sobrenome do contribuinte
  • AN-11  Sazonalidade       — concentração mensal atípica (>30% em 1 mês)
  • AN-14  Ciclo curto        — compra (DEST) e venda (REM) em <60 dias do
                                MESMO CPF (mesmo gado revendido rapidamente)
  • AN-16  Carrossel          — A vende para B E B vende para A no mesmo ano
  • AN-17  Cascata            — gado A→B→C entre clientes da carteira

NÃO automatizáveis (dependem de bases externas):
  AN-04, AN-05, AN-06, AN-07, AN-09, AN-10, AN-12, AN-15, AN-18

Saída:
  reports_nfa/ANOMALIAS_AN18_<data>.json
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DEST = RAIZ / "reports_nfa"
PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")

PDFS_TO = RAIZ / "data"

MAPA_PDFS = {
    "DEUSDETE": "deusdete_2025",
    "ADELA": "adela_fernanda_silva_santos_2025",
    "CLEITON": "cleiton_barbosa_santos_2025",
    "CLEUZENIR": "cleuzenir_rodrigues_de_almeida_2025",
    "ETERVALDO": "etervaldo_goncalves_da_cruz_2025",
    "FABIO": "fabio_humberto_ribeiro_santos_2025",
    "GEAN": "gean_oliveira_maia_2025",
    "GENIS": "genis_2025",
    "GEOVANE": "geovane_alves_vieira_2025",
    "GERALDO": "geraldo_martins_da_costa_2025",
    "GLAUBER": "glauber_tassi_de_souza_2025",
    "HELIO JOSE": "helio_jose_alves_da_silva_2025",
    "HELLIDA": "hellida_patricia_oliveira_camilo_pereira_2025",
    "JOSE AILTON": "jose_ailton_goncalves_da_silva_2025",
    "JOSE NELSON": "jose_nelson_fernandes_2025",
    "JOSMAIR": "josmair_pires_do_carmo_2025",
    "LAELSON": "laelson_rodrigues_de_souza_2025",
    "LEANDRO": "leandro_jose_da_silva_2025",
    "MARGARETH": "margareth_moreira_mendes_2025",
    "MARILZA": "marilza_pereira_dos_santos_2025",
    "MATHEUS": "matheus_bernardes_silva_mendes_2025",
    "RAUL": "raul_alves_de_aquino_2025",
    "RICARDO LOBO": "ricardo_de_souza_lobo_2025",
    "WANDERLINA": "wanderlina_lima_de_morais_tassi_2025",
}

# ── Pauta SEFAZ-GO (faixas R$/cabeça válidas em 2025) ─────────────────────
PAUTA_MIN = Decimal("1385")   # bezerra fêmea mais barata
PAUTA_MAX = Decimal("8500")   # touro reprodutor mais caro
PAUTA_MEDIA = Decimal("3500") # referência para sub/super

# ── Limiares ──────────────────────────────────────────────────────────────
LIM_AN02_ABS = Decimal("1000")   # R$/cab < 1000 = subfat. crítico
LIM_AN02_BAIXO = Decimal("1500") # R$/cab 1000-1500 = atenção
LIM_AN03_ALTO = Decimal("12000") # R$/cab > 12k = superfat. atenção
LIM_AN03_CRIT = Decimal("20000") # R$/cab > 20k = crítico
LIM_AN11_PCT = Decimal("30")     # >30% de receita em 1 mês = ATENÇÃO
LIM_AN11_CRIT = Decimal("50")    # >50% em 1 mês = CRÍTICO
LIM_AN14_DIAS = 60               # ciclo recria/engorda mínimo


# ── Utilitários ──────────────────────────────────────────────────────────

def ler_pdf(p: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(p), "-"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    ).stdout


def parse_brl(s: str) -> Decimal:
    s = s.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try: return Decimal(s)
    except Exception: return Decimal(0)


def parsear_notas(texto: str) -> list[dict]:
    """Extrai notas COM cabeças (campo Quantidade)."""
    blocos = re.split(r"IDENTIFICA[CA]?AO DA NOTA", texto, flags=re.IGNORECASE)[1:]
    if blocos and "RESUMO" in blocos[-1]:
        blocos[-1] = blocos[-1].split("RESUMO")[0]
    out = []
    for b in blocos:
        m = re.search(
            r"(\d{7,9})\s+(\d{2})/(\d{2})/(\d{4})\s+"
            r"(VENDA|REMESSA/LEILAO|OUTRA\s+REMESSAS|DEVOLU[CC]AO|COMPRA)", b)
        if not m: continue
        nat = re.sub(r"\s+", " ", m.group(5).strip())
        valor_total = Decimal(0)
        for v in re.findall(r"R\$\s*([\d.]+,\d{2})", b):
            n = parse_brl(v)
            if n > 0: valor_total += n
        # Cabeças (regex robusto)
        cabecas = sum(
            int(c) for c in re.findall(
                r"(?<!R\$\s)(?<!R\$)(?<![.\d])(\d+),00\b(?!\s*\d)", b)
            if int(c) > 0)
        # Destinatário
        d_nome, d_cpf = "—", "—"
        linhas = b.split("\n")
        for idx, l in enumerate(linhas):
            if re.match(r"\s*DESTINAT", l, re.IGNORECASE):
                for prox in linhas[idx + 1:idx + 6]:
                    if not prox.strip(): continue
                    md = re.match(
                        r"\s*(.+?)\s{2,}(\d+)\s+"
                        r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
                        prox)
                    if md:
                        d_nome, d_cpf = md.group(1).strip(), md.group(3)
                    break
                break
        # Remetente (mesmo padrão antes de DESTINATÁRIO)
        r_nome, r_cpf = "—", "—"
        for idx, l in enumerate(linhas):
            if re.match(r"\s*REMETENTE", l, re.IGNORECASE):
                for prox in linhas[idx + 1:idx + 6]:
                    if not prox.strip(): continue
                    mr = re.match(
                        r"\s*(.+?)\s{2,}(\d+)\s+"
                        r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
                        prox)
                    if mr:
                        r_nome, r_cpf = mr.group(1).strip(), mr.group(3)
                    break
                break
        out.append({
            "nfa": m.group(1),
            "data": f"{m.group(4)}-{m.group(3)}-{m.group(2)}",
            "natureza": nat,
            "valor": valor_total,
            "cabecas": cabecas,
            "dest_nome": d_nome, "dest_cpf": d_cpf,
            "rem_nome": r_nome, "rem_cpf": r_cpf,
        })
    return out


def localizar_pdfs(prefixo: str) -> tuple[Path | None, Path | None]:
    dest = next(iter(PDFS.glob(f"{prefixo} *DEST*.pdf")), None)
    rem = next(iter(PDFS.glob(f"{prefixo} *REM*.pdf")), None) \
          or next(iter(PDFS.glob(f"{prefixo}*REM*.pdf")), None)
    return dest, rem


# ── Detectores AN-02 .. AN-17 ────────────────────────────────────────────

def an02_subfaturamento(notas: list[dict]) -> list[dict]:
    """AN-02: R$/cabeça abaixo de R$ 1.500 (≈ min pauta SEFAZ-GO bezerra)."""
    achados = []
    for n in notas:
        if n["natureza"] != "VENDA" or n["cabecas"] <= 0: continue
        rs_cab = n["valor"] / n["cabecas"]
        if rs_cab < LIM_AN02_ABS:
            tipo = "CRITICO"
        elif rs_cab < LIM_AN02_BAIXO:
            tipo = "ATENCAO"
        else:
            continue
        achados.append({
            "tipo": tipo,
            "nfa": n["nfa"], "data": n["data"],
            "destinatario": n["dest_nome"], "cpf": n["dest_cpf"],
            "valor": n["valor"], "cabecas": n["cabecas"],
            "rs_por_cabeca": float(rs_cab),
            "pauta_min_referencia": float(LIM_AN02_BAIXO),
        })
    return achados


def an03_superfaturamento(notas_dest: list[dict]) -> list[dict]:
    """AN-03: COMPRAS com R$/cabeça muito acima da pauta (inflação despesa)."""
    achados = []
    for n in notas_dest:
        if n["cabecas"] <= 0: continue
        rs_cab = n["valor"] / n["cabecas"]
        if rs_cab > LIM_AN03_CRIT:
            tipo = "CRITICO"
        elif rs_cab > LIM_AN03_ALTO:
            tipo = "ATENCAO"
        else:
            continue
        achados.append({
            "tipo": tipo,
            "nfa": n["nfa"], "data": n["data"],
            "remetente": n["rem_nome"], "cpf": n["rem_cpf"],
            "valor": n["valor"], "cabecas": n["cabecas"],
            "rs_por_cabeca": float(rs_cab),
            "pauta_max_referencia": float(LIM_AN03_ALTO),
        })
    return achados


def _sobrenomes(nome: str) -> set[str]:
    """Extrai conjuntos de sobrenomes (palavras 4+ letras, exceto preposições
    e sobrenomes brasileiros ultra-comuns que geram falso positivo)."""
    stop = {"DA", "DE", "DO", "DAS", "DOS", "E", "JUNIOR", "FILHO", "NETO"}
    # Sobrenomes ultra-comuns no Brasil (top 10 IBGE) — exigem ≥2 match p/ contar
    return {p for p in re.split(r"\s+", nome.upper())
            if len(p) >= 4 and p not in stop and p.isalpha()}


SOBRENOMES_COMUNS = {"SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "SOUSA",
                      "PEREIRA", "RIBEIRO", "RODRIGUES", "FERREIRA", "ALVES",
                      "GOMES", "MARTINS", "LIMA", "COSTA", "BARBOSA"}


def an08_intrafamiliar(contribuinte_nome: str, notas: list[dict]) -> list[dict]:
    """AN-08: destinatário compartilha sobrenome RARO com contribuinte.

    Filtro endurecido: ignora matches só com sobrenomes ultra-comuns
    (SILVA, SANTOS, etc.) — exige ≥1 sobrenome fora da lista comum,
    OU ≥2 sobrenomes em comum (mesmo que ambos comuns).
    """
    sobr_contrib = _sobrenomes(contribuinte_nome)
    if not sobr_contrib: return []
    sobr_raros_contrib = sobr_contrib - SOBRENOMES_COMUNS
    achados = []
    visto = set()
    for n in notas:
        if n["natureza"] != "VENDA" or n["dest_cpf"] == "—": continue
        if n["dest_cpf"] in visto: continue
        sobr_dest = _sobrenomes(n["dest_nome"])
        comum = sobr_contrib & sobr_dest
        # Filtro: precisa de ao menos 1 sobrenome RARO, OU ≥2 sobrenomes
        comum_raros = comum - SOBRENOMES_COMUNS
        if not comum_raros and len(comum) < 2:
            continue
        visto.add(n["dest_cpf"])
        notas_dest = [m for m in notas
                      if m["natureza"] == "VENDA" and m["dest_cpf"] == n["dest_cpf"]]
        soma = sum((m["valor"] for m in notas_dest), Decimal(0))
        achados.append({
            "tipo": "CRITICO" if comum_raros else "ATENCAO",
            "destinatario": n["dest_nome"], "cpf": n["dest_cpf"],
            "sobrenomes_comuns": sorted(comum),
            "sobrenomes_raros": sorted(comum_raros),
            "qtd_notas": len(notas_dest),
            "valor_total": soma,
        })
    return achados


def an11_sazonalidade(notas: list[dict]) -> list[dict]:
    """AN-11: 1 mês concentra >30% (atenção) ou >50% (crítico) da receita."""
    vendas = [n for n in notas if n["natureza"] == "VENDA"]
    total = sum((n["valor"] for n in vendas), Decimal(0))
    if total <= 0: return []
    por_mes = defaultdict(lambda: Decimal(0))
    for n in vendas:
        mes = n["data"][:7]  # YYYY-MM
        por_mes[mes] += n["valor"]
    achados = []
    for mes, valor in por_mes.items():
        pct = valor / total * 100
        if pct >= LIM_AN11_CRIT:
            tipo = "CRITICO"
        elif pct >= LIM_AN11_PCT:
            tipo = "ATENCAO"
        else:
            continue
        qtd = sum(1 for n in vendas if n["data"].startswith(mes))
        achados.append({
            "tipo": tipo, "mes": mes,
            "pct": float(pct), "valor": valor, "qtd_notas": qtd,
        })
    return sorted(achados, key=lambda a: -a["pct"])


def an14_ciclo_curto(notas_dest: list[dict], notas_rem: list[dict]) -> list[dict]:
    """AN-14: compra (em DEST) seguida de venda (em REM) em <60 dias.

    Detecta quando há COMPRA de fornecedor X e VENDA para destinatário Y
    em janela < 60 dias — sugere passagem rápida sem recria real.
    """
    achados = []
    vendas = [n for n in notas_rem if n["natureza"] == "VENDA"]
    compras = [n for n in notas_dest if n["natureza"] in ("VENDA", "REMESSA/LEILAO",
                                                            "OUTRA REMESSAS", "COMPRA")]
    if not vendas or not compras: return achados

    # Para cada venda, busca compra anterior dentro de 60d com cabeças >= venda
    for v in vendas:
        if v["cabecas"] <= 0: continue
        dv = datetime.fromisoformat(v["data"])
        for c in compras:
            if c["cabecas"] <= 0: continue
            dc = datetime.fromisoformat(c["data"])
            delta = (dv - dc).days
            if 0 <= delta < LIM_AN14_DIAS and c["cabecas"] >= v["cabecas"]:
                achados.append({
                    "tipo": "ATENCAO",
                    "venda_nfa": v["nfa"], "venda_data": v["data"],
                    "venda_destinatario": v["dest_nome"],
                    "venda_cabecas": v["cabecas"], "venda_valor": v["valor"],
                    "compra_nfa": c["nfa"], "compra_data": c["data"],
                    "compra_remetente": c["rem_nome"],
                    "compra_cabecas": c["cabecas"], "compra_valor": c["valor"],
                    "dias_entre": delta,
                })
                break  # uma correspondência por venda
    return achados


def an16_carrossel_intercliente(carteira: dict[str, dict]) -> list[dict]:
    """AN-16: cliente A vende para B E B vende para A no mesmo ano."""
    # Mapa cpf_contribuinte -> nome
    cpf_para_nome = {}
    # Mapa (origem_cpf, dest_cpf) -> {qtd, valor}
    edges = defaultdict(lambda: {"qtd": 0, "valor": Decimal(0)})
    for slug, dados in carteira.items():
        cpf_orig = dados.get("contribuinte_cpf", "")
        nome_orig = dados.get("contribuinte_nome", slug)
        if cpf_orig: cpf_para_nome[cpf_orig] = nome_orig
        for n in dados.get("notas_rem", []):
            if n["natureza"] != "VENDA": continue
            cpf_dest = n["dest_cpf"]
            edges[(cpf_orig, cpf_dest)]["qtd"] += 1
            edges[(cpf_orig, cpf_dest)]["valor"] += n["valor"]

    achados = []
    visto = set()
    for (a, b), info_ab in edges.items():
        if a == b or a == "" or b == "—" or b == "": continue
        chave = tuple(sorted([a, b]))
        if chave in visto: continue
        # Procura aresta inversa
        info_ba = edges.get((b, a))
        if info_ba:
            visto.add(chave)
            achados.append({
                "tipo": "CRITICO",
                "cliente_a_cpf": a, "cliente_a_nome": cpf_para_nome.get(a, a),
                "cliente_b_cpf": b, "cliente_b_nome": cpf_para_nome.get(b, b),
                "a_para_b": {"qtd": info_ab["qtd"], "valor": info_ab["valor"]},
                "b_para_a": {"qtd": info_ba["qtd"], "valor": info_ba["valor"]},
            })
    return achados


def an17_cascata(carteira: dict[str, dict]) -> list[dict]:
    """AN-17: cadeia A → B → C com ORDEM TEMPORAL CORRETA.

    B vende para C DEPOIS de receber de A, dentro de janela ≤ 60 dias.
    """
    JANELA_DIAS = 60
    cpf_cliente = {d["contribuinte_cpf"]: slug
                    for slug, d in carteira.items() if d.get("contribuinte_cpf")}
    nome_cliente = {d["contribuinte_cpf"]: d["contribuinte_nome"]
                     for slug, d in carteira.items() if d.get("contribuinte_cpf")}

    achados = []
    for slug_a, dados_a in carteira.items():
        cpf_a = dados_a.get("contribuinte_cpf", "")
        for n in dados_a.get("notas_rem", []):
            if n["natureza"] != "VENDA": continue
            cpf_b = n["dest_cpf"]
            if cpf_b not in cpf_cliente: continue
            slug_b = cpf_cliente[cpf_b]
            data_ab = datetime.fromisoformat(n["data"])
            # B vendeu DEPOIS de receber? Mesma janela <=60d
            for m in carteira[slug_b].get("notas_rem", []):
                if m["natureza"] != "VENDA": continue
                if m["dest_cpf"] in (cpf_a, "—"): continue
                data_bc = datetime.fromisoformat(m["data"])
                delta = (data_bc - data_ab).days
                if not (0 <= delta <= JANELA_DIAS): continue
                achados.append({
                    "tipo": "CRITICO",
                    "a_cpf": cpf_a, "a_nome": nome_cliente.get(cpf_a, slug_a),
                    "b_cpf": cpf_b, "b_nome": nome_cliente.get(cpf_b, slug_b),
                    "c_cpf": m["dest_cpf"], "c_nome": m["dest_nome"],
                    "a_para_b_nfa": n["nfa"], "a_para_b_data": n["data"],
                    "a_para_b_valor": n["valor"], "a_para_b_cab": n["cabecas"],
                    "b_para_c_nfa": m["nfa"], "b_para_c_data": m["data"],
                    "b_para_c_valor": m["valor"], "b_para_c_cab": m["cabecas"],
                    "dias_entre": delta,
                })
                break
    return achados[:100]


# ── Orquestração ─────────────────────────────────────────────────────────

def carregar_contribuinte(slug: str) -> tuple[str, str]:
    """Retorna (nome, cpf) do contribuinte a partir do JSON em scripts/clientes."""
    p = RAIZ / "scripts" / "clientes" / f"{slug}.json"
    if not p.exists(): return slug, ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        # Schema flat (atual): chaves no top-level
        nome = d.get("contribuinte_nome") or d.get("contribuinte", {}).get("nome", slug)
        cpf = d.get("contribuinte_cpf") or d.get("contribuinte", {}).get("cpf", "")
        return nome, cpf
    except Exception:
        return slug, ""


def main() -> None:
    print(f"{'CLIENTE':45s} {'V':>4s} {'C':>4s} {'AN02':>5s} {'AN03':>5s} "
           f"{'AN08':>5s} {'AN11':>5s} {'AN14':>5s}")
    print("=" * 90)

    carteira: dict[str, dict] = {}
    consolidado = []

    for prefixo, slug in MAPA_PDFS.items():
        nome_contrib, cpf_contrib = carregar_contribuinte(slug)
        if prefixo == "DEUSDETE":
            from parser_deusdete_to import parsear_notas_deusdete
            saidas = PDFS_TO / "DEUSDETE_SAIDAS_2025.pdf"
            entradas = PDFS_TO / "DEUSDETE_ENTRADAS_2025.pdf"
            notas_rem = parsear_notas_deusdete(saidas) if saidas.exists() else []
            notas_dest = parsear_notas_deusdete(entradas) if entradas.exists() else []
        else:
            dest_pdf, rem_pdf = localizar_pdfs(prefixo)
            notas_rem = parsear_notas(ler_pdf(rem_pdf)) if rem_pdf else []
            notas_dest = parsear_notas(ler_pdf(dest_pdf)) if dest_pdf else []

        carteira[slug] = {
            "contribuinte_nome": nome_contrib,
            "contribuinte_cpf": cpf_contrib,
            "notas_rem": notas_rem,
            "notas_dest": notas_dest,
        }

        an02 = an02_subfaturamento(notas_rem)
        an03 = an03_superfaturamento(notas_dest)
        an08 = an08_intrafamiliar(nome_contrib, notas_rem)
        an11 = an11_sazonalidade(notas_rem)
        an14 = an14_ciclo_curto(notas_dest, notas_rem)

        consolidado.append({
            "slug": slug, "prefixo": prefixo,
            "contribuinte_nome": nome_contrib, "contribuinte_cpf": cpf_contrib,
            "qtd_vendas": sum(1 for n in notas_rem if n["natureza"] == "VENDA"),
            "qtd_compras": len(notas_dest),
            "an02": an02, "an03": an03, "an08": an08, "an11": an11, "an14": an14,
        })
        print(f"{slug:45s} {sum(1 for n in notas_rem if n['natureza']=='VENDA'):>4d} "
               f"{len(notas_dest):>4d} {len(an02):>5d} {len(an03):>5d} "
               f"{len(an08):>5d} {len(an11):>5d} {len(an14):>5d}")

    # AN-16 e AN-17 são análises de rede da carteira inteira
    print("\n" + "=" * 90)
    print("ANÁLISE DE REDE (AN-16 Carrossel + AN-17 Cascata)")
    print("=" * 90)
    an16 = an16_carrossel_intercliente(carteira)
    an17 = an17_cascata(carteira)
    print(f"AN-16 CARROSSEL: {len(an16)} par(es) cliente↔cliente bidirecional")
    for a in an16:
        print(f"  • {a['cliente_a_nome']} ↔ {a['cliente_b_nome']}")
        print(f"    A→B: {a['a_para_b']['qtd']} notas, R$ {a['a_para_b']['valor']:,.2f}")
        print(f"    B→A: {a['b_para_a']['qtd']} notas, R$ {a['b_para_a']['valor']:,.2f}")

    print(f"\nAN-17 CASCATA: {len(an17)} cadeia(s) A→B→C")
    for a in an17[:15]:
        print(f"  • {a['a_nome']} → {a['b_nome']} → {a['c_nome']}")
        print(f"    {a['a_para_b_data']} (NFA {a['a_para_b_nfa']}) → "
               f"{a['b_para_c_data']} (NFA {a['b_para_c_nfa']})")

    # JSON consolidado
    saida = DEST / f"ANOMALIAS_AN18_{datetime.now().strftime('%Y-%m-%d')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps({
        "por_cliente": consolidado,
        "an16_carrossel": an16,
        "an17_cascata": an17,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[OK] JSON consolidado: {saida}")

    # Detalhamento por cliente
    print()
    print("=" * 90)
    print("DETALHAMENTO POR CLIENTE")
    print("=" * 90)
    for c in consolidado:
        if not (c["an02"] or c["an03"] or c["an08"] or c["an11"] or c["an14"]):
            continue
        print(f"\n>>> {c['prefixo']}")
        if c["an02"]:
            crits = [a for a in c["an02"] if a["tipo"] == "CRITICO"]
            ates = [a for a in c["an02"] if a["tipo"] == "ATENCAO"]
            if crits:
                print(f"  AN-02 SUBFATURAMENTO CRITICO: {len(crits)} nota(s) <R$ 1.000/cab")
                for a in crits[:3]:
                    print(f"    • NFA {a['nfa']} {a['data']}: R$ {a['rs_por_cabeca']:,.2f}/cab "
                           f"({a['cabecas']} cab, R$ {a['valor']:,.2f}) - {a['destinatario']}")
            if ates:
                print(f"  AN-02 SUBFATURAMENTO ATENCAO: {len(ates)} nota(s) R$ 1.000-1.500/cab")
        if c["an03"]:
            crits = [a for a in c["an03"] if a["tipo"] == "CRITICO"]
            ates = [a for a in c["an03"] if a["tipo"] == "ATENCAO"]
            if crits:
                print(f"  AN-03 SUPERFATURAMENTO CRITICO: {len(crits)} compra(s) >R$ 20k/cab")
                for a in crits[:3]:
                    print(f"    • NFA {a['nfa']} {a['data']}: R$ {a['rs_por_cabeca']:,.2f}/cab "
                           f"({a['cabecas']} cab) - {a['remetente']}")
            if ates:
                print(f"  AN-03 SUPERFATURAMENTO ATENCAO: {len(ates)} compra(s) R$ 12-20k/cab")
                for a in ates[:3]:
                    print(f"    • NFA {a['nfa']} {a['data']}: R$ {a['rs_por_cabeca']:,.2f}/cab")
        if c["an08"]:
            print(f"  AN-08 INTRAFAMILIAR: {len(c['an08'])} destinatário(s) com sobrenome do contribuinte")
            for a in c["an08"][:3]:
                print(f"    • {a['destinatario']} - sobrenomes {a['sobrenomes_comuns']} - "
                       f"{a['qtd_notas']} notas, R$ {a['valor_total']:,.2f}")
        if c["an11"]:
            crits = [a for a in c["an11"] if a["tipo"] == "CRITICO"]
            ates = [a for a in c["an11"] if a["tipo"] == "ATENCAO"]
            if crits:
                print(f"  AN-11 SAZONALIDADE CRITICO: {len(crits)} mês(es) com >50% da receita")
                for a in crits[:3]:
                    print(f"    • {a['mes']}: {a['pct']:.1f}% (R$ {a['valor']:,.2f} em {a['qtd_notas']} notas)")
            if ates:
                for a in ates[:2]:
                    print(f"  AN-11 SAZONALIDADE ATENCAO: {a['mes']} = {a['pct']:.1f}% da receita")
        if c["an14"]:
            print(f"  AN-14 CICLO CURTO: {len(c['an14'])} venda(s) com compra recente (<60d)")
            for a in c["an14"][:3]:
                print(f"    • {a['dias_entre']}d: compra {a['compra_data']} ({a['compra_remetente']}) "
                       f"→ venda {a['venda_data']} ({a['venda_destinatario']}) "
                       f"- {a['venda_cabecas']} cab")


if __name__ == "__main__":
    main()
