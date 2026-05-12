"""Claude Message Batches — helper para workloads noturnos (-50% custo).

Envolve a Anthropic Message Batches API para casos onde latência síncrona não é
necessária (relatórios noturnos, reprocessamento histórico, calibração de
benchmarks). O custo de input e output cai 50% versus chamadas síncronas.

Fluxo típico:
    >>> reqs = [BatchRequest(custom_id="audit-001", model="haiku",
    ...                      system="...", prompt="...", max_tokens=512)]
    >>> batch_id = submit_batch(reqs)            # devolve imediatamente
    >>> while batch_status(batch_id) != "ended":
    ...     time.sleep(60)
    >>> for r in batch_results(batch_id):        # itera com custom_id e texto
    ...     processar(r.custom_id, r.text)

Modelos suportados: HAIKU, SONNET, OPUS — o adapter resolve o model_id final
via `horizon_blue_one.core.config.settings`.

Limitações deliberadas:
- Sem retry/backoff: o batch já é assíncrono (≤24h SLA da Anthropic).
- Sem persistência do batch_id: o caller é responsável por guardar.
- Sem prompt caching: o cache ephemeral não se beneficia em jobs assíncronos.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import anthropic

from horizon_blue_one.core.config import settings
from horizon_blue_one.core.model_adapter import ModelType


# ── Resolução de model_id ─────────────────────────────────────────────────────
def _resolve_model_id(model_type: ModelType) -> str:
    if model_type in (ModelType.CLAUDE, ModelType.SONNET):
        return settings.CLAUDE_MODEL_ID
    if model_type == ModelType.HAIKU:
        return settings.HAIKU_MODEL_ID
    if model_type == ModelType.OPUS:
        return settings.OPUS_MODEL_ID
    raise ValueError(f"Modelo não suportado em batch: {model_type}")


# ── Estruturas ────────────────────────────────────────────────────────────────
@dataclass
class BatchRequest:
    """Uma chamada que entra no lote noturno."""
    custom_id:  str                          # identificador devolvido nos resultados
    model:      ModelType                    # HAIKU / SONNET / OPUS
    prompt:     str                          # conteúdo do user message
    system:     str = ""                     # system prompt opcional
    max_tokens: int = 1024
    metadata:   dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        msgs = [{"role": "user", "content": self.prompt}]
        params: dict[str, Any] = {
            "model":      _resolve_model_id(self.model),
            "max_tokens": self.max_tokens,
            "messages":   msgs,
        }
        if self.system:
            params["system"] = self.system
        return {"custom_id": self.custom_id, "params": params}


@dataclass
class BatchResult:
    """Resultado individual decodificado de um batch."""
    custom_id: str
    text:      str                 # texto da resposta (vazio se erro/expired)
    status:    str                 # succeeded | errored | canceled | expired
    error:     str | None = None
    input_tokens:  int = 0
    output_tokens: int = 0


# ── Cliente lazy (separado do model_adapter para evitar acoplamento) ─────────
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ── API pública ───────────────────────────────────────────────────────────────
def submit_batch(requests: list[BatchRequest], client: Any | None = None) -> str:
    """Cria um Message Batch na Anthropic e retorna o id.

    `client` é injetável (para testes); o default usa o cliente lazy.
    """
    if not requests:
        raise ValueError("submit_batch requer ao menos 1 BatchRequest.")
    cli = client or _get_client()
    payloads = [r.to_payload() for r in requests]
    # SDK tipa `requests` como TypedDict; construímos a shape em runtime.
    batch = cli.messages.batches.create(requests=payloads)  # type: ignore[arg-type]
    return batch.id


def batch_status(batch_id: str, client: Any | None = None) -> str:
    """Retorna `processing_status` (in_progress | ended | canceling | canceled)."""
    cli = client or _get_client()
    batch = cli.messages.batches.retrieve(batch_id)
    return batch.processing_status


def batch_results(batch_id: str, client: Any | None = None) -> Iterator[BatchResult]:
    """Itera resultados de um batch finalizado.

    Yields BatchResult preservando custom_id e status individual. Não levanta
    quando uma chamada falha — emite `status="errored"` para o caller decidir.
    """
    cli = client or _get_client()
    for raw in cli.messages.batches.results(batch_id):
        yield _decodificar(raw)


def estimar_economia_usd(requests: list[BatchRequest]) -> float:
    """Estima a economia em USD vs chamadas síncronas (50% off no input+output).

    Heurística: ~4 chars/token para input (sys+prompt) e usa `max_tokens` como
    teto de output. Subestima ganho real (max_tokens raramente é atingido).
    """
    from horizon_blue_one.core.token_router import _CUSTO_INPUT, _CUSTO_OUTPUT

    total = 0.0
    for r in requests:
        t_in  = max(1, (len(r.prompt) + len(r.system)) // 4)
        t_out = r.max_tokens
        custo_sync = (
            t_in  * _CUSTO_INPUT.get(r.model,  0.0) +
            t_out * _CUSTO_OUTPUT.get(r.model, 0.0)
        ) / 1_000_000
        total += custo_sync * 0.5    # batch = 50% off
    return round(total, 6)


# ── Decodificação dos resultados do SDK ───────────────────────────────────────
def _decodificar(raw: Any) -> BatchResult:
    """Converte o objeto do SDK em BatchResult tipado e tolerante.

    O SDK retorna shape:
      raw.custom_id
      raw.result.type            ("succeeded" | "errored" | "canceled" | "expired")
      raw.result.message.content[0].text  (se succeeded)
      raw.result.message.usage   (input_tokens, output_tokens)
      raw.result.error.error.message (se errored)
    """
    custom_id = getattr(raw, "custom_id", "?")
    result    = getattr(raw, "result", None)
    tipo      = getattr(result, "type", "errored") if result else "errored"

    if tipo == "succeeded" and result is not None:
        msg = getattr(result, "message", None)
        text = ""
        t_in = t_out = 0
        if msg is not None:
            content = getattr(msg, "content", []) or []
            for blk in content:
                if getattr(blk, "type", None) == "text":
                    text += getattr(blk, "text", "")
            usage = getattr(msg, "usage", None)
            if usage is not None:
                t_in  = getattr(usage, "input_tokens",  0) or 0
                t_out = getattr(usage, "output_tokens", 0) or 0
        return BatchResult(
            custom_id=custom_id, text=text, status="succeeded",
            input_tokens=t_in, output_tokens=t_out,
        )

    erro = None
    if tipo == "errored" and result is not None:
        err_block = getattr(result, "error", None)
        if err_block is not None:
            inner = getattr(err_block, "error", err_block)
            erro = getattr(inner, "message", str(inner))
    return BatchResult(custom_id=custom_id, text="", status=tipo, error=erro)
