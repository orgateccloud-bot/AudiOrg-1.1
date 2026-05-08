"""
Cliente IA — Motor único: Claude (Anthropic).

Motor: Claude Sonnet (claude-sonnet-4-20250514) via ANTHROPIC_API_KEY.
Circuit breaker in-memory para resiliência.
System prompts compactos com output JSON forçado.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from nfa_extractor.domain.extractor import NFA, resumo_geral

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.env"

# ── Configuração de Modelos ──────────────────────────────────────────────────

# Limites de geração por função do agente
TOKEN_LIMITS: dict[str, int] = {
    "sigma": 1024,    # Análise quantitativa: números, não prosa
    "gama": 1536,     # Parecer jurídico: precisa de mais contexto
    "auditor": 2048,  # Consolidação final
    "chat": 1024,     # Conversacional
    "etl": 512,       # Extração pura
}


# ── System Prompts Otimizados ────────────────────────────────────────────────
# Máximo ~150 tokens por prompt. JSON mode forçado.
# Modelos 7B performam ~30% melhor com schema rígido.

SYSTEM_IPSILON = (
    "Processador ETL ORGATEC. Extraia totais agrupados por natureza. "
    'Responda APENAS em JSON: {"grupos": [{"natureza": str, "qtd_notas": int, '
    '"cabecas": float, "valor": float}]}'
)

SYSTEM_SIGMA = (
    "Você é @Sigma, analista quantitativo tributário.\n"
    "REGRAS: Use APENAS os dados fornecidos. Nunca invente valores. "
    "Responda EXCLUSIVAMENTE em JSON válido.\n"
    "SCHEMA: {"
    '"resumo": "string (máx 200 chars)", '
    '"total_notas": int, "valor_total": float, "cabecas_total": float, '
    '"ticket_medio": float, '
    '"anomalias": [{"tipo": str, "descricao": str, "severidade": "BAIXA|MEDIA|ALTA"}], '
    '"tendencia": "ESTAVEL|CRESCENTE|DECRESCENTE|IRREGULAR"}'
)

SYSTEM_GAMA = (
    "Você é @Gama, consultor tributário sênior.\n"
    "REGRAS: Baseie-se APENAS nos dados quantitativos. Nunca invente artigos. "
    "Responda EXCLUSIVAMENTE em JSON válido.\n"
    "SCHEMA: {"
    '"parecer": "string (máx 300 chars)", '
    '"risco_fiscal": "BAIXO|MEDIO|ALTO|CRITICO", '
    '"fundamentacao": ["string (artigos/normas)"], '
    '"recomendacoes": ["string"], '
    '"ressalvas": ["string"]}'
)

SYSTEM_AUDITOR = (
    "Você é o Auditor-Chefe da ORGATEC. Protocolo Soberano.\n"
    "REGRAS: ZERO ALUCINAÇÃO — dados insuficientes = declare 'DADOS INSUFICIENTES'. "
    "Toda conclusão DEVE citar NFA ou valor de origem. "
    "Responda EXCLUSIVAMENTE em JSON válido.\n"
    "SCHEMA: {"
    '"veredito": str, '
    '"entradas": {"cabecas": int, "valor": float}, '
    '"saidas": {"cabecas": int, "valor": float}, '
    '"anomalia_bio_contabil": {"diferenca_cabecas": int, "explicacao": str}, '
    '"hipotese_tecnica": str, '
    '"nivel_risco": "BAIXO|MEDIO|ALTO|SISTEMICO", '
    '"score_confianca": float, '
    '"evidencias": ["string"]}'
)

# Mapa de system prompts → função do agente (para calibrar token limits)
_SYSTEM_TO_ROLE: dict[int, str] = {
    id(SYSTEM_SIGMA): "sigma",
    id(SYSTEM_GAMA): "gama",
    id(SYSTEM_AUDITOR): "auditor",
    id(SYSTEM_IPSILON): "etl",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _carregar_env(chave: str) -> str:
    """Carrega variável de ambiente com fallback para config.env."""
    valor = os.getenv(chave, "")
    if valor:
        return valor
    if CONFIG_PATH.exists():
        for linha in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.startswith("#"):
                k, v = linha.strip().split("=", 1)
                if k.strip() == chave:
                    return v.strip()
    return ""


_PROMPT_SANITIZE = str.maketrans({"\x00": "", "\r": " "})


def _sanitizar_str(valor: str) -> str:
    """Remove caracteres perigosos para prompt injection."""
    if not isinstance(valor, str):
        return str(valor)
    return (
        valor.translate(_PROMPT_SANITIZE)
        .replace("{{", "{ {")
        .replace("}}", "} }")
        .strip()
    )


def _montar_prompt(notas: list[NFA]) -> str:
    """Monta prompt compacto — formato tabular, uma linha por nota."""
    if not notas:
        return "Nenhuma nota fiscal disponível."
    linhas = ["NFA|NAT|EMISSÃO|VALOR|CAPS"]
    for n in notas:
        nat = _sanitizar_str(n.natureza)[:12]
        emi = _sanitizar_str(n.emissao)
        linhas.append(f"{n.numero}|{nat}|{emi}|{n.valor_total:.2f}|{n.quantidade_total:.0f}")
    return "\n".join(linhas)


def _montar_prompt_compacto(resumo: dict[str, Any]) -> str:
    """Monta prompt a partir de métricas pré-calculadas (sem dados brutos).

    Reduz tokens de input em ~70% comparado a enviar notas individuais.
    """
    return json.dumps(resumo, ensure_ascii=False, separators=(",", ":"))


def _get_role(system: str) -> str:
    """Identifica a função do agente pelo system prompt."""
    return _SYSTEM_TO_ROLE.get(id(system), "chat")


# ── Circuit Breaker ──────────────────────────────────────────────────────────

@dataclass
class _CircuitState:
    """Estado interno de um provedor no circuit breaker."""
    failures: int = 0
    last_failure: float = 0.0
    is_open: bool = False
    total_calls: int = 0
    total_failures: int = 0
    total_latency: float = 0.0


class CircuitBreaker:
    """Circuit breaker leve para fallback entre provedores de IA.

    Após max_failures consecutivas, abre o circuito por cooldown segundos.
    Após o cooldown, permite uma tentativa (half-open).
    """

    def __init__(self, max_failures: int = 3, cooldown: float = 60.0) -> None:
        self._max = max_failures
        self._cooldown = cooldown
        self._states: dict[str, _CircuitState] = {}

    def _state(self, provider: str) -> _CircuitState:
        if provider not in self._states:
            self._states[provider] = _CircuitState()
        return self._states[provider]

    def is_available(self, provider: str) -> bool:
        """Verifica se o provedor pode receber requests."""
        s = self._state(provider)
        if not s.is_open:
            return True
        return time.monotonic() - s.last_failure >= self._cooldown

    def success(self, provider: str, latency: float) -> None:
        """Registra sucesso — reseta contagem de falhas."""
        s = self._state(provider)
        s.failures = 0
        s.is_open = False
        s.total_calls += 1
        s.total_latency += latency

    def failure(self, provider: str) -> None:
        """Registra falha — abre circuito se atingir limite."""
        s = self._state(provider)
        s.failures += 1
        s.total_calls += 1
        s.total_failures += 1
        s.last_failure = time.monotonic()
        if s.failures >= self._max:
            s.is_open = True

    def metrics(self) -> dict[str, dict]:
        """Retorna métricas por provedor para observabilidade."""
        return {
            name: {
                "calls": s.total_calls,
                "failures": s.total_failures,
                "avg_latency_ms": round((s.total_latency / s.total_calls) * 1000) if s.total_calls else 0,
                "circuit_open": s.is_open,
            }
            for name, s in self._states.items()
        }


_breaker = CircuitBreaker(max_failures=3, cooldown=60.0)


# ── Motores de IA ────────────────────────────────────────────────────────────

def _claude_generate(
    prompt: str,
    system: str,
    callback: Callable | None = None,
    max_tokens: int = 2048,
) -> str:
    """Motor Claude — único motor ativo. Requer ANTHROPIC_API_KEY."""
    import anthropic

    api_key = _carregar_env("ANTHROPIC_API_KEY")
    if not api_key or not api_key.startswith("sk-ant"):
        return "[Claude Inativo]"

    if not _breaker.is_available("claude"):
        return "[Claude Cooldown]"

    t0 = time.monotonic()
    try:
        client = anthropic.Anthropic(api_key=api_key)
        res = ""
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for t in stream.text_stream:
                res += t
                if callback:
                    callback(t)
        _breaker.success("claude", time.monotonic() - t0)
        return res
    except Exception as e:
        _breaker.failure("claude")
        logger.error(f"Claude: {e}")
        return f"[Claude Falhou: {e}]"


# ── Detecção de Falha ────────────────────────────────────────────────────────

def _is_failure(result: str) -> bool:
    """Detecta se o resultado indica falha do provedor."""
    markers = ["Falhou", "Inativo", "Erro", "Cooldown", "Indisponível"]
    return result.startswith("[") and any(m in result for m in markers)


# Motor único: Claude
_PROVIDER_PRIORITY: list[tuple[str, Callable]] = [
    ("claude", _claude_generate),
]


# ── API Pública ──────────────────────────────────────────────────────────────

def analisar(
    notas: list[NFA],
    callback: Callable | None = None,
    system_override: str | None = None,
    provedor: str = "auto",
    nome_produtor: str = "",
) -> str:
    """Orquestrador principal — motor Claude.

    - Circuit breaker in-memory para resiliência
    - Token limit calibrado por função do agente
    - Prompt compacto formato tabular
    """
    prompt = _montar_prompt(notas)
    if nome_produtor:
        prompt = f"ALVO: {nome_produtor}\n{prompt}"

    sys = system_override or SYSTEM_GAMA
    role = _get_role(sys)
    max_tokens = TOKEN_LIMITS.get(role, 1024)

    # Provedor específico solicitado (atualmente apenas "claude")
    if provedor == "claude":
        return _claude_generate(prompt, sys, callback, max_tokens=max_tokens)

    # Modo auto: motor único Claude com circuit breaker
    result = _claude_generate(prompt, sys, callback, max_tokens=max_tokens)
    if not _is_failure(result):
        return result
    if callback:
        callback("\n[!] claude indisponível.\n")

    return "[ERRO] Todos os provedores de IA estão indisponíveis."


def analisar_com_resumo(
    resumo: dict[str, Any],
    system: str,
    callback: Callable | None = None,
    nome_produtor: str = "",
) -> str:
    """Analisa a partir de métricas pré-calculadas (sem dados brutos).

    Reduz tokens de input em ~70% comparado a enviar notas individuais.
    Ideal para o pipeline Sigma → Gama → Auditor.
    """
    prompt = _montar_prompt_compacto(resumo)
    if nome_produtor:
        prompt = f"ALVO: {nome_produtor}\n{prompt}"

    role = _get_role(system)
    max_tokens = TOKEN_LIMITS.get(role, 1024)
    return _claude_generate(prompt, system, callback, max_tokens=max_tokens)


def analisar_pipeline(
    notas: list[NFA],
    callback: Callable | None = None,
    batch_size: int = 20,
    nome_contribuinte: str = "",
) -> str:
    """Pipeline em lotes para conjuntos grandes de NFAs.

    Cada lote é comprimido em métricas antes de ir ao Claude — economiza ~70% de tokens.
    Sigma recebe 1 chamada consolidada; Auditor recebe JSON compacto.
    """
    if callback:
        callback(f"\n[SQUAD] {len(notas)} notas em lotes de {batch_size}...\n")

    metricas_lotes: list[dict] = []
    total_lotes = (len(notas) + batch_size - 1) // batch_size

    for i in range(0, len(notas), batch_size):
        lote_num = (i // batch_size) + 1
        lote = notas[i : i + batch_size]
        if callback:
            callback(f"── Lote {lote_num}/{total_lotes} ({len(lote)} notas) ── ")

        # Comprimir lote em métricas numéricas (zero chamada de IA aqui)
        resumo_lote = resumo_geral(lote, nome_contribuinte=nome_contribuinte)
        metricas_lotes.append({
            "lote": lote_num,
            "notas": resumo_lote["total_notas"],
            "valor": round(resumo_lote["total_valor"], 2),
            "cabecas": round(resumo_lote["total_cabecas"], 1),
            "ticket_medio": round(resumo_lote["ticket_medio"], 2),
            "por_natureza": resumo_lote["por_natureza"],
        })
        if callback:
            callback("[OK]\n")

    # Sigma analisa métricas consolidadas (1 chamada, não N)
    if callback:
        callback("\n── @Sigma: Análise Quantitativa ──\n")

    consolidado = {
        "contribuinte": nome_contribuinte,
        "total_notas": len(notas),
        "total_valor": sum(m["valor"] for m in metricas_lotes),
        "total_cabecas": sum(m["cabecas"] for m in metricas_lotes),
        "lotes": metricas_lotes,
    }

    sigma_result = analisar_com_resumo(
        consolidado, SYSTEM_SIGMA, callback, nome_contribuinte,
    )

    # Auditor consolida com base em Sigma + métricas
    if callback:
        callback("\n\n── @Auditor: Veredito Final ──\n")

    prompt_auditor = json.dumps(
        {"metricas": consolidado, "analise_sigma": sigma_result},
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return _claude_generate(
        prompt_auditor,
        SYSTEM_AUDITOR,
        callback,
        max_tokens=TOKEN_LIMITS["auditor"],
    )


def perguntar(
    notas: list[NFA],
    context_ia: str = "",
    pergunta: str = "",
) -> str:
    """Endpoint de chat genérico para o agente conversacional."""
    prompt = pergunta
    if context_ia:
        prompt = f"CONTEXTO: {context_ia}\nPERGUNTA: {pergunta}"
    return analisar(notas, system_override=None)


def get_ai_metrics() -> dict:
    """Retorna métricas do circuit breaker para observabilidade."""
    return _breaker.metrics()
