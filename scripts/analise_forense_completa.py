"""scripts/analise_forense_completa.py

Bateria forense ENDURECIDA do skill_rural v1.1.0 sobre os PDFs GIEF
(NFE_GADO_2026). Limiares mais agressivos para reduzir falsos negativos:

  • T-01 Concentração Pontual  — ATENÇÃO ≥3% / CRÍTICO ≥7% da receita anual
  • T-02 Fragmentação Fiscal   — 4 subtipos:
        A) 3+ notas idênticas mesmo dia mesma contraparte
        B) 4+ notas em 7 dias mesma contraparte c/ 2+ valores iguais
        C) 2+ notas mesma data + mesma contraparte (qualquer valor)
        D) 3+ notas mesma contraparte em 30 dias, soma ≥ R$ 100k
  • T-03 Concentração de Contraparte (NOVO)
        ATENÇÃO: 1 contraparte concentra ≥20% da receita
        CRÍTICO: 1 contraparte concentra ≥30%
        CRÍTICO: TOP-3 contrapartes concentram ≥70%
  • T-04 Concentração PF      — ATENÇÃO ≥70% / CRÍTICO ≥85% c/ recorrência
  • T-08 Validação Documental — dígito CPF/CNPJ + CPF ausente em vendas

Saída:
  reports_nfa/ANALISE_FORENSE_<data>.json
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
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

# ── Limiares endurecidos ─────────────────────────────────────────────────
LIM_T01_ATENCAO = Decimal("3")     # % da receita anual
LIM_T01_CRITICO = Decimal("7")
LIM_T02_C_VALOR = Decimal("0")     # T-02-C: sem limiar de valor (qualquer)
LIM_T02_D_DIAS = 30
LIM_T02_D_SOMA = Decimal("100000")
LIM_T03_ATENCAO = Decimal("20")    # 1 contraparte
LIM_T03_CRITICO = Decimal("30")
LIM_T03_TOP3 = Decimal("70")       # soma TOP-3
LIM_T04_ATENCAO = Decimal("70")
LIM_T04_CRITICO = Decimal("85")
LIM_T08_CPF_AUSENTE_CRIT = 3       # 3+ vendas sem CPF informado


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


def validar_cpf(cpf: str) -> bool:
    c = "".join(d for d in cpf if d.isdigit())
    if len(c) != 11 or c == c[0] * 11:
        return False
    s = sum(int(c[i]) * (10 - i) for i in range(9))
    d1 = (s * 10) % 11
    if d1 == 10: d1 = 0
    if d1 != int(c[9]): return False
    s = sum(int(c[i]) * (11 - i) for i in range(10))
    d2 = (s * 10) % 11
    if d2 == 10: d2 = 0
    return d2 == int(c[10])


def validar_cnpj(cnpj: str) -> bool:
    c = "".join(d for d in cnpj if d.isdigit())
    if len(c) != 14 or c == c[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    s1 = sum(int(c[i]) * pesos1[i] for i in range(12))
    d1 = s1 % 11
    d1 = 0 if d1 < 2 else 11 - d1
    if d1 != int(c[12]): return False
    s2 = sum(int(c[i]) * pesos2[i] for i in range(13))
    d2 = s2 % 11
    d2 = 0 if d2 < 2 else 11 - d2
    return d2 == int(c[13])


def validar_documento(doc: str) -> bool:
    digs = "".join(d for d in doc if d.isdigit())
    if len(digs) == 11: return validar_cpf(doc)
    if len(digs) == 14: return validar_cnpj(doc)
    return False


# ── Parsing de notas ─────────────────────────────────────────────────────

def parsear_notas(texto: str) -> list[dict]:
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
        out.append({
            "nfa": m.group(1),
            "data": f"{m.group(4)}-{m.group(3)}-{m.group(2)}",
            "natureza": nat,
            "valor": valor_total,
            "dest_nome": d_nome,
            "dest_cpf": d_cpf,
        })
    return out


# ── Testes Forenses (endurecidos) ────────────────────────────────────────

def teste_t01_concentracao(notas: list[dict]) -> list[dict]:
    """T-01 endurecido: ATENÇÃO ≥3%, CRÍTICO ≥7% da receita anual."""
    vendas = [n for n in notas if n["natureza"] == "VENDA"]
    if not vendas: return []
    total = sum((n["valor"] for n in vendas), Decimal(0))
    if total <= 0: return []
    achados = []
    for n in vendas:
        pct = (n["valor"] / total * 100) if total else Decimal(0)
        if pct >= LIM_T01_CRITICO:
            tipo = "CRITICO"
        elif pct >= LIM_T01_ATENCAO:
            tipo = "ATENCAO"
        else:
            continue
        achados.append({
            "tipo": tipo,
            "nfa": n["nfa"], "data": n["data"],
            "destinatario": n["dest_nome"], "cpf": n["dest_cpf"],
            "valor": n["valor"], "pct": float(pct),
        })
    return achados


def teste_t02_smurfing(notas: list[dict]) -> list[dict]:
    """T-02 endurecido: 4 subtipos A/B/C/D."""
    vendas = [n for n in notas if n["natureza"] == "VENDA"]
    por_dest = defaultdict(list)
    for n in vendas: por_dest[n["dest_cpf"]].append(n)
    achados = []
    for cpf, lista in por_dest.items():
        if cpf == "—": continue
        lista.sort(key=lambda x: x["data"])
        d_nome = lista[0]["dest_nome"]

        # A) 3+ notas idênticas mesmo dia
        por_dia = defaultdict(list)
        for n in lista: por_dia[n["data"]].append(n)
        for dia, ds in por_dia.items():
            if len(ds) >= 3:
                iguais = max(Counter(n["valor"] for n in ds).values())
                if iguais >= 3:
                    achados.append({
                        "tipo": "CRITICO_A",
                        "destinatario": d_nome, "cpf": cpf, "data": dia,
                        "qtd_notas": len(ds), "qtd_iguais": iguais,
                        "valor_total": sum((n["valor"] for n in ds), Decimal(0)),
                        "notas": [n["nfa"] for n in ds],
                    })

        # C) 2+ notas mesma data + mesma contraparte (qualquer valor)
        for dia, ds in por_dia.items():
            if len(ds) >= 2:
                ja_em_a = any(
                    a["tipo"] == "CRITICO_A" and a["cpf"] == cpf and a["data"] == dia
                    for a in achados)
                if ja_em_a: continue
                achados.append({
                    "tipo": "CRITICO_C",
                    "destinatario": d_nome, "cpf": cpf, "data": dia,
                    "qtd_notas": len(ds),
                    "valor_total": sum((n["valor"] for n in ds), Decimal(0)),
                    "notas": [n["nfa"] for n in ds],
                })

        # B) 4+ notas em 7d, 2+ valores iguais
        if len(lista) >= 4:
            for i, n in enumerate(lista):
                d0 = datetime.fromisoformat(n["data"])
                janela = [m for m in lista[i:]
                           if (datetime.fromisoformat(m["data"]) - d0).days <= 7]
                if len(janela) >= 4:
                    iguais = max(Counter(m["valor"] for m in janela).values())
                    if iguais >= 2:
                        achados.append({
                            "tipo": "CRITICO_B",
                            "destinatario": d_nome, "cpf": cpf,
                            "periodo": f"{janela[0]['data']} a {janela[-1]['data']}",
                            "qtd_notas": len(janela), "qtd_iguais": iguais,
                            "valor_total": sum((m["valor"] for m in janela), Decimal(0)),
                            "notas": [m["nfa"] for m in janela],
                        })
                        break

        # D) 3+ notas em 30 dias, soma ≥ R$ 100k
        if len(lista) >= 3:
            for i, n in enumerate(lista):
                d0 = datetime.fromisoformat(n["data"])
                janela = [m for m in lista[i:]
                           if (datetime.fromisoformat(m["data"]) - d0).days <= LIM_T02_D_DIAS]
                soma = sum((m["valor"] for m in janela), Decimal(0))
                if len(janela) >= 3 and soma >= LIM_T02_D_SOMA:
                    achados.append({
                        "tipo": "CRITICO_D",
                        "destinatario": d_nome, "cpf": cpf,
                        "periodo": f"{janela[0]['data']} a {janela[-1]['data']}",
                        "qtd_notas": len(janela),
                        "valor_total": soma,
                        "notas": [m["nfa"] for m in janela],
                    })
                    break
    return achados


def teste_t03_concentracao_contraparte(notas: list[dict]) -> dict:
    """T-03 NOVO: concentração de contraparte (Pareto)."""
    vendas = [n for n in notas if n["natureza"] == "VENDA"]
    if not vendas: return {}
    total = sum((n["valor"] for n in vendas), Decimal(0))
    if total <= 0: return {}
    por_dest = defaultdict(lambda: {"nome": "", "valor": Decimal(0), "qtd": 0})
    for n in vendas:
        d = por_dest[n["dest_cpf"]]
        d["nome"] = n["dest_nome"]
        d["valor"] += n["valor"]
        d["qtd"] += 1

    ranking = sorted(
        [{"cpf": k, **v, "pct": float(v["valor"] / total * 100)}
         for k, v in por_dest.items() if k != "—"],
        key=lambda x: -x["valor"])

    achados = []
    if ranking:
        top = ranking[0]
        if Decimal(str(top["pct"])) >= LIM_T03_CRITICO:
            achados.append({
                "tipo": "CRITICO", "subtipo": "TOP1",
                "destinatario": top["nome"], "cpf": top["cpf"],
                "pct": top["pct"], "valor": top["valor"], "qtd": top["qtd"],
            })
        elif Decimal(str(top["pct"])) >= LIM_T03_ATENCAO:
            achados.append({
                "tipo": "ATENCAO", "subtipo": "TOP1",
                "destinatario": top["nome"], "cpf": top["cpf"],
                "pct": top["pct"], "valor": top["valor"], "qtd": top["qtd"],
            })

    if len(ranking) >= 3:
        soma_top3 = sum(r["valor"] for r in ranking[:3])
        pct_top3 = float(soma_top3 / total * 100)
        if Decimal(str(pct_top3)) >= LIM_T03_TOP3:
            achados.append({
                "tipo": "CRITICO", "subtipo": "TOP3",
                "pct": pct_top3, "valor": soma_top3,
                "destinatarios": [{"nome": r["nome"], "pct": r["pct"]} for r in ranking[:3]],
            })

    return {"achados": achados, "ranking_top5": ranking[:5]} if achados else {}


def teste_t04_concentracao_pf(notas: list[dict]) -> dict:
    """T-04 endurecido: ATENÇÃO ≥70% / CRÍTICO ≥85% c/ recorrência."""
    vendas = [n for n in notas if n["natureza"] == "VENDA"]
    if not vendas: return {}
    pf = [n for n in vendas if len("".join(d for d in (n["dest_cpf"] or "") if d.isdigit())) == 11]
    pct_pf = Decimal(len(pf)) / Decimal(len(vendas)) * 100 if vendas else Decimal(0)
    recorrentes = Counter(n["dest_cpf"] for n in pf)
    recorrentes_3plus = [
        {"cpf": cpf, "nome": next(n["dest_nome"] for n in pf if n["dest_cpf"] == cpf),
          "qtd": q, "valor": sum((n["valor"] for n in pf if n["dest_cpf"] == cpf), Decimal(0))}
        for cpf, q in recorrentes.items() if q >= 3 and cpf != "—"
    ]
    if pct_pf >= LIM_T04_CRITICO and recorrentes_3plus:
        tipo = "CRITICO"
    elif pct_pf >= LIM_T04_ATENCAO:
        tipo = "ATENCAO"
    else:
        return {}
    return {
        "tipo": tipo,
        "pct_pf": float(pct_pf),
        "qtd_vendas_pf": len(pf), "qtd_vendas": len(vendas),
        "recorrentes": sorted(recorrentes_3plus, key=lambda x: -x["valor"])[:15],
    }


def teste_t08_documental(notas: list[dict]) -> dict:
    """T-08 endurecido: dígito inválido + CPF ausente em vendas."""
    invalidos_set = set()
    invalidos_list = []
    sem_cpf_vendas = []
    for n in notas:
        cpf = n["dest_cpf"]
        if cpf == "—" and n["natureza"] == "VENDA":
            sem_cpf_vendas.append({"nfa": n["nfa"], "data": n["data"],
                                    "destinatario": n["dest_nome"], "valor": n["valor"]})
            continue
        if cpf == "—": continue
        if cpf in invalidos_set: continue
        if not validar_documento(cpf):
            invalidos_set.add(cpf)
            invalidos_list.append({"cpf": cpf, "nome": n["dest_nome"], "nfa_exemplo": n["nfa"]})

    if not (invalidos_list or sem_cpf_vendas): return {}
    tipo_sem_cpf = "CRITICO" if len(sem_cpf_vendas) >= LIM_T08_CPF_AUSENTE_CRIT else "ATENCAO"
    return {
        "invalidos": invalidos_list,
        "sem_cpf": sem_cpf_vendas[:10],
        "qtd_sem_cpf": len(sem_cpf_vendas),
        "tipo_sem_cpf": tipo_sem_cpf if sem_cpf_vendas else None,
    }


# ── Orquestração ─────────────────────────────────────────────────────────

def main() -> None:
    print(f"{'CLIENTE':45s} {'N':>5s} {'T01':>5s} {'T02':>5s} {'T03':>5s} {'T04':>5s} {'T08':>5s}")
    print("=" * 80)
    consolidado = []
    for prefixo, slug in MAPA_PDFS.items():
        # DEUSDETE (Tocantins) — usar parser específico
        if prefixo == "DEUSDETE":
            saidas_pdf = PDFS_TO / "DEUSDETE_SAIDAS_2025.pdf"
            if not saidas_pdf.exists(): continue
            from parser_deusdete_to import parsear_notas_deusdete
            notas = parsear_notas_deusdete(saidas_pdf)
        else:
            rem = next(iter(PDFS.glob(f"{prefixo} *REM*.pdf")), None) \
                  or next(iter(PDFS.glob(f"{prefixo}*REM*.pdf")), None)
            if not rem: continue
            notas = parsear_notas(ler_pdf(rem))
        t01 = teste_t01_concentracao(notas)
        t02 = teste_t02_smurfing(notas)
        t03 = teste_t03_concentracao_contraparte(notas)
        t04 = teste_t04_concentracao_pf(notas)
        t08 = teste_t08_documental(notas)
        consolidado.append({
            "slug": slug, "prefixo": prefixo, "qtd_notas": len(notas),
            "t01": t01, "t02": t02, "t03": t03, "t04": t04, "t08": t08,
        })
        m_t03 = "X" if t03 else "—"
        m_t04 = "X" if t04 else "—"
        m_t08 = "X" if t08 else "—"
        print(f"{slug:45s} {len(notas):>5d} {len(t01):>5d} {len(t02):>5d} {m_t03:>5s} {m_t04:>5s} {m_t08:>5s}")

    saida_json = DEST / f"ANALISE_FORENSE_HARD_{datetime.now().strftime('%Y-%m-%d')}.json"
    saida_json.parent.mkdir(parents=True, exist_ok=True)
    saida_json.write_text(json.dumps(
        consolidado, ensure_ascii=False, indent=2, default=str,
    ), encoding="utf-8")
    print(f"\n[OK] JSON consolidado: {saida_json}")

    print()
    print("=" * 80)
    print("DETALHAMENTO DOS ACHADOS (regras endurecidas)")
    print("=" * 80)
    for c in consolidado:
        if not (c["t01"] or c["t02"] or c["t03"] or c["t04"] or c["t08"]): continue
        print(f"\n>>> {c['prefixo']}")
        if c["t01"]:
            crits = [a for a in c["t01"] if a["tipo"] == "CRITICO"]
            ates = [a for a in c["t01"] if a["tipo"] == "ATENCAO"]
            if crits:
                print(f"  T-01 CRITICO: {len(crits)} nota(s) ≥7% da receita anual")
                for a in crits[:5]:
                    print(f"    • NFA {a['nfa']} {a['data']}: {a['pct']:.2f}% - "
                           f"R$ {a['valor']:,.2f} - {a['destinatario']}")
            if ates:
                print(f"  T-01 ATENCAO: {len(ates)} nota(s) 3-7% da receita anual")
        if c["t02"]:
            por_tipo = Counter(a["tipo"] for a in c["t02"])
            print(f"  T-02 SMURFING: {dict(por_tipo)}")
            for a in c["t02"][:5]:
                tag = a["tipo"].replace("CRITICO_", "")
                print(f"    • [{tag}] {a['destinatario']} ({a['cpf']}) "
                       f"- {a['qtd_notas']} notas, R$ {a['valor_total']:,.2f}")
        if c["t03"]:
            for a in c["t03"]["achados"]:
                if a["subtipo"] == "TOP1":
                    print(f"  T-03 {a['tipo']} TOP1: {a['destinatario']} = {a['pct']:.1f}% "
                           f"da receita (R$ {a['valor']:,.2f}, {a['qtd']} notas)")
                else:
                    print(f"  T-03 {a['tipo']} TOP3: {a['pct']:.1f}% (R$ {a['valor']:,.2f})")
                    for d in a["destinatarios"]:
                        print(f"      - {d['nome']}: {d['pct']:.1f}%")
        if c["t04"]:
            t = c["t04"]
            print(f"  T-04 CONCENTRAÇÃO PF: {t['tipo']} - "
                   f"{t['pct_pf']:.1f}% vendas para PF ({t['qtd_vendas_pf']}/{t['qtd_vendas']}) "
                   f"- {len(t['recorrentes'])} PFs recorrentes")
        if c["t08"]:
            t = c["t08"]
            if t.get("invalidos"):
                print(f"  T-08 DOCUMENTAL INVÁLIDO: {len(t['invalidos'])} CPF/CNPJ")
                for a in t["invalidos"][:3]:
                    print(f"    • {a['cpf']} - {a['nome']}")
            if t.get("qtd_sem_cpf"):
                print(f"  T-08 SEM CPF: {t['tipo_sem_cpf']} - {t['qtd_sem_cpf']} venda(s) sem CPF do destinatário")


if __name__ == "__main__":
    main()
