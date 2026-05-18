"""api.middleware.sentry
Integracao Sentry SDK para OrgAudi (Issue #25).

Inicializa o Sentry no lifespan da aplicacao via SENTRY_DSN em .env.
Captura excecoes nao tratadas, performance traces e erros de agente.
Funciona como modulo opcional: se sentry_sdk nao estiver instalado ou
SENTRY_DSN estiver vazio, o sistema continua sem observabilidade Sentry.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("orgaudi.sentry")

SENTRY_DISPONIVEL = False


def init_sentry() -> bool:
    """Inicializa Sentry SDK com SENTRY_DSN do ambiente.

    Returns:
        True se inicializado com sucesso, False caso contrario.
    """
    global SENTRY_DISPONIVEL

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("sentry_desabilitado: SENTRY_DSN nao configurado")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        import structlog

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("ENVIRONMENT", "production"),
            release=os.getenv("APP_VERSION", "1.0.0"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,
                    event_level=logging.ERROR,
                ),
            ],
            # Nao enviar dados PII ao Sentry (LGPD)
            send_default_pii=False,
            # Filtrar eventos com dados sensiveis
            before_send=_before_send_filter,
        )
        SENTRY_DISPONIVEL = True
        logger.info("sentry_inicializado", dsn=dsn[:20] + "***")
        return True
    except ImportError:
        logger.warning("sentry_sdk_nao_instalado: adicione sentry-sdk ao requirements.txt")
        return False
    except Exception as exc:
        logger.error("sentry_init_falhou", erro=str(exc))
        return False


def _before_send_filter(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Filtro pre-envio: remove PII e dados sensiveis antes de enviar ao Sentry.

    Remove CPF, CNPJ, tokens @Delta e chaves de API de request bodies e
    stack traces para garantir conformidade LGPD Art. 37.
    """
    # Remover dados de request que possam conter PII
    if "request" in event:
        request = event["request"]
        # Remover body de requisicoes (pode conter CPF/CNPJ)
        if "data" in request:
            request["data"] = "[FILTRADO-LGPD]"
        # Remover headers com tokens
        headers = request.get("headers", {})
        for header_key in list(headers.keys()):
            if header_key.lower() in ("authorization", "x-api-key", "cookie"):
                headers[header_key] = "[FILTRADO]"

    # Remover variaveis locais de stack frames com nomes suspeitos
    PII_VARS = {"cpf", "cnpj", "password", "senha", "token", "api_key", "secret"}
    for exception in event.get("exception", {}).get("values", []):
        for frame in exception.get("stacktrace", {}).get("frames", []):
            local_vars = frame.get("vars", {})
            for var_name in list(local_vars.keys()):
                if any(pii in var_name.lower() for pii in PII_VARS):
                    local_vars[var_name] = "[FILTRADO-LGPD]"

    return event


def capturar_excecao(exc: Exception, contexto: dict[str, Any] | None = None) -> None:
    """Captura excecao no Sentry com contexto adicional.

    Wrapper seguro: nao lanca excecao se Sentry nao estiver disponivel.

    Args:
        exc: Excecao a capturar.
        contexto: Dict com dados extras (sem PII).
    """
    if not SENTRY_DISPONIVEL:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if contexto:
                for key, value in contexto.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass  # Sentry nao pode falhar a aplicacao principal


__all__ = ["init_sentry", "capturar_excecao", "SENTRY_DISPONIVEL"]
