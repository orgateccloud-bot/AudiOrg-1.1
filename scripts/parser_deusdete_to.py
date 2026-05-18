"""scripts/parser_deusdete_to.py

Adaptador para DEUSDETE (Tocantins / SEFAZ-TO).

Os PDFs SEFAZ-TO têm layout tabular linear (linhas por produto) e usam CFOP
em vez de NATUREZA. Este módulo lê o PDF via pdfplumber e devolve a MESMA
lista de dicts que `analise_forense_completa.py::parsear_notas` produz
para os PDFs GIEF SEFAZ-GO, agrupando linhas por número de NFA-e.

Mapeamento CFOP → NATUREZA:
    5.101 / 5.102 / 6.101  →  VENDA (saída externa)
    5.914 / 6.914           →  REMESSA/LEILAO (trânsito; mesmo CPF = interno)
    1.914 / 2.914           →  DEVOLUCAO
    1.101 / 1.102 / 5.911   →  COMPRA
    outros                  →  OUTRA REMESSAS
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pdfplumber


def _cfop_para_natureza(cfop: str) -> str:
    c = cfop.replace(".", "").strip()
    if c in ("5101", "5102", "6101", "6102"): return "VENDA"
    if c in ("5914", "6914"): return "REMESSA/LEILAO"
    if c in ("1914", "2914"): return "DEVOLUCAO"
    if c in ("1101", "1102", "2101", "2102", "5911", "1911"): return "COMPRA"
    return "OUTRA REMESSAS"


def _parse_brl(s) -> Decimal:
    if s is None: return Decimal(0)
    s = str(s).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try: return Decimal(s)
    except Exception: return Decimal(0)


def _parse_num(s) -> Decimal:
    """Parse número aceitando '1,00' ou '1.000,00' ou '10.00'."""
    if s is None: return Decimal(0)
    s = str(s).strip()
    if not s: return Decimal(0)
    # Se tem vírgula como decimal pt-BR
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try: return Decimal(s)
    except Exception: return Decimal(0)


def _normaliza_data(dt: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD."""
    try:
        d, m, y = dt.strip().split("/")
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        return dt


_RE_LINHA = re.compile(
    r"^(?P<nfa>\d{6,9})\s+"
    r"(?P<data>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<rem_cpf>[\d./-]+)\s+"
    r"(?P<resto>.+)$"
)


def parsear_notas_deusdete(caminho_pdf: Path) -> list[dict]:
    """Lê PDF SEFAZ-TO via regex sobre texto (pdfplumber)."""
    if not caminho_pdf.exists(): return []

    linhas_por_nfa = defaultdict(list)
    with pdfplumber.open(str(caminho_pdf)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            for raw in txt.split("\n"):
                m = _RE_LINHA.match(raw.strip())
                if not m: continue
                resto = m.group("resto")
                # resto = "REMETENTE_NOME CFOP DEST_CPF DEST_NOME PRODUTO QTD V.UNIT V.TOTAL"
                # CFOP no formato N.NNN ou N,NNN
                cfop_m = re.search(r"\s+(\d\.\d{3})\s+", resto)
                if not cfop_m: continue
                idx = cfop_m.start()
                rem_nome = resto[:idx].strip()
                pos = cfop_m.end()
                cfop = cfop_m.group(1)
                # Próximo: CPF/CNPJ destino
                dest_m = re.match(r"([\d./-]+)\s+(.*)$", resto[pos:])
                if not dest_m: continue
                dest_cpf = dest_m.group(1)
                resto_dest = dest_m.group(2)
                # Os 3 últimos números são QTD, V.UNIT, V.TOTAL
                nums = re.findall(r"([\d.]+,\d{2})", resto_dest)
                if len(nums) < 3: continue
                qtd_str, vunit_str, vtot_str = nums[-3], nums[-2], nums[-1]
                # Nome dest + produto = tudo antes dos 3 números
                pos_qtd = resto_dest.rfind(qtd_str)
                texto_dest_prod = resto_dest[:pos_qtd].strip()
                # Tenta separar destinatário (NOME) de produto (BOVINO...)
                prod_m = re.search(r"(BOVINO|GADO|TOURO|VACA|BOI)", texto_dest_prod)
                if prod_m:
                    dest_nome = texto_dest_prod[:prod_m.start()].strip()
                    produto = texto_dest_prod[prod_m.start():].strip()
                else:
                    dest_nome = texto_dest_prod
                    produto = ""

                linhas_por_nfa[m.group("nfa")].append({
                    "data": m.group("data"),
                    "rem_cpf": m.group("rem_cpf"),
                    "rem_nome": rem_nome,
                    "cfop": cfop,
                    "dest_cpf": dest_cpf,
                    "dest_nome": dest_nome,
                    "produto": produto,
                    "qtd": _parse_num(qtd_str),
                    "vunit": _parse_num(vunit_str),
                    "vtotal": _parse_num(vtot_str),
                })

    notas = []
    for nfa, linhas in linhas_por_nfa.items():
        l0 = linhas[0]
        # Nome destinatário: pega o primeiro NÃO-vazio que difere do remetente
        dest_nome = l0["dest_nome"]
        for ln in linhas:
            if ln["dest_nome"] and ln["dest_nome"].upper() != l0["rem_nome"].upper():
                dest_nome = ln["dest_nome"]
                break
        if not dest_nome:
            dest_nome = l0["dest_nome"] or "—"

        valor_total = sum((ln["vtotal"] for ln in linhas), Decimal(0))
        cabecas = sum(int(ln["qtd"]) for ln in linhas if ln["qtd"] == int(ln["qtd"]))

        natureza = _cfop_para_natureza(l0["cfop"])
        if l0["rem_cpf"] == l0["dest_cpf"] and natureza == "VENDA":
            natureza = "REMESSA/LEILAO"

        notas.append({
            "nfa": nfa,
            "data": _normaliza_data(l0["data"]),
            "natureza": natureza,
            "valor": valor_total,
            "cabecas": cabecas,
            "dest_nome": dest_nome,
            "dest_cpf": l0["dest_cpf"],
            "rem_nome": l0["rem_nome"],
            "rem_cpf": l0["rem_cpf"],
        })

    notas.sort(key=lambda n: n["data"])
    return notas
