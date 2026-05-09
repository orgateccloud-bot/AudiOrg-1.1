"""Bridge entre nfa-repo (extrator de PDFs SEFAZ-GO) e Horizon-Blue.

Converte os Pydantic NFA do nfa-repo em dicts compatíveis com `core/precalc.py`
e os 7 agentes consolidados (S1..S7), respeitando:
  - Regra Especial 1 (RE-1): VENDA->COMPRA quando produtor é DESTINATARIO
  - Heurística CFOP determinística (extrator não extrai CFOP)
  - Posicao correta (REMETENTE | DESTINATARIO) por arquivo origem
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

# Garantir nfa-repo no sys.path (default D:\nfa-repo, override via NFA_REPO_PATH)
_NFA_REPO = os.environ.get("NFA_REPO_PATH", r"D:\nfa-repo")
if _NFA_REPO not in sys.path:
    sys.path.insert(0, _NFA_REPO)


# ── Heurística CFOP ────────────────────────────────────────────────────────────
# Como o extractor do nfa-repo NÃO extrai CFOP, derivamos dele a partir de
# (natureza, posicao). Default: operações intra-estaduais Goiás (5xxx/1xxx).
# Em caso de dúvida, usar 5949/1949 (outras saídas/entradas).
_CFOP_TABELA: dict[tuple[str, str], str] = {
    ("VENDA",          "REMETENTE"):    "5102",  # Venda mercadoria adq. terceiros
    ("VENDA",          "DESTINATARIO"): "1102",  # Compra mercadoria comerc. (RE-1 reclassifica)
    ("REMESSA",        "REMETENTE"):    "5949",  # Outra saida (remessa generica)
    ("REMESSA",        "DESTINATARIO"): "1949",  # Outra entrada
    ("TRANSFERENCIA",  "REMETENTE"):    "5152",  # Transferencia mercadoria
    ("TRANSFERENCIA",  "DESTINATARIO"): "1152",  # Recebimento transferencia
    ("OUTRAS",         "REMETENTE"):    "5949",
    ("OUTRAS",         "DESTINATARIO"): "1949",
}


def cfop_heuristico(natureza: str, posicao: str) -> str:
    """Deriva CFOP a partir de (natureza, posicao). Retorna '5949' como fallback."""
    nat = (natureza or "OUTRAS").upper()
    pos = (posicao or "REMETENTE").upper()
    # Normaliza prefixos comuns
    if "VENDA" in nat:
        chave_nat = "VENDA"
    elif "REMESSA" in nat:
        chave_nat = "REMESSA"
    elif "TRANSFER" in nat:
        chave_nat = "TRANSFERENCIA"
    else:
        chave_nat = "OUTRAS"
    if "DESTIN" in pos:
        chave_pos = "DESTINATARIO"
    else:
        chave_pos = "REMETENTE"
    return _CFOP_TABELA.get((chave_nat, chave_pos), "5949")


# ── Conversão NFA Pydantic -> dict precalc ─────────────────────────────────────
def nfa_to_dict(
    nfa: Any,
    contribuinte_cpf: str,
    posicao_origem: str,
    atividade: str = "bovino",
) -> dict:
    """Converte NFA Pydantic em dict compativel com `core/precalc.py`.

    `posicao_origem` é definida pelo arquivo de origem (REM ou DEST).
    Não infere por CPF — confia no arquivo. Isso é crítico porque o nome
    do produtor frequentemente vem vazio do extractor.
    """
    rem = nfa.remetente
    dst = nfa.destinatario
    natureza_norm = classificar_natureza(nfa.natureza or "")
    pos = "REMETENTE" if "REM" in (posicao_origem or "").upper() else "DESTINATARIO"
    cfop = cfop_heuristico(natureza_norm, pos)
    return {
        "numero":              nfa.numero,
        "data":                nfa.emissao,
        "natureza":            natureza_norm,
        "cfop":                cfop,
        "valor_total":         float(nfa.valor_total or 0),
        "valor_icms":          float(nfa.valor_icms or 0),
        "quantidade":          float(nfa.quantidade_total or 0),
        "chave_acesso":        nfa.chave_acesso or "",
        "remetente":           rem.nome or "",
        "remetente_cpf":       rem.cpf_cnpj or "",
        "ie_remetente":        rem.ie or "",
        "destinatario":        dst.nome or "",
        "destinatario_cpf":    dst.cpf_cnpj or "",
        "ie_destinatario":     dst.ie or "",
        "posicao":             pos,
        "atividade":           atividade,
        "tipo_doc":            "nfa-e",
        "contribuinte_cpf":    contribuinte_cpf,
    }


def classificar_natureza(natureza: str) -> str:
    """Replica a lógica do nfa-repo (sem precisar importar)."""
    n = (natureza or "").upper()
    if "VENDA" in n:    return "VENDA"
    if "REMESSA" in n:  return "REMESSA"
    if "TRANSFER" in n: return "TRANSFERENCIA"
    return "OUTRAS"


# ── Agrupamento de PDFs por produtor ───────────────────────────────────────────
_RE_SUFIXO_REM = re.compile(r"\s+REM\.pdf$",  re.IGNORECASE)
_RE_SUFIXO_DST = re.compile(r"\s+DEST\.pdf$", re.IGNORECASE)


def _nome_produtor(arquivo: Path) -> tuple[str, str]:
    """Extrai (nome_produtor, posicao) do nome do arquivo.

    Convencao: '<NOME> REM.pdf' ou '<NOME> DEST.pdf'.
    Retorna ('', '') se nao bater no padrao.
    """
    nome = arquivo.name
    if _RE_SUFIXO_REM.search(nome):
        return _RE_SUFIXO_REM.sub("", nome).strip(), "REMETENTE"
    if _RE_SUFIXO_DST.search(nome):
        return _RE_SUFIXO_DST.sub("", nome).strip(), "DESTINATARIO"
    return "", ""


def agrupar_pdfs_por_produtor(pasta: Path) -> dict[str, dict[str, list[Path]]]:
    """Agrupa PDFs por nome de produtor.

    Retorna: { 'ADELA': {'REMETENTE': [Path], 'DESTINATARIO': [Path]} }
    """
    grupos: dict[str, dict[str, list[Path]]] = {}
    for pdf in sorted(Path(pasta).glob("*.pdf")):
        produtor, posicao = _nome_produtor(pdf)
        if not produtor:
            continue
        grupos.setdefault(produtor, {"REMETENTE": [], "DESTINATARIO": []})
        grupos[produtor][posicao].append(pdf)
    return grupos


# ── Processamento por produtor ─────────────────────────────────────────────────
def processar_produtor(
    nome_produtor: str,
    pdfs_por_posicao: dict[str, list[Path]],
    atividade: str = "bovino",
) -> dict | None:
    """Extrai todos os PDFs de um produtor e monta payload pronto p/ precalc.

    Retorna None se nada foi extraido. Caso contrario, dict com:
      - notas (lista de dicts ja com posicao correta por arquivo)
      - contribuinte (cpf identificado)
      - lcdpr_data (totais derivados)
    """
    from src.domain.extractor import extrair_notas  # type: ignore

    todas: list[dict] = []
    contribuinte_cpf = ""
    contribuinte_nome = nome_produtor

    # Primeira passagem: identifica CPF a partir de qualquer arquivo do produtor
    for posicao, pdfs in pdfs_por_posicao.items():
        for pdf in pdfs:
            try:
                notas, nome, cpf = extrair_notas(str(pdf))
            except Exception:
                continue
            if cpf and not contribuinte_cpf:
                contribuinte_cpf = cpf
            if nome and not contribuinte_nome.strip():
                contribuinte_nome = nome
            for n in notas:
                todas.append(nfa_to_dict(n, contribuinte_cpf or cpf, posicao, atividade))

    if not todas:
        return None

    receita = sum(n["valor_total"] for n in todas
                  if n["natureza"] == "VENDA" and n["posicao"] == "REMETENTE")
    despesa = sum(n["valor_total"] for n in todas
                  if not (n["natureza"] == "VENDA" and n["posicao"] == "REMETENTE"))

    return {
        "produtor":     nome_produtor,
        "notas":        todas,
        "contribuinte": {
            "razao_social":        contribuinte_nome or nome_produtor,
            "cpf_cnpj":            contribuinte_cpf,
            "inscricao_estadual":  "12345678",
            "area_total_ha":       100,
            "area_utilizada_ha":   90,
        },
        "lcdpr_data": {
            "total_receitas": receita,
            "total_despesas": despesa,
        },
    }


# ── Lote ───────────────────────────────────────────────────────────────────────
async def executar_lote(
    pasta_pdfs: Path,
    atividade: str = "bovino",
) -> list[dict]:
    """Executa precalc determinístico para cada produtor agrupado.

    Retorna lista de dicts (1 por produtor) com payload + __precalc__.
    """
    from horizon_blue_one.core.precalc import precalcular

    grupos = agrupar_pdfs_por_produtor(Path(pasta_pdfs))
    resultados: list[dict] = []
    for produtor, pdfs in grupos.items():
        payload = processar_produtor(produtor, pdfs, atividade)
        if not payload:
            continue
        payload = await precalcular(payload)
        resultados.append(payload)
    return resultados
