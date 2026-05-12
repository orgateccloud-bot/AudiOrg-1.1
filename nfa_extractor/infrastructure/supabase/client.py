"""
ORGATEC — Cliente Supabase.

Wrapper centralizado para conexão com Supabase (Orgatec-data).
Gerencia autenticação e fornece acesso tipado às tabelas financeiras.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from supabase import Client, create_client

logger = logging.getLogger(__name__)


def _get_env(key: str) -> str:
    """Lê variável de ambiente obrigatória."""
    val = os.getenv(key, "")
    if not val:
        logger.warning(f"Variável {key} não configurada. Supabase desabilitado.")
    return val


@lru_cache(maxsize=1)
def get_supabase_client() -> Client | None:
    """Retorna cliente Supabase singleton. None se não configurado."""
    url = _get_env("SUPABASE_URL")
    key = _get_env("SUPABASE_SERVICE_KEY")

    if not url or not key:
        return None

    try:
        client = create_client(url, key)
        logger.info(f"Supabase conectado: {url}")
        return client
    except Exception as e:
        logger.error(f"Erro ao conectar Supabase: {e}")
        return None


def is_supabase_enabled() -> bool:
    """Verifica se Supabase está configurado e acessível."""
    return get_supabase_client() is not None
