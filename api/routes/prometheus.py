"""api.routes.prometheus
Endpoint /metrics — exporta metricas Prometheus do OrgAudi (Issue #25).

Exporta as 4 metricas principais:
1. orgaudi_laudos_total — contador de laudos gerados (laudos/h via rate())
2. orgaudi_auditoria_duration_seconds — histograma de latencia (p95 via histogram_quantile)
3. orgaudi_agente_erros_total{agente="s5"} — erros de agente S5 (erros S5)
4. orgaudi_custo_tokens_reais_dia — gauge de custo estimado de tokens por dia

Alvo Issue #25: /metrics retorna texto Prometheus; Sentry recebe erros nao tratados.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Response

logger = logging.getLogger("orgaudi.prometheus")

router = APIRouter(prefix="/metrics", tags=["observability"])

# Custo estimado por 1000 tokens (USD convertido para BRL)
_CUSTO_POR_1K_TOKENS_BRL = float(os.getenv("CUSTO_TOKEN_BRL_POR_1K", "0.05"))

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, CONTENT_TYPE_LATEST, generate_latest
    )
    from horizon_blue_one.core.metrics import (
        MODEL_TOKENS_IN, MODEL_TOKENS_OUT, MODEL_LATENCY,
        LEDGER_INSERTS, LEDGER_FALLBACKS, ROUTER_DECISIONS,
        PDF_BUILDS, PDF_BUILD_LATENCY, PROMETHEUS_DISPONIVEL
    )

    # Metrica 1: Laudos gerados total (rate() = laudos/h no Grafana)
    LAUDOS_TOTAL = Counter(
        "orgaudi_laudos_total",
        "Total de laudos de auditoria NFA-e gerados com sucesso.",
        labelnames=("cliente_id", "nivel_risco"),
    )

    # Metrica 2: Latencia de auditoria completa (histogram_quantile(0.95,...) = p95)
    AUDITORIA_DURATION = Histogram(
        "orgaudi_auditoria_duration_seconds",
        "Duracao total do pipeline de auditoria NFA-e (RE-1 -> XGBoost -> F1-F6 -> A-07 -> A-08).",
        labelnames=("nivel_risco",),
        buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
    )

    # Metrica 3: Erros por agente (counter de erros S5 / A-08)
    AGENTE_ERROS_TOTAL = Counter(
        "orgaudi_agente_erros_total",
        "Total de erros por agente do pipeline.",
        labelnames=("agente", "tipo_erro"),
    )

    # Metrica 4: Custo estimado de tokens por dia (gauge atualizado pelo token_router)
    CUSTO_TOKENS_DIA_REAIS = Gauge(
        "orgaudi_custo_tokens_reais_dia",
        "Custo estimado de tokens Claude consumidos hoje (BRL).",
    )

    # Gauge de uptime
    _START_TIME = time.time()
    UPTIME_SECONDS = Gauge(
        "orgaudi_uptime_seconds_total",
        "Tempo de atividade da instancia OrgAudi em segundos.",
    )

    _PROMETHEUS_ROUTES_OK = True

except ImportError:
    _PROMETHEUS_ROUTES_OK = False
    logger.warning("prometheus_client nao instalado: /metrics indisponivel")


if _PROMETHEUS_ROUTES_OK:
    @router.get("", response_class=Response, include_in_schema=False)
    async def get_metrics() -> Response:
        """Exporta metricas no formato texto Prometheus.

        Compativel com prometheus_client>=0.20 e Prometheus Server >=2.x.
        Endpoint: GET /metrics
        Content-Type: text/plain; version=0.0.4; charset=utf-8
        """
        # Atualizar gauge de uptime antes de exportar
        UPTIME_SECONDS.set(time.time() - _START_TIME)

        # Atualizar custo de tokens a partir do banco (best-effort)
        try:
            _atualizar_custo_tokens()
        except Exception as exc:
            logger.debug("custo_tokens_nao_atualizado", erro=str(exc))

        content = generate_latest()
        return Response(
            content=content,
            media_type=CONTENT_TYPE_LATEST,
        )

    def _atualizar_custo_tokens() -> None:
        """Consulta claude_stats e atualiza o gauge de custo do dia."""
        try:
            from nfa_extractor.infrastructure.database_v2 import SessionLocal
            from sqlalchemy import text
            from datetime import date

            db = SessionLocal()
            try:
                hoje = date.today().isoformat()
                resultado = db.execute(
                    text(
                        "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) "
                        "FROM claude_stats WHERE DATE(created_at) = :hoje"
                    ),
                    {"hoje": hoje},
                ).scalar()
                tokens_hoje = int(resultado or 0)
                custo_brl = (tokens_hoje / 1000) * _CUSTO_POR_1K_TOKENS_BRL
                CUSTO_TOKENS_DIA_REAIS.set(custo_brl)
            finally:
                db.close()
        except Exception:
            pass  # Gauge mantem valor anterior se DB indisponivel


def registrar_laudo(cliente_id: str = "anonimo", nivel_risco: str = "DESCONHECIDO") -> None:
    """Incrementa o contador de laudos gerados.

    Wrapper seguro para uso nos servicos de auditoria.
    """
    if not _PROMETHEUS_ROUTES_OK:
        return
    try:
        LAUDOS_TOTAL.labels(
            cliente_id=cliente_id[:8],  # Nao expor ID completo em labels
            nivel_risco=nivel_risco,
        ).inc()
    except Exception:
        pass


def registrar_erro_agente(agente: str, tipo_erro: str = "UNKNOWN") -> None:
    """Incrementa o contador de erros de agente.

    Args:
        agente: Identificador do agente (ex: "s5", "a07", "a08").
        tipo_erro: Tipo do erro (ex: "TIMEOUT", "LLM_INDISPONIVEL", "PARSE_ERROR").
    """
    if not _PROMETHEUS_ROUTES_OK:
        return
    try:
        AGENTE_ERROS_TOTAL.labels(agente=agente, tipo_erro=tipo_erro).inc()
    except Exception:
        pass


__all__ = [
    "router",
    "registrar_laudo",
    "registrar_erro_agente",
    "_PROMETHEUS_ROUTES_OK",
]
