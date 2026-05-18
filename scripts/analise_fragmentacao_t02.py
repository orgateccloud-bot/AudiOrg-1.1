"""scripts/analise_fragmentacao_t02.py

Executa o Teste Forense T-02 (Fragmentação Fiscal / Smurfing) em todos os
PDFs GIEF da pasta NFE_GADO_2026. Critérios (do skill_rural v1.1.0):

  • CRITICO_A: >= 3 notas idênticas (mesmo valor) para mesmo destinatário no MESMO DIA
  • CRITICO_B: >= 5 notas para mesmo destinatário em 7 DIAS com >= 2 valores iguais

Gera relatório consolidado:
  reports_nfa/ANALISE_FRAGMENTACAO_T02_<data>.pdf
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
CLIENTES = RAIZ / "scripts" / "clientes"
PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")

# Mesmo mapa do parser_gief_mensal.py
MAPA_PDFS = {
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


def ler_pdf(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=False,
        encoding="utf-8", errors="ignore",
    ).stdout


def parse_brl(s: str) -> Decimal:
    s = s.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try: return Decimal(s)
    except Exception: return Decimal(0)


def parsear_notas_com_destinatario(texto: str) -> list[dict]:
    """Extrai dados estruturados de cada NFA-e: número, data, natureza,
    destinatário (CPF + nome), valor total.

    Layout do PDF GIEF — bloco típico de nota:
      IDENTIFICAAO DA NOTA
      CHAVE DE ACESSO
      <chave>
      NMERO DA NFA   EMISSO                NATUREZA
      <num>          <DD/MM/AAAA>          <NATUREZA>
      ...
      REMETENTE      INSCRIO ESTADUAL  CNPJ/CPF              MUNICPIO
      <nome rem>     <ie>              <cpf>                 <mun>
      DESTINATRIO    INSCRIO ESTADUAL  CNPJ/CPF              MUNICPIO
      <nome dest>    <ie>              <cpf>                 <mun>
    """
    blocos = re.split(r"IDENTIFICA[CA]?AO DA NOTA", texto, flags=re.IGNORECASE)[1:]
    if blocos and "RESUMO" in blocos[-1]:
        blocos[-1] = blocos[-1].split("RESUMO")[0]

    notas = []
    for bloco in blocos:
        m = re.search(
            r"(\d{7,9})\s+(\d{2})/(\d{2})/(\d{4})\s+"
            r"(VENDA|REMESSA/LEILAO|OUTRA\s+REMESSAS|DEVOLU[CC]AO|COMPRA)",
            bloco)
        if not m: continue
        numero = m.group(1)
        data = f"{m.group(4)}-{m.group(3)}-{m.group(2)}"
        natureza = re.sub(r"\s+", " ", m.group(5).strip())

        # Soma valores não-zero (Vlr.Total das linhas de produto)
        valores = re.findall(r"R\$\s*([\d.]+,\d{2})", bloco)
        valor_total = Decimal(0)
        for v in valores:
            n = parse_brl(v)
            if n > 0: valor_total += n

        # Destinatário — parsing por linhas (mais robusto que regex multiline)
        dest_nome = "—"
        dest_cpf = "—"
        dest_mun = "—"
        linhas = bloco.split("\n")
        for idx, l in enumerate(linhas):
            if re.match(r"\s*DESTINAT", l, re.IGNORECASE):
                # Procura próxima linha não-vazia
                for prox in linhas[idx + 1:idx + 6]:
                    if not prox.strip():
                        continue
                    # Padrão: "NOME ... IE ... CPF/CNPJ ... MUNICIPIO"
                    md = re.match(
                        r"\s*(.+?)\s{2,}(\d+)\s+"
                        r"(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})"
                        r"\s+(.+?)\s*$", prox)
                    if md:
                        dest_nome = md.group(1).strip()
                        dest_cpf = md.group(3)
                        dest_mun = md.group(4).strip()
                    break
                break

        notas.append({
            "nfa": numero,
            "data": data,
            "natureza": natureza,
            "valor": valor_total,
            "dest_nome": dest_nome,
            "dest_cpf": dest_cpf,
            "dest_mun": dest_mun,
        })
    return notas


def teste_t02(notas: list[dict]) -> list[dict]:
    """Executa T-02 (smurfing) e retorna lista de achados."""
    achados = []
    # Agrupa por destinatário
    por_dest = defaultdict(list)
    for n in notas:
        if n["natureza"] != "VENDA":  # T-02 só sobre vendas
            continue
        chave = n["dest_cpf"] or n["dest_nome"]
        por_dest[chave].append(n)

    for dest, lista in por_dest.items():
        lista.sort(key=lambda x: x["data"])
        if len(lista) < 3: continue
        dest_nome = lista[0]["dest_nome"]

        # CRITICO_A: 3+ notas idênticas (mesmo valor) no mesmo dia
        por_dia = defaultdict(list)
        for n in lista:
            por_dia[n["data"]].append(n)
        for dia, ds in por_dia.items():
            if len(ds) >= 3:
                # Conta valores idênticos
                valores = [n["valor"] for n in ds]
                from collections import Counter
                cnt = Counter(valores)
                iguais = max(cnt.values())
                if iguais >= 3:
                    achados.append({
                        "tipo": "CRITICO_A",
                        "destinatario": dest_nome,
                        "cpf": dest,
                        "data": dia,
                        "qtd_notas": len(ds),
                        "qtd_iguais": iguais,
                        "valor_total": sum((n["valor"] for n in ds), Decimal(0)),
                        "notas": [n["nfa"] for n in ds],
                    })

        # CRITICO_B: 5+ notas em 7 dias com 2+ valores iguais
        for i, n in enumerate(lista):
            d0 = datetime.fromisoformat(n["data"])
            janela = [m for m in lista[i:]
                      if (datetime.fromisoformat(m["data"]) - d0).days <= 7]
            if len(janela) >= 5:
                from collections import Counter
                cnt = Counter(m["valor"] for m in janela)
                iguais = max(cnt.values())
                if iguais >= 2:
                    achados.append({
                        "tipo": "CRITICO_B",
                        "destinatario": dest_nome,
                        "cpf": dest,
                        "periodo": f"{janela[0]['data']} a {janela[-1]['data']}",
                        "qtd_notas": len(janela),
                        "qtd_iguais": iguais,
                        "valor_total": sum((n["valor"] for n in janela), Decimal(0)),
                        "notas": [n["nfa"] for n in janela],
                    })
                    break  # uma janela por destinatário basta
    return achados


def main() -> None:
    print(f"{'CLIENTE':45s} {'NOTAS':>6s} {'T-02 A':>7s} {'T-02 B':>7s} {'TOTAL':>7s}")
    print("=" * 80)
    consolidado = []
    for prefixo, slug in MAPA_PDFS.items():
        rem = next(iter(PDFS.glob(f"{prefixo} *REM*.pdf")), None) \
              or next(iter(PDFS.glob(f"{prefixo}*REM*.pdf")), None)
        if not rem: continue
        notas = parsear_notas_com_destinatario(ler_pdf(rem))
        achados = teste_t02(notas)
        n_a = sum(1 for a in achados if a["tipo"] == "CRITICO_A")
        n_b = sum(1 for a in achados if a["tipo"] == "CRITICO_B")
        consolidado.append({
            "slug": slug, "prefixo": prefixo, "qtd_notas": len(notas),
            "achados": achados, "qtd_a": n_a, "qtd_b": n_b,
        })
        print(f"{slug:45s} {len(notas):>6d} {n_a:>7d} {n_b:>7d} {len(achados):>7d}")

    # Detalhamento dos achados
    print()
    print("=" * 80)
    print("DETALHAMENTO DOS ACHADOS T-02")
    print("=" * 80)
    for c in consolidado:
        if not c["achados"]: continue
        print(f"\n>>> {c['prefixo']} ({c['slug']}) — {len(c['achados'])} achados")
        for a in c["achados"]:
            print(f"  [{a['tipo']}] dest: {a['destinatario']} ({a['cpf']})")
            if a["tipo"] == "CRITICO_A":
                print(f"     Data: {a['data']} | {a['qtd_notas']} notas ({a['qtd_iguais']} com valor idêntico) "
                       f"| R$ {a['valor_total']:,.2f}")
            else:
                print(f"     Período: {a['periodo']} | {a['qtd_notas']} notas em 7d ({a['qtd_iguais']} com valor igual) "
                       f"| R$ {a['valor_total']:,.2f}")
            print(f"     NFAs: {', '.join(a['notas'][:9])}{'...' if len(a['notas']) > 9 else ''}")

    # Salva JSON consolidado
    saida = RAIZ / "reports_nfa" / f"ANALISE_FRAGMENTACAO_T02_{datetime.now().strftime('%Y-%m-%d')}.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(
        [{**c, "achados": [{**a, "valor_total": str(a["valor_total"])} for a in c["achados"]]}
         for c in consolidado],
        ensure_ascii=False, indent=2,
        default=str,
    ), encoding="utf-8")
    print(f"\n[OK] JSON consolidado: {saida}")


if __name__ == "__main__":
    main()
