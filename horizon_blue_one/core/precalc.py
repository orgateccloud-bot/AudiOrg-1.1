"""Precalc — Camada Determinística de Pré-Cálculo Paralelo.

Centraliza TODO cálculo determinístico do pipeline em UM único passe paralelo,
antes que qualquer agente LLM seja chamado. Resolve falhas F1/F2/F13/F14:

    F1: Detectores forenses rodavam 2x (a07 + a23).
    F2: extrair_features_completas chamava detectores 5x por audit.
    F13: detectar_devolucao_posterior corrigido (sem multiplicar por 1.1).
    F14: RE-1 aplicada ANTES de @Delta para evitar dupla anonimização.

Como funciona:
    payload = await precalcular(payload)
    # Após isso payload["__precalc__"] contém TUDO determinístico:
    #   - notas_re1 (já reclassificadas pela Regra Especial 1)
    #   - pii (CPFs/contas detectados)
    #   - documentos (validação ZeroTrust)
    #   - detectores ({carrossel, smurfing, fantasma, devolucao, anomalia_temp})
    #   - xgboost ({score, prob_autuacao, tipologias_criticas, shap})
    #   - lstm ({modo, score_medio, produtores_anomalos, detalhes})   ← NOVO
    #   - cfop ({total, divergentes, validos})
    #   - lcdpr ({receita_notas, receita_lcdpr, divergencia})
    #   - itr ({area_total_ha, area_utilizada, gu_pct})
    #   - grafo ({densidade, ciclos, hubs})
    #   - caixa ({entradas, saidas, saldo})
    # Os 7 novos agentes consultam este cache em vez de recomputar.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import structlog

from horizon_blue_one.agents.detectores_forenses import (
    detectar_anomalia_temporal,
    detectar_carrossel,
    detectar_devolucao_posterior,
    detectar_fornecedor_fantasma,
    detectar_smurfing,
)
from horizon_blue_one.ml.lstm_scorer import calcular_lstm
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1

logger = structlog.get_logger()

# ── Regex compilados (LGPD) ──────────────────────────────────────────────────
_RE_CPF     = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_RE_CNPJ    = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_RE_CONTA   = re.compile(r"\b\d{4,6}-?\d\b")

_CFOP_RURAL_VALIDOS: frozenset[str] = frozenset({
    # Compras / vendas / devoluções
    "1101", "1102", "1116", "1201", "1202", "1411", "1551", "1556",
    "2101", "2102", "2116", "2201", "2202", "2411", "2551", "2556",
    "5101", "5102", "5116", "5201", "5202", "5411", "5551", "5556",
    "6101", "6102", "6116", "6201", "6202", "6411", "6551", "6556",
    # Remessa / transferência rural (legítimas)
    "1151", "1152", "1949",
    "2151", "2152", "2949",
    "5151", "5152", "5949",
    "6151", "6152", "6949",
})


# ── 1. Regra Especial 1 (PRIMEIRO, antes de anonimizar) ─────────────────────
def _re1_classifier(notas: list[dict]) -> list[dict]:
    """Aplica RE-1 ANTES de qualquer anonimização. Corrige F14.

    `aplicar_regra_especial_1` muta o dict; clonamos antes para preservar
    estabilidade do hash de memo (ler 2x a mesma entrada deve dar o mesmo h).
    """
    return [aplicar_regra_especial_1(dict(n)) for n in notas]


# ── 2. PII Scanner (Protocolo @Delta) ───────────────────────────────────────
def _pii_scanner(notas: list[dict]) -> dict:
    achados_cpf: list[str] = []
    achados_cnpj: list[str] = []
    achados_conta: list[str] = []
    for n in notas:
        blob = " ".join(str(v) for v in n.values() if v is not None)
        achados_cpf.extend(_RE_CPF.findall(blob))
        achados_cnpj.extend(_RE_CNPJ.findall(blob))
        achados_conta.extend(_RE_CONTA.findall(blob))
    return {
        "cpfs_detectados":   len(set(achados_cpf)),
        "cnpjs_detectados":  len(set(achados_cnpj)),
        "contas_detectadas": len(set(achados_conta)),
        "total_pii":         len(achados_cpf) + len(achados_cnpj) + len(achados_conta),
    }


# ── 3. ZeroTrust documental ─────────────────────────────────────────────────
def _doc_validator(notas: list[dict], contribuinte: dict) -> dict:
    pendencias = []
    for n in notas:
        if not n.get("chave_acesso") or len(str(n.get("chave_acesso", ""))) < 44:
            pendencias.append(f"chave invalida:{n.get('numero', '?')}")
        if not n.get("data"):
            pendencias.append(f"sem_data:{n.get('numero', '?')}")
    inscricao = contribuinte.get("inscricao_estadual", "")
    return {
        "documentos_validos":   len(notas) - len(pendencias),
        "pendencias":           pendencias[:20],
        "ie_valida":            bool(inscricao and str(inscricao).strip() not in ("", "ISENTO")),
        "total_pendencias":     len(pendencias),
    }


# ── 4. Detectores forenses (UMA vez só) ─────────────────────────────────────
def _detectores_all(notas: list[dict]) -> dict:
    """Roda os 5 detectores UMA vez. Resultado consumido por XGBoost + S2 forense."""
    return {
        "carrossel":          detectar_carrossel(notas),
        "smurfing":           detectar_smurfing(notas),
        "fornecedor_fantasma": detectar_fornecedor_fantasma(notas),
        "devolucao_posterior": detectar_devolucao_posterior(notas),
        "anomalia_temporal":  detectar_anomalia_temporal(notas),
    }


# ── 5. Score XGBoost (consome detectores cacheados) ─────────────────────────
def _xgboost_score(notas: list[dict], detectores: dict) -> dict:
    """Score heurístico. F2: detectores vêm cacheados, não recomputa."""
    try:
        from horizon_blue_one.ml.xgboost_scorer import calcular_score_com_cache
        return calcular_score_com_cache(notas, detectores)
    except (ImportError, AttributeError):
        # Fallback: heurística inline se scorer ainda não tem cache API
        peso = 0.0
        if detectores["carrossel"]:           peso += 25
        if detectores["smurfing"]:            peso += 20
        if detectores["fornecedor_fantasma"]: peso += 15
        if detectores["devolucao_posterior"]: peso += 15
        if detectores["anomalia_temporal"]:   peso += 10
        n_susp = len(detectores.get("fornecedor_fantasma", [])) if isinstance(
            detectores.get("fornecedor_fantasma"), list) else 0
        peso += min(n_susp * 2, 15)
        score = min(peso, 100.0)
        return {
            "score":                  round(score, 2),
            "score_risco":            round(score, 2),
            "probabilidade_autuacao": round(score / 100.0, 3),
            "tipologias_criticas":    sum(1 for v in detectores.values() if v),
            "shap":                   detectores,
        }


# ── 5b. Score LSTM (série temporal por produtor) ─────────────────────────────
def _lstm_score(notas: list[dict]) -> dict:
    """Análise temporal LSTM. Heurístico sem modelo; treinado via LSTM_MODEL_PATH."""
    try:
        return calcular_lstm(notas)
    except Exception as exc:
        logger.warning("lstm_score_erro", error=str(exc))
        return {"modo": "erro", "score_medio": 0.0, "produtores_anomalos": [], "detalhes": {}}


# ── 6. CFOP validator + breakdown por tipo (F3: detalha entrada/saída) ──────
# 1xxx = entrada interna · 2xxx = entrada interestadual
# 5xxx = saída interna   · 6xxx = saída interestadual
def _cfop_tipo(cfop: str) -> str:
    if not cfop:
        return "ausente"
    primeiro = cfop[0]
    if primeiro == "1":
        return "entrada_interna"
    if primeiro == "2":
        return "entrada_interestadual"
    if primeiro == "5":
        return "saida_interna"
    if primeiro == "6":
        return "saida_interestadual"
    return "outro"


def _cfop_validator(notas: list[dict]) -> dict:
    divergentes: list[dict] = []
    validos = 0
    breakdown: dict[str, int] = {
        "entrada_interna": 0, "entrada_interestadual": 0,
        "saida_interna":   0, "saida_interestadual":   0,
        "outro":           0, "ausente":               0,
    }
    valor_por_tipo: dict[str, float] = dict.fromkeys(breakdown, 0.0)
    for n in notas:
        cfop = str(n.get("cfop", "")).strip()
        tipo = _cfop_tipo(cfop)
        breakdown[tipo] += 1
        valor_por_tipo[tipo] += float(n.get("valor_total", 0) or 0)
        if cfop in _CFOP_RURAL_VALIDOS:
            validos += 1
        else:
            divergentes.append({"numero": n.get("numero", "?"), "cfop": cfop, "tipo": tipo})
    return {
        "total":              len(notas),
        "validos":            validos,
        "divergentes":        divergentes[:50],
        "total_divergencias": len(divergentes),
        "por_tipo":           breakdown,
        "valor_por_tipo":     {k: round(v, 2) for k, v in valor_por_tipo.items()},
    }


# ── 6b. ICMS — alíquota efetiva por CFOP + divergências (F3) ────────────────
# Heurística rural GO: intra-UF (1xxx/5xxx) tende a alíquota efetiva ≈ 0
# (isenção/diferimento). Interestadual rural deve cair na banda 7%–18%.
# Divergências sinalizam — não decidem; S3/@Fiscalista valida no LLM.
_BANDA_ALIQ_INTERESTADUAL = (0.05, 0.18)


def _icms_por_cfop(notas: list[dict]) -> dict:
    """Agrega ICMS por tipo de CFOP e detecta alíquotas suspeitas."""
    agregado: dict[str, dict[str, float]] = {}
    suspeitas: list[dict] = []
    for n in notas:
        cfop  = str(n.get("cfop", "")).strip()
        tipo  = _cfop_tipo(cfop)
        valor = float(n.get("valor_total", 0) or 0)
        icms  = float(n.get("valor_icms",  0) or 0)
        slot  = agregado.setdefault(tipo, {"valor_total": 0.0, "icms_total": 0.0, "n": 0})
        slot["valor_total"] += valor
        slot["icms_total"]  += icms
        slot["n"]           += 1
        if valor > 0:
            aliq = icms / valor
            if tipo == "saida_interestadual" and not (
                _BANDA_ALIQ_INTERESTADUAL[0] <= aliq <= _BANDA_ALIQ_INTERESTADUAL[1]
            ):
                suspeitas.append({
                    "numero": n.get("numero", "?"),
                    "cfop":   cfop,
                    "aliquota_efetiva": round(aliq, 4),
                    "motivo": "fora_banda_interestadual",
                })
            elif tipo in ("entrada_interna", "saida_interna") and icms > 0:
                suspeitas.append({
                    "numero": n.get("numero", "?"),
                    "cfop":   cfop,
                    "aliquota_efetiva": round(aliq, 4),
                    "motivo": "icms_em_intra_uf_rural",
                })
    resumo: dict[str, dict[str, float]] = {}
    for tipo, slot in agregado.items():
        v = slot["valor_total"]
        resumo[tipo] = {
            "n":                int(slot["n"]),
            "valor_total":      round(v, 2),
            "icms_total":       round(slot["icms_total"], 2),
            "aliquota_efetiva": round(slot["icms_total"] / v, 4) if v > 0 else 0.0,
        }
    return {
        "por_tipo":    resumo,
        "suspeitas":   suspeitas[:50],
        "n_suspeitas": len(suspeitas),
    }


# ── 7. LCDPR diff ────────────────────────────────────────────────────────────
def _lcdpr_diff(notas: list[dict], lcdpr: dict) -> dict:
    receita_notas = sum(
        float(n.get("valor_total", 0))
        for n in notas
        if str(n.get("categoria_contabil", "")).upper() == "RECEITA"
    )
    receita_lcdpr = float(lcdpr.get("total_receitas", 0))
    despesa_lcdpr = float(lcdpr.get("total_despesas", 0))
    div = receita_notas - receita_lcdpr
    if abs(div) < 1e-2:
        status = "CONFORME"
    elif abs(div) > 50_000:
        status = "CRITICO"
    else:
        status = "DIVERGENTE"
    return {
        "receita_notas":     round(receita_notas, 2),
        "receita_lcdpr":     round(receita_lcdpr, 2),
        "despesa_lcdpr":     round(despesa_lcdpr, 2),
        "divergencia":       round(div, 2),
        "saldo_lcdpr":       round(receita_lcdpr - despesa_lcdpr, 2),
        "status_conformidade": status,
    }


# ── 8. ITR — Capacidade de uso + classe GU (F3) ─────────────────────────────
# Classes GU conforme Lei 9.393/96 (alíquotas progressivas do ITR):
#   alta:        gu >= 80%   (alíquota mínima)
#   media:       50% <= gu < 80%
#   baixa:       30% <= gu < 50%
#   subutilizada: gu < 30%  (alíquota máxima — risco de autuação)
def _classe_gu(gu_pct: float, area_total: float) -> str:
    if area_total <= 0:
        return "sem_imovel"
    if gu_pct >= 80:
        return "alta"
    if gu_pct >= 50:
        return "media"
    if gu_pct >= 30:
        return "baixa"
    return "subutilizada"


def _itr_capacidade(contribuinte: dict) -> dict:
    area_total = float(contribuinte.get("area_total_ha", 0))
    area_util  = float(contribuinte.get("area_utilizada_ha", 0))
    gu = (area_util / area_total * 100) if area_total > 0 else 0
    classe = _classe_gu(gu, area_total)
    return {
        "area_total_ha":   area_total,
        "area_utilizada":  area_util,
        "gu_pct":          round(gu, 2),
        "subutilizado":    gu < 80 if area_total > 0 else False,
        "classe_gu":       classe,
        "risco_autuacao":  classe in ("baixa", "subutilizada"),
    }


# ── 9. Métricas de grafo (NetworkX opcional) ────────────────────────────────
def _grafo_metrics(notas: list[dict]) -> dict:
    try:
        import networkx as nx
    except ImportError:
        return {"densidade": 0, "ciclos": 0, "hubs": [], "disponivel": False}
    g = nx.DiGraph()
    for n in notas:
        rem = str(n.get("remetente_cpf") or n.get("remetente") or "")
        dst = str(n.get("destinatario_cpf") or n.get("destinatario") or "")
        if rem and dst:
            g.add_edge(rem, dst, valor=float(n.get("valor_total", 0)))
    if g.number_of_nodes() < 2:
        return {"densidade": 0, "ciclos": 0, "hubs": [], "disponivel": True}
    try:
        ciclos = len(list(nx.simple_cycles(g)))
    except Exception:
        ciclos = 0
    grau = sorted(g.degree(), key=lambda x: x[1], reverse=True)
    hubs = [n for n, _ in grau[:3]]
    return {
        "densidade":  round(nx.density(g), 4),
        "ciclos":     ciclos,
        "hubs":       hubs,
        "nos":        g.number_of_nodes(),
        "arestas":    g.number_of_edges(),
        "disponivel": True,
    }


# ── 10. Caixa (entradas/saídas/saldo) ───────────────────────────────────────
def _caixa_aggregator(notas: list[dict]) -> dict:
    entradas = 0.0
    saidas   = 0.0
    for n in notas:
        v = float(n.get("valor_total", 0))
        cat = str(n.get("categoria_contabil", "")).upper()
        if cat == "RECEITA":
            entradas += v
        elif cat in ("DESPESA", "CUSTO"):
            saidas += v
    return {
        "entradas": round(entradas, 2),
        "saidas":   round(saidas, 2),
        "saldo":    round(entradas - saidas, 2),
    }


# ── Memo cache (TTL 5min, in-process, thread-safe) ──────────────────────────
# Isolamento por requisição: cache armazena snapshot imutável (deepcopy na
# escrita); leituras retornam deepcopy para que mutações downstream (a08, a26)
# não contaminem o cache compartilhado entre requisições concorrentes.
_MEMO_CACHE: dict[str, tuple[float, dict]] = {}
_MEMO_TTL = 300.0  # segundos
_MEMO_LOCK = threading.Lock()
_MEMO_MAX = 256


def _payload_hash(payload: dict) -> str:
    """Hash estável de notas+contribuinte+lcdpr para memoização."""
    chave = {
        "notas":        payload.get("notas", []),
        "contribuinte": payload.get("contribuinte", {}),
        "lcdpr":        payload.get("lcdpr_data", {}),
    }
    raw = json.dumps(chave, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def reset_precalc_cache() -> None:
    """Limpa o memo cache. Uso restrito a fixtures de teste."""
    with _MEMO_LOCK:
        _MEMO_CACHE.clear()


# ── Orquestração paralela ───────────────────────────────────────────────────
async def precalcular(payload: dict) -> dict:
    """Executa as 10 funções determinísticas em paralelo (uma única vez).

    Idempotente: se já houver `__precalc__` no payload, retorna sem recalcular.
    Memoizado: se o mesmo (notas, contribuinte, lcdpr) rodou há <5min, reusa.
    """
    if "__precalc__" in payload:
        return payload

    # ── Memo: hit por contribuinte+notas+lcdpr ───────────────────────────────
    h = _payload_hash(payload)
    agora = time.time()
    with _MEMO_LOCK:
        cached = _MEMO_CACHE.get(h)
    if cached and (agora - cached[0]) < _MEMO_TTL:
        # Deep copy: cada requisição recebe seu próprio snapshot. Agentes
        # downstream (a08_geo, a26_anomalia) podem mutar __precalc__ sem
        # contaminar o cache nem outras requisições concorrentes.
        snapshot = copy.deepcopy(cached[1])
        payload["__precalc__"] = snapshot
        payload["notas_classificadas"] = snapshot["notas_re1"]
        logger.info("precalc.memo_hit", hash=h, idade_s=round(agora - cached[0], 1))
        return payload

    notas_raw    = payload.get("notas", []) or []
    contribuinte = payload.get("contribuinte", {}) or {}
    lcdpr        = payload.get("lcdpr_data", {}) or {}

    # PASSO 1: RE-1 antes de qualquer anonimização (corrige F14)
    notas_re1 = _re1_classifier(notas_raw)

    # PASSO 2: 9 funções restantes em paralelo
    loop = asyncio.get_event_loop()

    async def _run(fn: Callable[..., Any], *args: Any) -> Any:
        return await loop.run_in_executor(None, fn, *args)

    pii, docs, det, cfop, icms, lcdpr_d, itr_d, grafo, caixa = await asyncio.gather(
        _run(_pii_scanner, notas_re1),
        _run(_doc_validator, notas_re1, contribuinte),
        _run(_detectores_all, notas_re1),
        _run(_cfop_validator, notas_re1),
        _run(_icms_por_cfop, notas_re1),
        _run(_lcdpr_diff, notas_re1, lcdpr),
        _run(_itr_capacidade, contribuinte),
        _run(_grafo_metrics, notas_re1),
        _run(_caixa_aggregator, notas_re1),
    )

    # XGBoost depende dos detectores → roda depois (mas é determinístico/rápido)
    # LSTM roda em paralelo com XGBoost (independente dos detectores)
    xgb, lstm = await asyncio.gather(
        _run(_xgboost_score, notas_re1, det),
        _run(_lstm_score, notas_re1),
    )

    pre_resultado = {
        "notas_re1":    notas_re1,
        "pii":          pii,
        "documentos":   docs,
        "detectores":   det,
        "xgboost":      xgb,
        "lstm":         lstm,
        "cfop":         cfop,
        "icms":         icms,
        "lcdpr":        lcdpr_d,
        "itr":          itr_d,
        "grafo":        grafo,
        "caixa":        caixa,
    }
    # Snapshot imutável para o cache (independente do payload que vai pra
    # downstream). Sem isso, agentes mutando __precalc__ corromperiam o
    # cache compartilhado.
    snapshot_cache = copy.deepcopy(pre_resultado)
    payload["__precalc__"] = pre_resultado
    payload["notas_classificadas"] = notas_re1  # compat A-08/A-26
    with _MEMO_LOCK:
        _MEMO_CACHE[h] = (agora, snapshot_cache)
        # Limpa entradas expiradas (keep memory bounded). check-then-pop
        # protegido pelo mesmo lock para evitar race entre requisições.
        if len(_MEMO_CACHE) > _MEMO_MAX:
            expirados = [
                k for k, (t, _) in _MEMO_CACHE.items()
                if (agora - t) > _MEMO_TTL
            ]
            for k in expirados:
                _MEMO_CACHE.pop(k, None)

    logger.info(
        "precalc.concluido",
        notas=len(notas_re1),
        score=xgb.get("score", 0),
        criticos=xgb.get("tipologias_criticas", 0),
        cfop_div=cfop.get("total_divergencias", 0),
        lcdpr_div=lcdpr_d.get("divergencia", 0),
    )
    return payload


def get_precalc(payload: dict[str, Any]) -> dict[str, Any]:
    """Retorna o cache `__precalc__` ou {} se ainda não rodou."""
    pc: dict[str, Any] = payload.get("__precalc__", {})
    return pc
