"""ModelAdapter — Claude Sonnet/Haiku/Opus com retry, prompt caching e tool_use (MCP).

Recursos:
- Retry com backoff exponencial via tenacity (3 tentativas, 1–8s)
- Prompt caching ephemeral (~90% de economia em system prompts repetidos)
- Cliente lazy (criado na primeira chamada, evita erro de import sem API key)
- Motor único: Anthropic Claude (Sonnet 4.6 / Haiku 4.5 / Opus 4.7)
- call_model_with_tools(): suporte a tool_use (MCP bridge) com loop agentico
"""
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

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


# ─── Tool Use (MCP) ───────────────────────────────────────────────────────────

_MAX_TOOL_ROUNDS = 5  # evita loop infinito em alucinações de tool_use


async def call_model_with_tools(
    model_type: ModelType,
    prompt: str,
    system: str = "",
    max_tokens: int = 4096,
    tools: list[dict] | None = None,
    tool_handler: Callable[[str, dict], Awaitable[str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Chama Claude com tool_use (MCP bridge) e executa o loop agentico.

    Executa rounds de tool_use até stop_reason == 'end_turn' ou limite.

    Args:
        tools:        Lista de schemas de ferramentas (formato Anthropic).
        tool_handler: Async callable(tool_name, tool_input) → str (JSON).

    Returns:
        (texto_final, uso) onde uso contém input_tokens, output_tokens, tool_calls.
    """
    if not tools or not tool_handler:
        texto = await call_model(model_type, prompt, system, max_tokens)
        return texto, {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0}

    if model_type in (ModelType.CLAUDE, ModelType.SONNET):
        model_id = settings.CLAUDE_MODEL_ID
    elif model_type == ModelType.HAIKU:
        model_id = settings.HAIKU_MODEL_ID
    elif model_type == ModelType.OPUS:
        model_id = settings.OPUS_MODEL_ID
    else:
        raise ValueError(f"Modelo não suportado: {model_type}")

    client    = _get_claude()
    sys_p     = _build_system_param(system)
    msgs: list[dict] = [{"role": "user", "content": prompt}]
    kwargs: dict     = {"model": model_id, "max_tokens": max_tokens, "tools": tools, "messages": msgs}
    if sys_p:
        kwargs["system"] = sys_p

    total_input  = 0
    total_output = 0
    tool_calls   = 0
    texto_final  = ""
    inicio       = time.monotonic()

    for rodada in range(_MAX_TOOL_ROUNDS):
        resp = await client.messages.create(**kwargs)
        total_input  += resp.usage.input_tokens
        total_output += resp.usage.output_tokens

        # Coleta texto e tool_use do response
        tool_uses  = [b for b in resp.content if b.type == "tool_use"]
        texto_blks = [b for b in resp.content if b.type == "text"]
        if texto_blks:
            texto_final = texto_blks[-1].text

        if resp.stop_reason != "tool_use" or not tool_uses:
            break

        # Executa ferramentas e monta próxima mensagem
        tool_results = []
        for tu in tool_uses:
            tool_calls += 1
            logger.info("mcp_tool_chamado", tool=tu.name, rodada=rodada + 1)
            resultado = await tool_handler(tu.name, tu.input)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tu.id,
                "content":     resultado,
            })

        # Acrescenta resposta do assistente e resultados das ferramentas
        msgs = list(kwargs["messages"])
        msgs.append({"role": "assistant", "content": resp.content})
        msgs.append({"role": "user",      "content": tool_results})
        kwargs["messages"] = msgs
    else:
        logger.warning("mcp_max_rounds_atingido", rodadas=_MAX_TOOL_ROUNDS)

    ms = round((time.monotonic() - inicio) * 1000, 2)
    logger.info(
        "call_model_with_tools_ok",
        model=model_type.value,
        ms=ms,
        tool_calls=tool_calls,
        input_tokens=total_input,
        output_tokens=total_output,
    )
    return texto_final, {
        "input_tokens":  total_input,
        "output_tokens": total_output,
        "tool_calls":    tool_calls,
    }
