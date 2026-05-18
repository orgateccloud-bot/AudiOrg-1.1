"""ModelAdapter — Claude Sonnet/Haiku/Opus com retry, prompt caching e métricas.
Recursos:
- Retry com backoff exponencial via tenacity (3 tentativas, 1–8s)
- Prompt caching ephemeral (~90% de economia em system prompts repetidos)
- Cliente lazy (criado na primeira chamada, evita erro de import sem API key)
- Motor único: Anthropic Claude (Sonnet 4.6 / Haiku 4.5 / Opus 4.7)
- Log de usage_metadata (input_tokens, output_tokens, cache_hits) por chamada
- Métricas Prometheus opcionais via counter/histogram quando disponíveis
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

import anthropic
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from horizon_blue_one.core.config import settings

logger = structlog.get_logger()
_stdlogger = logging.getLogger("model_adapter")

# ─── Cliente lazy ──────────────────────────────────────────────────────────────
_client_claude: Optional[anthropic.AsyncAnthropic] = None


def _get_claude() -> anthropic.AsyncAnthropic:
    global _client_claude
    if _client_claude is None:
        _client_claude = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client_claude


class ModelType(str, Enum):
    CLAUDE = "claude"    # alias → Sonnet
    SONNET = "sonnet"    # claude-sonnet-4-6
    HAIKU = "haiku"      # claude-haiku-4-5 (alto volume, roteamento)
    OPUS = "opus"        # claude-opus-4-7 (casos críticos, score > 85)


RECOVERABLE = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
)


def _build_system_param(system: str) -> list | None:
    """Constrói parâmetro system com cache_control ephemeral (TTL 5 min)."""
    if not system:
        return None
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def _log_usage(model_type: ModelType, resp: anthropic.types.Message, ms: float) -> None:
    """Loga tokens consumidos e cache hits para controle de custos."""
    usage = resp.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    logger.info(
        "model_usage",
        model=model_type.value,
        ms=ms,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=cache_read,
        cache_create_tokens=cache_create,
        chars_out=len(resp.content[0].text) if resp.content else 0,
    )

    # Prometheus opcional (não bloqueia se indisponível)
    try:
        from horizon_blue_one.core.metrics import (
            MODEL_TOKENS_IN,
            MODEL_TOKENS_OUT,
            MODEL_LATENCY,
        )
        MODEL_TOKENS_IN.labels(model=model_type.value).inc(usage.input_tokens)
        MODEL_TOKENS_OUT.labels(model=model_type.value).inc(usage.output_tokens)
        MODEL_LATENCY.labels(model=model_type.value).observe(ms / 1000)
    except ImportError:
        pass


async def call_model(
    model_type: ModelType,
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
) -> str:
    """Chama o modelo Claude com retry automático e log de usage."""
    inicio = time.monotonic()
    if model_type in (ModelType.CLAUDE, ModelType.SONNET):
        model_id = settings.CLAUDE_MODEL_ID
    elif model_type == ModelType.HAIKU:
        model_id = settings.HAIKU_MODEL_ID
    elif model_type == ModelType.OPUS:
        model_id = settings.OPUS_MODEL_ID
    else:
        raise ValueError(f"Modelo não suportado: {model_type}")

    try:
        resp = await _call_claude(prompt, system, max_tokens, model_id)
        ms = round((time.monotonic() - inicio) * 1000, 2)
        _log_usage(model_type, resp, ms)
        return resp.content[0].text
    except RECOVERABLE as exc:
        ms = round((time.monotonic() - inicio) * 1000, 2)
        logger.warning(
            "model_call_falhou", model=model_type.value, ms=ms, erro=str(exc)
        )
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(RECOVERABLE),
    before_sleep=before_sleep_log(_stdlogger, logging.WARNING),
    reraise=True,
)
async def _call_claude(
    prompt: str, system: str, max_tokens: int, model_id: str
) -> anthropic.types.Message:
    """Chamada interna com retry — retorna o objeto Message completo."""
    msgs = [{"role": "user", "content": prompt}]
    kwargs: dict = {"model": model_id, "max_tokens": max_tokens, "messages": msgs}
    sys_p = _build_system_param(system)
    if sys_p:
        kwargs["system"] = sys_p
    return await _get_claude().messages.create(**kwargs)
