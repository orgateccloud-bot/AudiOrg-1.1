"""
Motor de Orquestração de Agentes — Pipeline Sigma → Gama → Auditor (Claude).

Otimizações de contexto:
  1. Context pruning: Sigma recebe métricas numéricas, não texto bruto.
  2. Gama recebe JSON do Sigma (estruturado), não texto livre.
  3. Auditor recebe resumo compacto dos 2 agentes anteriores.
  4. Cada nó limita o tamanho do contexto que passa ao modelo.
  5. Logging estruturado por nó para rastreabilidade.
"""

from __future__ import annotations

import json
import logging
import operator
from typing import Annotated, Any, List, TypedDict

from langgraph.graph import END, StateGraph

from nfa_extractor.domain.extractor import NFA, resumo_geral
from nfa_extractor.infrastructure.ai_client import (
    SYSTEM_AUDITOR,
    SYSTEM_GAMA,
    SYSTEM_SIGMA,
    analisar_com_resumo,
)

logger = logging.getLogger("agents_engine")

# Limite máximo de caracteres de contexto entre agentes.
# Limite de contexto entre agentes — economiza tokens de input.
_MAX_CONTEXT_CHARS: int = 1500


class AgentState(TypedDict):
    """Estado compartilhado entre os nós do grafo de agentes."""
    notas: List[NFA]
    nome_contribuinte: str
    contexto_quant: dict
    analise_sigma: str
    analise_gama: str
    veredito_final: str
    historico: Annotated[List[str], operator.add]


def _truncar(texto: str, limite: int = _MAX_CONTEXT_CHARS) -> str:
    """Trunca texto para caber na janela de contexto do modelo."""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + "... [TRUNCADO]"


def _extrair_metricas_compactas(
    notas: list[NFA],
    nome_contribuinte: str,
) -> dict[str, Any]:
    """Extrai métricas consolidadas das notas — formato compacto para o modelo.

    Retorna apenas números e categorias, sem dados textuais extensos.
    Isso reduz tokens de input em ~70%.
    """
    resumo = resumo_geral(notas, nome_contribuinte=nome_contribuinte)
    return {
        "contribuinte": nome_contribuinte,
        "total_notas": resumo["total_notas"],
        "total_valor": round(resumo["total_valor"], 2),
        "total_cabecas": round(resumo["total_cabecas"], 1),
        "ticket_medio": round(resumo["ticket_medio"], 2),
        "vendas": {
            "notas": resumo.get("vendas_notas", 0),
            "valor": round(resumo.get("vendas_valor", 0), 2),
            "cabecas": round(resumo.get("vendas_cabecas", 0), 1),
        },
        "por_natureza": resumo["por_natureza"],
        "top_destinatarios": [
            {"nome": d["nome"], "valor": round(d["valor"], 2), "cabecas": round(d["cabecas"], 1)}
            for d in resumo.get("top_dest", [])[:5]
        ],
    }


# ── Nós do Grafo ─────────────────────────────────────────────────────────────

def node_sigma(state: AgentState) -> dict:
    """@Sigma: Análise quantitativa e detecção de anomalias.

    Recebe métricas numéricas pré-calculadas + ground truth da engine.
    Não recebe texto livre nem notas brutas — economia de ~70% de tokens.
    """
    logger.info("[SIGMA] Iniciando análise quantitativa...")
    cq = state["contexto_quant"]

    # Monta input compacto: métricas + ground truth
    metricas = _extrair_metricas_compactas(state["notas"], state["nome_contribuinte"])
    input_sigma: dict[str, Any] = {
        "ground_truth": {
            "risk_score": cq.get("risk_score", 0),
            "fraud_level": cq.get("fraud_level", "NONE"),
        },
        "metricas": metricas,
    }

    resultado = analisar_com_resumo(
        input_sigma,
        SYSTEM_SIGMA,
        nome_produtor=state["nome_contribuinte"],
    )
    logger.info(f"[SIGMA] Concluído ({len(resultado)} chars)")

    return {
        "analise_sigma": resultado,
        "historico": ["Sigma: análise quantitativa concluída."],
    }


def node_gama(state: AgentState) -> dict:
    """@Gama: Parecer jurídico e compliance fiscal.

    Recebe:
    - Output JSON do Sigma (truncado se necessário)
    - Risk score da engine quantitativa
    Não recebe notas brutas.
    """
    logger.info("[GAMA] Iniciando parecer jurídico...")
    cq = state["contexto_quant"]

    input_gama: dict[str, Any] = {
        "analise_quantitativa": _truncar(state["analise_sigma"]),
        "risk_score": cq.get("risk_score", 0),
        "fraud_level": cq.get("fraud_level", "NONE"),
        "contribuinte": state["nome_contribuinte"],
    }

    resultado = analisar_com_resumo(
        input_gama,
        SYSTEM_GAMA,
        nome_produtor=state["nome_contribuinte"],
    )
    logger.info(f"[GAMA] Concluído ({len(resultado)} chars)")

    return {
        "analise_gama": resultado,
        "historico": ["Gama: parecer jurídico concluído."],
    }


def node_auditor(state: AgentState) -> dict:
    """Auditor-Chefe: Consolidação forense final.

    Recebe:
    - Métricas compactas das notas
    - Output do Sigma (truncado)
    - Output do Gama (truncado)
    - Ground truth da engine quantitativa
    """
    logger.info("[AUDITOR] Gerando veredito final...")
    cq = state["contexto_quant"]

    metricas = _extrair_metricas_compactas(state["notas"], state["nome_contribuinte"])
    input_auditor: dict[str, Any] = {
        "metricas_lote": metricas,
        "ground_truth": {
            "risk_score": cq.get("risk_score", 0),
            "fraud_level": cq.get("fraud_level", "NONE"),
        },
        "sigma": _truncar(state["analise_sigma"], 800),
        "gama": _truncar(state["analise_gama"], 600),
    }

    resultado = analisar_com_resumo(
        input_auditor,
        SYSTEM_AUDITOR,
        nome_produtor=state["nome_contribuinte"],
    )
    logger.info(f"[AUDITOR] Veredito emitido ({len(resultado)} chars)")

    return {
        "veredito_final": resultado,
        "historico": ["Auditor: veredito soberano emitido."],
    }


# ── Grafo ────────────────────────────────────────────────────────────────────

def build_graph() -> Any:
    """Constrói o grafo sequencial Sigma → Gama → Auditor."""
    workflow = StateGraph(AgentState)
    workflow.add_node("sigma", node_sigma)
    workflow.add_node("gama", node_gama)
    workflow.add_node("auditor", node_auditor)

    workflow.set_entry_point("sigma")
    workflow.add_edge("sigma", "gama")
    workflow.add_edge("gama", "auditor")
    workflow.add_edge("auditor", END)

    return workflow.compile()


def rodar_auditoria_completa(
    notas: list[NFA],
    nome_contribuinte: str,
    contexto_quant: dict | None = None,
) -> dict:
    """Executa a auditoria completa: Sigma → Gama → Auditor.

    Args:
        notas: Lista de NFAs extraídas do PDF.
        nome_contribuinte: Nome do contribuinte auditado.
        contexto_quant: Ground truth da AntiGravityQuantEngine (risk_score, fraud_level).

    Returns:
        Estado final com analise_sigma, analise_gama, veredito_final e historico.
    """
    app = build_graph()
    initial_state: AgentState = {
        "notas": notas,
        "nome_contribuinte": nome_contribuinte,
        "contexto_quant": contexto_quant or {},
        "analise_sigma": "",
        "analise_gama": "",
        "veredito_final": "",
        "historico": [],
    }
    return app.invoke(initial_state)
