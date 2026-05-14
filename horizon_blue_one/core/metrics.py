"""Métricas Prometheus para OrgAudi Sovereign.

Exporta contadores e histogramas para observabilidade do model_adapter,
ledger e roteador de tokens. Funciona como módulo opcional: se
prometheus_client não estiver instalado, todos os símbolos viram no-ops
para não quebrar o resto do sistema.

Uso típico:

    from horizon_blue_one.core.metrics import MODEL_TOKENS_IN
    MODEL_TOKENS_IN.labels(model="sonnet").inc(usage.input_tokens)

Exposição HTTP (FastAPI):

    from prometheus_client import make_asgi_app
    app.mount("/metrics", make_asgi_app())
"""
from __future__ import annotations

try:
    from prometheus_client import Counter, Histogram

    # ── LLM ────────────────────────────────────────────────────────────────────
    MODEL_TOKENS_IN = Counter(
        "orgaudi_model_tokens_in_total",
        "Total de tokens de entrada consumidos pelo modelo Claude.",
        labelnames=("model",),
    )
    MODEL_TOKENS_OUT = Counter(
        "orgaudi_model_tokens_out_total",
        "Total de tokens de saída gerados pelo modelo Claude.",
        labelnames=("model",),
    )
    MODEL_LATENCY = Histogram(
        "orgaudi_model_latency_seconds",
        "Latência (s) de chamadas ao modelo Claude.",
        labelnames=("model",),
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    )

    # ── Ledger ────────────────────────────────────────────────────────────────
    LEDGER_INSERTS = Counter(
        "orgaudi_ledger_inserts_total",
        "Total de eventos persistidos no ledger.",
        labelnames=("agent_id", "status"),
    )
    LEDGER_FALLBACKS = Counter(
        "orgaudi_ledger_fallbacks_total",
        "Total de eventos que caíram para o JSONL fallback (DB indisponível).",
        labelnames=("agent_id",),
    )

    # ── Token Router ──────────────────────────────────────────────────────────
    ROUTER_DECISIONS = Counter(
        "orgaudi_router_decisions_total",
        "Decisões do token_router por modelo selecionado e tipo de tarefa.",
        labelnames=("modelo", "tipo_tarefa", "downgrade"),
    )

    # ── PDF Engine ────────────────────────────────────────────────────────────
    PDF_BUILDS = Counter(
        "orgaudi_pdf_builds_total",
        "Total de laudos PDF gerados pelo pdf_engine.",
        labelnames=("status",),
    )
    PDF_BUILD_LATENCY = Histogram(
        "orgaudi_pdf_build_latency_seconds",
        "Latência (s) de geração de PDF (HTML→PDF via Chrome headless).",
        buckets=(0.5, 1, 2, 5, 10, 20, 30, 60),
    )

    PROMETHEUS_DISPONIVEL = True
except ImportError:  # pragma: no cover — prometheus_client não instalado
    PROMETHEUS_DISPONIVEL = False

    class _NoopMetric:
        """Stub que aceita qualquer atributo/método e retorna self."""

        def __init__(self, *args, **kwargs) -> None:
            pass

        def labels(self, *args, **kwargs) -> "_NoopMetric":
            return self

        def inc(self, *args, **kwargs) -> None:
            pass

        def observe(self, *args, **kwargs) -> None:
            pass

    MODEL_TOKENS_IN = _NoopMetric()
    MODEL_TOKENS_OUT = _NoopMetric()
    MODEL_LATENCY = _NoopMetric()
    LEDGER_INSERTS = _NoopMetric()
    LEDGER_FALLBACKS = _NoopMetric()
    ROUTER_DECISIONS = _NoopMetric()
    PDF_BUILDS = _NoopMetric()
    PDF_BUILD_LATENCY = _NoopMetric()


__all__ = [
    "MODEL_TOKENS_IN",
    "MODEL_TOKENS_OUT",
    "MODEL_LATENCY",
    "LEDGER_INSERTS",
    "LEDGER_FALLBACKS",
    "ROUTER_DECISIONS",
    "PDF_BUILDS",
    "PDF_BUILD_LATENCY",
    "PROMETHEUS_DISPONIVEL",
]
