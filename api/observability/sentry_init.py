"""Bootstrap do Sentry SDK (#25).

Init idempotente: chamado no startup do FastAPI via lifespan. Sem `SENTRY_DSN`
no ambiente, o init é no-op (modo dev/teste). Em produção (`ENVIRONMENT=production`)
ausência do DSN gera log de warning — observabilidade é responsabilidade do
operador, não silenciar é parte do contrato.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("orgaudi.sentry")

# Flag interno para garantir init único entre testes/reloads de uvicorn.
_INICIALIZADO = False


def init_sentry() -> bool:
    """Inicializa o Sentry SDK quando `SENTRY_DSN` está disponível.

    Retorna `True` se o SDK foi inicializado nesta chamada, `False` se foi
    pulado (sem DSN, já inicializado, ou módulo `sentry_sdk` ausente).
    Segura para chamar várias vezes — controlada por flag em módulo.
    """
    global _INICIALIZADO
    if _INICIALIZADO:
        return False

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    ambiente = os.environ.get("ENVIRONMENT", "development").lower()

    if not dsn:
        if ambiente == "production":
            logger.warning(
                "sentry.sem_dsn_em_producao "
                "— defina SENTRY_DSN para habilitar captura de erros"
            )
        else:
            logger.info("sentry.desabilitado ambiente=%s", ambiente)
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError as exc:
        logger.warning("sentry.sdk_indisponivel erro=%s", exc)
        return False

    try:
        traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    except ValueError:
        traces_sample_rate = 0.1

    sentry_sdk.init(
        dsn=dsn,
        environment=ambiente,
        release=os.environ.get("APP_VERSION", "8.0.0"),
        traces_sample_rate=max(0.0, min(traces_sample_rate, 1.0)),
        send_default_pii=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
    )
    _INICIALIZADO = True
    logger.info("sentry.iniciado ambiente=%s traces=%.2f", ambiente, traces_sample_rate)
    return True


def reset_sentry_state_for_tests() -> None:
    """Reseta o flag idempotente. Uso restrito a fixtures."""
    global _INICIALIZADO
    _INICIALIZADO = False
