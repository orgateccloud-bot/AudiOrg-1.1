"""scripts/parser_gief_mensal.py

Extrai detalhamento MENSAL de cada PDF GIEF (NFE_GADO_2026) e atualiza
os JSONs em scripts/clientes/. Para cada cliente:
  • PDF REM (saídas) → vendas_mensais (VENDA) + remessas_mensais (REMESSA/LEILAO + DEVOLUCAO)
  • PDF DEST (entradas) → compras_mensais

Replica o padrão da Planilha de Gado IR do GENIS (mês × qtd_notas × cabecas × valor).
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
CLIENTES = RAIZ / "scripts" / "clientes"
PDFS = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")

MESES_PT = {
    "01": "Janeiro",   "02": "Fevereiro", "03": "Março",
    "04": "Abril",     "05": "Maio",      "06": "Junho",
    "07": "Julho",     "08": "Agosto",    "09": "Setembro",
    "10": "Outubro",   "11": "Novembro",  "12": "Dezembro",
}

# Mapa: slug do cliente -> prefixo do nome do PDF na pasta NFE_GADO_2026
MAPA_PDFS = {
    "adela_fernanda_silva_santos_2025":         "ADELA",
    "cleiton_barbosa_santos_2025":              "CLEITON",
    "cleuzenir_rodrigues_de_almeida_2025":      "CLEUZENIR",
    "etervaldo_goncalves_da_cruz_2025":         "ETERVALDO",
    "fabio_humberto_ribeiro_santos_2025":       "FABIO",
    "gean_oliveira_maia_2025":                  "GEAN",
    "genis_2025":                               "GENIS",
    "genis_carlos_luiz_de_oliveira_2025":       "GENIS",
    "geovane_alves_vieira_2025":                "GEOVANE",
    "geraldo_martins_da_costa_2025":            "GERALDO",
    "glauber_tassi_de_souza_2025":              "GLAUBER",
    "helio_jose_alves_da_silva_2025":           "HELIO JOSE",
    "hellida_patricia_oliveira_camilo_pereira_2025": "HELLIDA",
    "jose_ailton_goncalves_da_silva_2025":      "JOSE AILTON",
    "jose_nelson_fernandes_2025":               "JOSE NELSON",
    "josmair_pires_do_carmo_2025":              "JOSMAIR",
    "laelson_rodrigues_de_souza_2025":          "LAELSON",
    "leandro_jose_da_silva_2025":               "LEANDRO",
    "margareth_moreira_mendes_2025":            "MARGARETH",
    "marilza_pereira_dos_santos_2025":          "MARILZA",
    "matheus_bernardes_silva_mendes_2025":      "MATHEUS",
    "raul_alves_de_aquino_2025":                "RAUL",
    "ricardo_de_souza_lobo_2025":               "RICARDO LOBO",
    "wanderlina_lima_de_morais_tassi_2025":     "WANDERLINA",
}


def ler_pdf(path: Path) -> str:
    """Extrai texto do PDF preservando layout."""
    res = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True, check=False,
        encoding="utf-8", errors="ignore",
    )
    return res.stdout


def parse_brl(s: str) -> Decimal:
    """'R$ 33.529,58' → Decimal('33529.58')"""
    s = s.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return Decimal(s)
    except Exception:
        return Decimal(0)


def parsear_notas(texto: str) -> list[dict]:
    """Quebra o texto em blocos de nota e extrai data, natureza, valor, cabeças.

    Retorna lista de dicts: [{data, mes, natureza, valor, cabecas}, ...]
    """
    # Cada nota é separada por "IDENTIFICAAO DA NOTA" (sem cedilha após pdftotext)
    blocos = re.split(r"IDENTIFICA[CA]?AO DA NOTA", texto, flags=re.IGNORECASE)[1:]
    if blocos and "RESUMO" in blocos[-1]:
        blocos[-1] = blocos[-1].split("RESUMO")[0]

    notas = []
    for bloco in blocos:
        # Linha que tem NUMERO + DATA + NATUREZA, ex: "24793449 29/01/2025 VENDA"
        m = re.search(
            r"(\d{7,9})\s+(\d{2})/(\d{2})/(\d{4})\s+"
            r"(VENDA|REMESSA/LEILAO|OUTRA\s+REMESSAS|DEVOLU[CC]AO|COMPRA)",
            bloco)
        if not m:
            continue
        natureza = re.sub(r"\s+", " ", m.group(5).strip())
        mes_num = m.group(3)
        ano = m.group(4)
        mes_nome = MESES_PT.get(mes_num, "—")

        # Soma valores dos produtos no bloco (Vlr.Total) — pega TODOS R$ não-zero
        valores = re.findall(r"R\$\s*([\d.]+,\d{2})", bloco)
        valor_total = Decimal(0)
        for v in valores:
            n = parse_brl(v)
            if n > 0:
                valor_total += n

        # Cabeças: número no formato XX,00 (coluna Quantidade do PDF GIEF)
        # Filtros:
        #   • Não precedido por "R$" (exclui R$ 0,00 do ICMS)
        #   • Não precedido por "." ou outro dígito (exclui "400" de "5.400,00")
        #   • Não seguido por outro dígito (exclui inícios de números maiores)
        cabecas = sum(
            int(c) for c in re.findall(
                r"(?<!R\$\s)(?<!R\$)(?<![.\d])(\d+),00\b(?!\s*\d)", bloco)
            if int(c) > 0
        )

        notas.append({
            "numero": m.group(1),
            "data":   f"{m.group(2)}/{mes_num}/{ano}",
            "mes":    mes_nome,
            "mes_num": int(mes_num),
            "natureza": natureza,
            "valor": valor_total,
            "cabecas": cabecas,
        })
    return notas


def agregar_mensal(notas: list[dict], naturezas_alvo: set[str]) -> list[dict]:
    """Agrega lista de notas por mês para naturezas escolhidas."""
    por_mes: dict[int, dict] = {}
    for n in notas:
        if n["natureza"] not in naturezas_alvo:
            continue
        m = n["mes_num"]
        if m not in por_mes:
            por_mes[m] = {"mes": n["mes"], "qtd_notas": 0,
                          "cabecas": 0, "valor": Decimal(0)}
        por_mes[m]["qtd_notas"] += 1
        por_mes[m]["cabecas"] += n["cabecas"]
        por_mes[m]["valor"] += n["valor"]
    out = []
    for m in sorted(por_mes):
        d = por_mes[m]
        out.append({
            "mes":       d["mes"],
            "qtd_notas": d["qtd_notas"],
            "cabecas":   d["cabecas"],
            "valor":     str(d["valor"].quantize(Decimal("0.01"))),
        })
    return out


def localizar_pdfs(prefixo: str) -> tuple[Path | None, Path | None]:
    """Localiza PDFs DEST e REM do cliente pelo prefixo."""
    dest = next(iter(PDFS.glob(f"{prefixo} *DEST*.pdf")), None)
    rem  = next(iter(PDFS.glob(f"{prefixo} *REM*.pdf")), None)
    if not rem:
        # Algumas variações com espaço duplo (ex: "JOSE  REM.pdf")
        rem = next(iter(PDFS.glob(f"{prefixo}*REM*.pdf")), None)
    return dest, rem


def processar_cliente(slug: str, prefixo: str) -> dict:
    """Processa um cliente: lê PDFs, agrega mensal, retorna dict para mesclar no JSON."""
    out = {"vendas_mensais": [], "remessas_mensais": [], "compras_mensais": []}

    dest_pdf, rem_pdf = localizar_pdfs(prefixo)

    if rem_pdf and rem_pdf.exists():
        notas_rem = parsear_notas(ler_pdf(rem_pdf))
        out["vendas_mensais"] = agregar_mensal(notas_rem, {"VENDA"})
        # REMESSA/LEILAO + DEVOLUCAO somam em remessas_mensais (regra OrgAudi 1.1)
        out["remessas_mensais"] = agregar_mensal(
            notas_rem, {"REMESSA/LEILAO", "OUTRA REMESSAS", "DEVOLUCAO"})

    if dest_pdf and dest_pdf.exists():
        notas_dest = parsear_notas(ler_pdf(dest_pdf))
        # Em DEST, natureza vista pelo remetente é VENDA — mas para o destinatário
        # (nosso contribuinte) é COMPRA pela Regra Especial 1.
        # Conta todas as notas do PDF DEST como compras.
        out["compras_mensais"] = agregar_mensal(
            notas_dest, {"VENDA", "REMESSA/LEILAO", "OUTRA REMESSAS", "COMPRA"})

    return out


def atualizar_json(slug: str, mensais: dict) -> str:
    """Atualiza vendas/remessas/compras_mensais no JSON do cliente.

    Retorna status: 'ok (V/R/C)', 'sem_alteracao', ou 'sem_pdfs'.
    """
    path = CLIENTES / f"{slug}.json"
    if not path.exists():
        return "ja_existe"
    d = json.loads(path.read_text(encoding="utf-8"))

    v = mensais.get("vendas_mensais") or []
    r = mensais.get("remessas_mensais") or []
    c = mensais.get("compras_mensais") or []
    if not (v or r or c):
        return "sem_dados"

    if v: d["vendas_mensais"] = v
    if r: d["remessas_mensais"] = r
    if c: d["compras_mensais"] = c

    path.write_text(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return f"ok ({len(v)}V/{len(r)}R/{len(c)}C)"


def main() -> None:
    print(f"{'CLIENTE':45s} {'PDF DEST':>9s} {'PDF REM':>9s} {'STATUS':>30s}")
    print("=" * 100)
    for slug, prefixo in MAPA_PDFS.items():
        d, r = localizar_pdfs(prefixo)
        has_d = "OK" if d and d.exists() else "—"
        has_r = "OK" if r and r.exists() else "—"
        mensais = processar_cliente(slug, prefixo)
        status = atualizar_json(slug, mensais)
        print(f"{slug:45s} {has_d:>9s} {has_r:>9s} {status:>30s}")


if __name__ == "__main__":
    main()
