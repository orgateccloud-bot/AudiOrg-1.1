"""
Pipeline reutilizável para simulação:
  1. Extrai notas do PDF (determinístico)
  2. Aplica RE-1 + apura F1-F6 (sem custo Claude)
  3. Roda agentes Horizon-Blue via Orchestrator com Claude MOCKED
  4. Captura snapshot dos tokens consumidos por agente
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

from nfa_extractor.domain.extractor import extrair_notas
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1
from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo
from horizon_blue_one.core.token_router import (
    _CUSTO_INPUT, _CUSTO_OUTPUT, ModelType,
    reset_stats, snapshot_stats,
)
from horizon_blue_one.core.orchestrator import Orchestrator

from scripts.simulacao.instrumentacao import (
    agente_ativo, instrumentar, set_num_notas,
)


# ── Caps de notas por modelo (rev v3) ─────────────────────────────────────
NOTAS_CAP_POR_MODELO = {
    "opus":   8,
    "sonnet": 20,
    "haiku":  100,
}

# Cap específico por agente — sobrepõe o cap por modelo.
# Agentes auditores especializados consomem amostra MÍNIMA (8 notas).
NOTAS_CAP_POR_AGENTE = {
    "A-07": 8,    # Assurance: amostra para detectar padrões
    "A-08": 8,    # Auditor-NFA: amostra crítica (já era 50, agora 8)
    "A-23": 12,   # Anomalias: precisa um pouco mais para AN-01..AN-18
    "A-27": 8,    # Forense grafo: amostra de relacionamentos
    "A-00": 5,    # CEO: vê só as 5 mais relevantes (recomenda decisão final)
}


def cap_notas_para_modelo(notas: list[dict], modelo: str, agent_id: str = "") -> list[dict]:
    """Trunca por agente (override) ou por modelo (default)."""
    cap = NOTAS_CAP_POR_AGENTE.get(agent_id) or NOTAS_CAP_POR_MODELO.get(modelo.lower(), 50)
    return notas[:cap] if len(notas) > cap else notas


# ── Mapa de abreviação para compactar JSON (-30% chars típico) ──────────────
_KEYS_COMPACTAS = {
    "valor_total": "v", "valor_icms": "vi", "quantidade_total": "q",
    "natureza": "nat", "natureza_exibicao": "ne",
    "categoria_contabil": "cc", "regra_aplicada": "ra",
    "remetente": "r", "destinatario": "d", "transportador": "t",
    "produtos": "p", "emissao": "e", "numero": "n",
    "chave_acesso": "k", "posicao": "po", "atividade": "at",
    "tipo_doc": "td", "produtor": "pr", "pdf_origem": "pf",
    "efeito_irpf": "ei", "confianca": "cf", "alertas_re1": "al",
}


def compactar_nota(nota: dict) -> dict:
    """Abrevia chaves para reduzir tamanho do JSON enviado ao LLM.
    Mantém apenas campos relevantes para auditoria."""
    out: dict = {}
    for k, v in nota.items():
        if v is None or v == "" or v == 0 or v == 0.0:
            continue  # remove nulos/zeros
        if isinstance(v, (dict, list)) and not v:
            continue
        nk = _KEYS_COMPACTAS.get(k, k)
        # Trunca strings longas
        if isinstance(v, str) and len(v) > 60:
            v = v[:60] + "..."
        # Recursão em dicts (remetente, destinatario)
        if isinstance(v, dict):
            v = {
                _KEYS_COMPACTAS.get(kk, kk): vv
                for kk, vv in v.items()
                if vv not in (None, "", 0, 0.0)
            }
        out[nk] = v
    return out


def compactar_notas(notas: list[dict]) -> list[dict]:
    return [compactar_nota(n) for n in notas]


def comprimir_resultados(resultados: dict[str, Any]) -> dict[str, dict]:
    """Reduz cada resultado de agente aos campos essenciais para o A-00.
    Evita inflar payload com JSON gigante de 27 outputs intermediários."""
    out: dict[str, dict] = {}
    for aid, r in resultados.items():
        if isinstance(r, dict):
            out[aid] = {
                "status":     r.get("status", "?"),
                "score":      r.get("score", r.get("score_global", 0)),
                "decisao":    r.get("decisao", "?"),
                "recomendacao": str(r.get("recomendacao_geral", r.get("resumo", "")))[:200],
            }
        else:
            out[aid] = {"status": "?", "raw": str(r)[:100]}
    return out


# Agentes redundantes/dispensáveis em auditoria rural focada
# (A-08 já cobre rural; A-26 biológicos é redundante; A-09 TI sem necessidade)
AGENTES_DISPENSAVEIS_RURAL = {"A-09", "A-26"}


def filtrar_pipeline(agentes: list[str], skip_redundantes: bool = True) -> list[str]:
    """Remove agentes redundantes para auditoria rural — economia adicional."""
    if not skip_redundantes:
        return list(agentes)
    return [a for a in agentes if a not in AGENTES_DISPENSAVEIS_RURAL]


PIPELINE_AUDITOR = ["A-07", "A-08", "A-23", "A-27", "A-00"]
PIPELINE_FULL = [
    "A-01", "A-02", "A-03", "A-04", "A-05", "A-06",
    "A-07", "A-08", "A-09", "A-10", "A-11", "A-12",
    "A-13", "A-14", "A-15", "A-16", "A-17", "A-18",
    "A-19", "A-20", "A-21", "A-22", "A-23", "A-24",
    "A-25", "A-26", "A-27", "A-00",
]


def posicao_e_produtor(arquivo: str) -> tuple[str, str]:
    base = arquivo.upper().replace(".PDF", "").strip()
    if base.endswith(" DEST"): return "DESTINATARIO", base[:-5].strip()
    if base.endswith(" REM"):  return "REMETENTE",    base[:-4].strip()
    return "DESCONHECIDO", base


def extrair_e_classificar(pdf_path: Path) -> tuple[list[dict], str, str]:
    """Extrai notas e aplica RE-1 — etapa puramente determinística.
    Retorna (notas_classificadas, posicao, produtor)."""
    posicao, produtor = posicao_e_produtor(pdf_path.name)
    notas, _, _ = extrair_notas(str(pdf_path))
    notas_dict: list[dict] = []
    for n in notas:
        d = n.model_dump()
        d.update(
            posicao=posicao, atividade="bovino", tipo_doc="nfa-e",
            produtor=produtor, pdf_origem=pdf_path.name,
        )
        d = aplicar_regra_especial_1(d)
        notas_dict.append(d)
    return notas_dict, posicao, produtor


LEGACY_OUTPUT_MEDIO = 1500   # tokens/chamada — antes da calibração max_tokens

def custo_baseline_sonnet(snap: dict, n_chamadas: int = 0) -> float:
    """Calcula custo do cenário LEGADO antes das otimizações:
    - Todas as chamadas em Sonnet (sem mix Haiku/Opus)
    - max_tokens=4096 default → output médio histórico ~1500 tokens
    - Sem prompt cache

    Usa os tokens_input REAIS do squad (prompt construído pelos agentes)
    e estima output legado fixo. A diferença vs custo atual é a economia
    obtida pelas alavancas (mix 80/15/5 + max_tokens calibrado).
    """
    total_t_in = sum(snap.get("tokens_input", {}).values())
    if n_chamadas == 0:
        n_chamadas = sum(snap.get("chamadas", {}).values())
    legacy_out = n_chamadas * LEGACY_OUTPUT_MEDIO
    custo_in = total_t_in * _CUSTO_INPUT[ModelType.SONNET] / 1_000_000
    custo_out = legacy_out * _CUSTO_OUTPUT[ModelType.SONNET] / 1_000_000
    return custo_in + custo_out


async def rodar_squad(
    notas: list[dict],
    pipeline: list[str],
    score: float,
    contribuinte: dict[str, str],
    modo: str = "mock",
) -> dict:
    """Roda o Orchestrator com instrumentação. Devolve snapshot de tokens.

    Otimizações aplicadas:
    - Cap de notas por modelo do agente (Opus=20, Sonnet=40, Haiku=150)
    - resultados_agentes comprimido antes de passar adiante
    - Cache de system prompt simulado (90% hit, 90% desconto)
    """
    payload_full = _build_payload(notas, score, contribuinte)

    # IMPORTANTE: setar num_notas/score antes de chamar agentes
    set_num_notas(len(notas))

    reset_stats()
    # NÃO reseta cache de system entre PDFs — em produção, agentes
    # têm system fixo e cache Anthropic dura por toda a sessão.
    # O reset acontece só no início da execução completa (no entry).
    with instrumentar(modo=modo):
        # Wrapper: cada agente roda dentro de agente_ativo()
        # mas o Orchestrator não tem hook para isso — vamos fazer
        # o tracking via post-snapshot global por enquanto.
        # Para tracking por agente, executamos os agentes manualmente.
        from horizon_blue_one.agents.base_agent import BaseAgent
        import importlib

        chamadas: list[dict] = []
        resultados: dict = {}
        # Acumulado de resultados pré-compressão (referência interna)
        _raw_results: dict[str, dict] = {}

        for aid in pipeline:
            mod_nome = _AGENT_MOD[aid]
            mod = importlib.import_module(f"horizon_blue_one.agents.{mod_nome}")
            Cls = _find_agent_class(mod)
            if Cls is None:
                continue
            agente = Cls()

            # Decide modelo deste agente para aplicar cap correto de notas
            from horizon_blue_one.core.token_router import rotear, TipoTarefa
            d = rotear(tipo_tarefa=TipoTarefa.AUDITORIA,
                       score_risco=score, num_notas=len(notas), agent_id=aid)
            notas_capadas = cap_notas_para_modelo(notas, d.modelo.value, agent_id=aid)
            # Compactar JSON: abrevia keys + remove zeros/nulos -> -30% chars
            notas_compactas = compactar_notas(notas_capadas)

            # Payload deste agente: notas compactas + resultados COMPRIMIDOS
            payload_agente = dict(payload_full)
            payload_agente["notas"] = notas_compactas
            payload_agente["notas_classificadas"] = notas_compactas
            payload_agente["resultados_agentes"] = comprimir_resultados(_raw_results)

            # Snapshot ANTES de rodar este agente
            snap_pre = snapshot_stats()
            with agente_ativo(aid, num_notas=len(notas_capadas), score=score):
                try:
                    res = await agente.process(payload_agente)
                    resultados[aid] = res
                    _raw_results[aid] = (
                        res.output if isinstance(res.output, dict) else {"raw": str(res.output)}
                    )
                except Exception as exc:
                    chamadas.append({
                        "agent_id": aid, "modelo": "?",
                        "tokens_in": 0, "tokens_out": 0, "custo_usd": 0.0,
                        "erro": f"{type(exc).__name__}: {str(exc)[:120]}",
                    })
                    continue

            # Snapshot DEPOIS — diferença é o que esse agente consumiu
            snap_pos = snapshot_stats()
            delta = _diff_snapshot(snap_pre, snap_pos)
            delta["notas_enviadas"] = len(notas_capadas)
            delta["notas_originais"] = len(notas)
            if delta["tokens_in"] > 0:
                chamadas.append({"agent_id": aid, **delta})

    final_snap = snapshot_stats()
    return {
        "chamadas": chamadas,
        "totais": _consolidar_totais(final_snap),
        "resultados": {k: _resumir_result(v) for k, v in resultados.items()},
        "snap": final_snap.get("resumo", {}),
    }


# ── Helpers internos ─────────────────────────────────────────────────────────

_AGENT_MOD = {
    "A-00":"a00_ceo","A-01":"a01_junior","A-02":"a02_protetor","A-03":"a03_zerotrust",
    "A-04":"a04_vigilante","A-05":"a05_engenheiro_erp","A-06":"a06_extrator",
    "A-07":"a07_auditoria_assurance","A-08":"a08_auditor_nfa","A-09":"a09_auditor_ti",
    "A-10":"a10_auditor_patrimonio","A-11":"a11_planejador_tributario",
    "A-12":"a12_descobridor_deducoes","A-13":"a13_monitor_conformidade",
    "A-14":"a14_avaliador_risco","A-15":"a15_juridico_ext","A-16":"a16_lgpd",
    "A-17":"a17_previsor_caixa","A-18":"a18_analista_csuite","A-19":"a19_contabilista_ia",
    "A-20":"a20_esocial_ia","A-21":"a21_auditor_icms","A-22":"a22_auditor_itr",
    "A-23":"a23_analista_anomalias","A-24":"a24_classificador_cfop",
    "A-25":"a25_auditor_lcdpr","A-26":"a26_auditor_biologicos","A-27":"a27_epsilon_forensic",
}


def _find_agent_class(mod):
    from horizon_blue_one.agents.base_agent import BaseAgent
    for nome in dir(mod):
        obj = getattr(mod, nome)
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent:
            return obj
    return None


def _build_payload(notas: list[dict], score: float, contrib: dict) -> dict:
    """Payload mínimo (rev v3) — apenas chaves consumidas pelos agentes.
    Campos zerados/não-usados foram removidos para reduzir tokens IN."""
    fiscal = apurar_resumo(notas, eh_pj=False, eh_segurado_especial=True,
                           data_referencia=date(2026, 6, 1))
    # Estruturas vazias só quando o agente exige (ITR/eSocial são só keys '?')
    return {
        "notas":                  notas,
        "notas_classificadas":    notas,
        "contribuinte":           contrib,
        "is_pj":                  False,
        "score_risco":            score,
        "valor_total":            fiscal.f1_receita_imediata,
        "tipologias_criticas":    0,
        "probabilidade_autuacao": 0.15,
        "regime_atual":           "PF Rural",
        "receita_bruta":          fiscal.f1_receita_imediata,
        "score_info":             {"score": score, "shap_values": {}},
        "shap_values":            {},
        "esocial_data":           {},
        "itr_data":               {},
        "lcdpr_data":             {},
        "dados_erp":              {},
        "sistema_erp":            "g",
        "formato":                "nfa-e",
        "texto_nfa":              "",
        "tipo_analise":           "auditoria",
        "contexto":               contrib.get("nome", "audit"),
        "requisicao_id":          f"s{int(time.time())%100000}",
        "entidades":              [],
        "detectores_pre":         {},
    }


def _diff_snapshot(pre: dict, pos: dict) -> dict:
    """Diferença entre dois snapshots — extrai tokens/custo dessa chamada."""
    pre_t_in = sum(pre.get("tokens_input", {}).values())
    pos_t_in = sum(pos.get("tokens_input", {}).values())
    pre_t_out = sum(pre.get("tokens_output", {}).values())
    pos_t_out = sum(pos.get("tokens_output", {}).values())
    pre_custo = sum(pre.get("custo_usd", {}).values())
    pos_custo = sum(pos.get("custo_usd", {}).values())

    # Identifica modelo predominante usando diff de chamadas
    modelo = "haiku"
    chamadas_pre = pre.get("chamadas", {})
    chamadas_pos = pos.get("chamadas", {})
    for m in ("opus", "sonnet", "haiku"):
        if chamadas_pos.get(m, 0) > chamadas_pre.get(m, 0):
            modelo = m
            break
    return {
        "modelo": modelo,
        "tokens_in":  pos_t_in - pre_t_in,
        "tokens_out": pos_t_out - pre_t_out,
        "custo_usd":  round(pos_custo - pre_custo, 6),
    }


def _consolidar_totais(snap: dict) -> dict:
    t_in = sum(snap.get("tokens_input", {}).values())
    t_out = sum(snap.get("tokens_output", {}).values())
    custo = sum(snap.get("custo_usd", {}).values())
    n_chamadas = sum(snap.get("chamadas", {}).values())
    custo_base = custo_baseline_sonnet(snap, n_chamadas=n_chamadas)
    return {
        "tokens_in":             t_in,
        "tokens_out":            t_out,
        "custo_usd":             round(custo, 6),
        "custo_baseline_sonnet": round(custo_base, 6),
        "economia_pct":          round(
            (custo_base - custo) / custo_base * 100
            if custo_base > 0 else 0, 2),
        "distribuicao":          dict(snap.get("chamadas", {})),
    }


def _resumir_result(res: Any) -> dict:
    """Extrai apenas campos textuais relevantes para ground-truth match."""
    if not res or not hasattr(res, "output"):
        return {"status": getattr(res, "status", "?")}
    out = res.output if isinstance(res.output, dict) else {}
    return {
        "status":             getattr(res, "status", "?"),
        "confidence":         round(getattr(res, "confidence", 0.0), 2),
        "recomendacao_geral": str(out.get("recomendacao_geral", ""))[:500],
        "resumo_executivo":   str(out.get("narrativa_executiva", out.get("resumo", "")))[:500],
        "score":              out.get("score", out.get("score_global", 0)),
    }
