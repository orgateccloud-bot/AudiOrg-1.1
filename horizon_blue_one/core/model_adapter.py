"""ModelAdapter — Claude Sonnet/Haiku/Opus com retry e prompt caching.

Recursos:
- Retry com backoff exponencial via tenacity (3 tentativas, 1–8s)
- Prompt caching ephemeral (~90% de economia em system prompts repetidos)
- Cliente lazy (criado na primeira chamada, evita erro de import sem API key)
- Motor único: Anthropic Claude (Sonnet 4.6 / Haiku 4.5 / Opus 4.7)
"""
import time
import logging
import structlog
from enum import Enum

import anthropic
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

from horizon_blue_one.core.config import settings

logger      = structlog.get_logger()
_stdlogger  = logging.getLogger("model_adapter")

# ─── Cliente lazy ─────────────────────────────────────────────────────────────
_client_claude: anthropic.AsyncAnthropic | None = None


def _get_claude() -> anthropic.AsyncAnthropic:
    global _client_claude
    if _client_claude is None:
        _client_claude = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client_claude


class ModelType(str, Enum):
    CLAUDE  = "claude"    # alias → Sonnet
    SONNET  = "sonnet"    # claude-sonnet-4-6
    HAIKU   = "haiku"     # claude-haiku-4-5  (alto volume, roteamento)
    OPUS    = "opus"      # claude-opus-4-7   (casos críticos, score > 85)


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


async def call_model(
    model_type: ModelType,
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
) -> str:
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
        logger.info("model_call_ok", model=model_type.value, ms=ms, chars=len(resp))
        return resp
    except RECOVERABLE as exc:
        ms = round((time.monotonic() - inicio) * 1000, 2)
        logger.warning("model_call_falhou", model=model_type.value, ms=ms, erro=str(exc))
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(RECOVERABLE),
    before_sleep=before_sleep_log(_stdlogger, logging.WARNING),
    reraise=True,
)
async def _call_claude(prompt: str, system: str, max_tokens: int, model_id: str) -> str:
    msgs   = [{"role": "user", "content": prompt}]
    kwargs = {"model": model_id, "max_tokens": max_tokens, "messages": msgs}
    sys_p  = _build_system_param(system)
    if sys_p:
        kwargs["system"] = sys_p
    resp = await _get_claude().messages.create(**kwargs)
    return resp.content[0].text
