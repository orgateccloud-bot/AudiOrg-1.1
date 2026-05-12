"""
ORGATEC — Serviço de Perfis de Usuário (Supabase).

CRUD para a tabela public.profiles (extensão de auth.users).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel

from nfa_extractor.infrastructure.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    id: str  # UUID do auth.users
    display_name: str | None = None
    avatar_url: str | None = None
    currency: str = "BRL"


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    currency: str | None = None


class ProfileResponse(BaseModel):
    id: str
    display_name: str | None
    avatar_url: str | None
    currency: str
    created_at: str
    updated_at: str


# ── Operações ────────────────────────────────────────────────────────────────

def get_profile(user_id: str) -> dict | None:
    """Busca perfil pelo ID do usuário."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        res = client.table("profiles").select("*").eq("id", user_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar profile {user_id}: {e}")
        return None


def update_profile(user_id: str, data: ProfileUpdate) -> dict | None:
    """Atualiza perfil do usuário."""
    client = get_supabase_client()
    if not client:
        return None

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return get_profile(user_id)

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        res = client.table("profiles").update(update_data).eq("id", user_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao atualizar profile {user_id}: {e}")
        return None
