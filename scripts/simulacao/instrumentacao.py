"""
Instrumentação para modo MOCK — substitui call_model por uma versão
que estima tokens com base no PROMPT REAL construído pelo agente,
sem chamar a Claude API.

Inclui simulação de prompt caching (90% hit rate, 90% desconto no system).
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
from typing import Any, AsyncIterator, Iterator
from unittest.mock import patch

from horizon_blue_one.core.token_router import (
    TipoTarefa, _CUSTO_INPUT, _CUSTO_OUTPUT, registrar_uso, rotear,
)
from horizon_blue_one.core.model_adapter import ModelType


# ── Cache de system prompts (simulação) ──────────────────────────────────────
# 1ª chamada com determinado system: paga 100% do input do system
# Chamadas seguintes (até hit_rate): paga 10% do input do system
_SYSTEM_CACHE_SEEN: set[str] = set()
_CACHE_HIT_DESCONTO = 0.10   # cache hit custa 10% do preço (Anthropic ephemeral)
_CACHE_HIT_RATE_TARGET = 0.95  # alvo: 95% das chamadas após a primeira (rev v2)


def reset_cache():
    """Reseta o cache de system prompts (chamar entre PDFs/produtores)."""
    _SYSTEM_CACHE_SEEN.clear()


# ── Contexto thread-safe para identificar o agente atualmente ativo ──────────
_active_agent: contextvars.ContextVar[str] = contextvars.ContextVar(
    "active_agent", default="?"
)
_active_num_notas: contextvars.ContextVar[int] = contextvars.ContextVar(
    "active_num_notas", default=0
)
_active_score: contextvars.ContextVar[float] = contextvars.ContextVar(
    "active_score", default=0.0
)


# ── JSON fake compatível com schemas dos 28 agentes ──────────────────────────
def _make_fake_response(agent_id: str) -> str:
    """Devolve JSON com TODOS os campos esperados pelos schemas dos agentes
    (NFAAuditSchema, planejador, csuite, esocial, itr, anomalias, etc)."""
    return json.dumps({
        # Genéricos
        "status": "APROVADO", "confidence": 0.85, "decisao": "APROVADO",
        "score": 50, "score_risco": 50, "score_global": 50,
        "tipologias": [], "tipologias_criticas": [],
        "anomalias": [], "anomalias_detectadas": [],
        "achados": [], "alertas": [],
        "recomendacoes": ["Mock determinístico"],
        "acoes_recomendadas": [],
        "justificativa": "Mock para simulação de consumo.",
        "resumo": "Sem indícios críticos no modo mock.",
        "categoria": "MEDIO", "severidade": "MEDIA",
        # NFAAuditSchema (A-08)
        "f1_receita_imediata": 0.0, "f2_transito": 0.0,
        "f4_receita_bruta": 0.0, "f6_despesa": 0.0,
        "f5_resultado_rural": 0.0, "funrural": 0.0,
        "aliquota_funrural": 0.0163, "irpf_estimado": 0.0,
        "total_notas": 0, "notas_re1_aplicada": 0,
        "probabilidade_autuacao": 0.15, "desvio_mercado_cepea": 0.05,
        "recomendacao_geral": "Mock — sem chamada real",
        "proximos_passos": ["Validar"],
        # Planejador-Tributário (A-11)
        "regime_recomendado": "PF Rural", "economia_estimada": 0.0,
        "comparativo": {"PF": 0}, "tributos_estimados": {"funrural": 0},
        # C-Suite (A-18)
        "kpis": {}, "narrativa_executiva": "Mock",
        # eSocial (A-20)
        "eventos_pendentes": [], "compliance_score": 0.95,
        # ITR (A-22)
        "itr_devido": 0.0, "isencao_itr": False,
        "diagnostico_itr": "Mock",
        # Anomalias (A-23)
        "shap_values": {}, "drivers_top": [],
        # Forense (A-27)
        "conclusao": "Mock", "risco_conluio": "BAIXO",
        # Geral
        "deducoes_encontradas": [],
        "previsao_caixa": {"30d": 0, "60d": 0, "90d": 0},
        "modelo_usado": "haiku",
    }, ensure_ascii=False)


# ── Mock principal ───────────────────────────────────────────────────────────
async def _fake_call_model(
    model_type: ModelType, prompt: str, system: str = "", max_tokens: int = 4096,
) -> str:
    """Substituto de call_model em modo mock.

    Simula:
    - Tokens reais do prompt (len/4)
    - Roteamento via rotear() respeitando mix 80/15/5
    - Prompt caching ephemeral: system com hash repetido → 90% desconto
    - max_tokens calibrado por agente (output ratio 40%)
    """
    aid = _active_agent.get()
    num_notas = _active_num_notas.get()
    score = _active_score.get()

    decision = rotear(
        tipo_tarefa=TipoTarefa.AUDITORIA,
        score_risco=score, num_notas=num_notas, agent_id=aid,
    )

    # Tokens — system separado do user para simular cache
    sys_tokens = max(1, len(system) // 4)
    user_tokens = max(1, len(prompt) // 4)

    # Cache hit no system?
    sys_hash = hashlib.md5(system.encode("utf-8")).hexdigest() if system else ""
    if sys_hash and sys_hash in _SYSTEM_CACHE_SEEN:
        # Hit: custo do system reduzido a 10% (efetivo)
        sys_tokens_efetivos = int(sys_tokens * _CACHE_HIT_DESCONTO)
    else:
        # Miss: custo cheio + adiciona ao cache
        sys_tokens_efetivos = sys_tokens
        if sys_hash:
            _SYSTEM_CACHE_SEEN.add(sys_hash)

    tokens_in = sys_tokens_efetivos + user_tokens
    # Output ratio 30% (Claude é conciso quando recebe schema rigoroso)
    tokens_out = min(max_tokens, max(50, int(user_tokens * 0.30)))

    registrar_uso(decision.modelo, tokens_in, tokens_out, decision)
    return _make_fake_response(aid)


# ── Helpers de contexto ──────────────────────────────────────────────────────

@contextlib.contextmanager
def agente_ativo(agent_id: str, num_notas: int = 0, score: float = 0.0) -> Iterator[None]:
    """Define o agente ativo durante o bloco — usado para colorir
    as chamadas a call_model com o agent_id correto."""
    t1 = _active_agent.set(agent_id)
    t2 = _active_num_notas.set(num_notas)
    t3 = _active_score.set(score)
    try:
        yield
    finally:
        _active_agent.reset(t1)
        _active_num_notas.reset(t2)
        _active_score.reset(t3)


def set_num_notas(n: int) -> None:
    """Atualiza o ContextVar global de num_notas (escopo da chamada atual)."""
    _active_num_notas.set(n)


@contextlib.contextmanager
def instrumentar(modo: str = "mock") -> Iterator[None]:
    """Patcheia call_model para a versão fake durante o bloco. Em modo
    'real', não faz nada — call_model real é usado."""
    if modo == "mock":
        with patch(
            "horizon_blue_one.core.model_adapter.call_model",
            side_effect=_fake_call_model,
        ):
            yield
    else:
        yield
