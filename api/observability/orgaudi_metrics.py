"""Métricas Prometheus OrgAudi-específicas (#25).

Estende as métricas HTTP/Claude já registradas em
`api/middleware/prometheus.py` e `api/middleware/claude_metrics.py` com:

- `orgaudi_laudos_total{status}` — counter de laudos emitidos por desfecho
- `orgaudi_errors_s5_total{component}` — counter de erros 5xx por componente
  (primeiro segmento da rota: `auditoria`, `auth`, `clientes`, etc.)
- `orgaudi_claude_cost_usd_total{model}` — alias do counter de custo Claude,
  exposto no namespace `orgaudi_*` para uniformidade do dashboard.

O middleware Prometheus (`api/middleware/prometheus.py`) ganha um hook que
chama `registrar_erro_s5` quando o status code é 5xx; rotas que emitem
laudo chamam `registrar_laudo` diretamente. Custo Claude já é publicado
pelo listener em `api/middleware/claude_metrics.py`; aqui apenas duplicamos
no namespace `orgaudi_*` quando o counter remoto avança.
"""
from __future__ import annotations

from prometheus_client import Counter

from api.middleware.claude_metrics import (
    _CUSTO_INPUT_USD_PER_MTOK,
    _CUSTO_OUTPUT_USD_PER_MTOK,
)
from horizon_blue_one.core.model_adapter import ModelType
from horizon_blue_one.core.token_router import (
    RotingDecision,
    adicionar_listener,
)

# ── Counters ─────────────────────────────────────────────────────────────────

ORGAUDI_LAUDOS_TOTAL = Counter(
    "orgaudi_laudos_total",
    "Total de laudos emitidos pelo motor OrgAudi, segmentado por status.",
    ["status"],  # sucesso | falha
)

ORGAUDI_ERRORS_S5_TOTAL = Counter(
    "orgaudi_errors_s5_total",
    "Total de respostas HTTP 5xx, segmentado pelo componente da rota.",
    ["component"],  # auditoria | auth | clientes | agente | finance | outros
)

ORGAUDI_CLAUDE_COST_USD_TOTAL = Counter(
    "orgaudi_claude_cost_usd_total",
    "Custo acumulado em USD do Claude (alias namespaceado de claude_cost_usd_total).",
    ["model"],
)


# ── Helpers de registro ──────────────────────────────────────────────────────

_COMPONENTES_CONHECIDOS = frozenset({
    "auditoria", "auth", "clientes", "agente", "finance",
    "metrics", "nfae", "ping", "tokens", "stats",
})


def _extrair_componente(path: str) -> str:
    """Mapeia a rota para um rótulo de componente estável e de baixa cardinalidade."""
    if not path or path == "/":
        return "raiz"
    primeiro = path.lstrip("/").split("/", 1)[0]
    if not primeiro:
        return "raiz"
    return primeiro if primeiro in _COMPONENTES_CONHECIDOS else "outros"


def registrar_laudo(status: str = "sucesso") -> None:
    """Incrementa o counter de laudos emitidos. `status` ∈ {"sucesso", "falha"}."""
    if status not in ("sucesso", "falha"):
        status = "falha"
    ORGAUDI_LAUDOS_TOTAL.labels(status=status).inc()


def registrar_erro_s5(path: str) -> None:
    """Incrementa o counter de erros 5xx para o componente derivado da rota."""
    ORGAUDI_ERRORS_S5_TOTAL.labels(component=_extrair_componente(path)).inc()


def _espelhar_custo_claude(
    modelo: ModelType,
    tokens_in: int,
    tokens_out: int,
    decision: RotingDecision,
    max_tokens: int | None,
    agent_id: str | None,
) -> None:
    """Listener paralelo ao de `claude_metrics`: espelha o custo no counter
    namespaceado `orgaudi_claude_cost_usd_total{model}`."""
    del decision, max_tokens, agent_id  # contrato do listener, não usado aqui
    custo = (
        tokens_in  * _CUSTO_INPUT_USD_PER_MTOK.get(modelo,  0.0) +
        tokens_out * _CUSTO_OUTPUT_USD_PER_MTOK.get(modelo, 0.0)
    ) / 1_000_000
    if custo > 0:
        ORGAUDI_CLAUDE_COST_USD_TOTAL.labels(model=modelo.value).inc(custo)


# Registro automático no import — `api/main.py` deve importar este módulo.
adicionar_listener(_espelhar_custo_claude)
