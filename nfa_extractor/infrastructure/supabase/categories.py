"""
ORGATEC — Serviço de Categorias (Supabase).

CRUD para a tabela public.categories.
Categorias são isoladas por user_id (RLS).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from nfa_extractor.infrastructure.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(income|expense)$")
    icon: str | None = None
    color: str | None = None
    is_default: bool = False


class CategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    color: str | None = None


class CategoryResponse(BaseModel):
    id: str
    user_id: str
    name: str
    type: str
    icon: str | None
    color: str | None
    is_default: bool
    created_at: str


# ── Seed de Categorias Padrão ────────────────────────────────────────────────

DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    {"name": "Salário", "type": "income", "icon": "💰", "color": "#22c55e", "is_default": True},
    {"name": "Freelance", "type": "income", "icon": "💼", "color": "#3b82f6", "is_default": True},
    {"name": "Investimentos", "type": "income", "icon": "📈", "color": "#8b5cf6", "is_default": True},
    {"name": "Outros (Receita)", "type": "income", "icon": "➕", "color": "#6b7280", "is_default": True},
    {"name": "Alimentação", "type": "expense", "icon": "🍔", "color": "#ef4444", "is_default": True},
    {"name": "Transporte", "type": "expense", "icon": "🚗", "color": "#f59e0b", "is_default": True},
    {"name": "Moradia", "type": "expense", "icon": "🏠", "color": "#ec4899", "is_default": True},
    {"name": "Saúde", "type": "expense", "icon": "🏥", "color": "#14b8a6", "is_default": True},
    {"name": "Educação", "type": "expense", "icon": "📚", "color": "#6366f1", "is_default": True},
    {"name": "Lazer", "type": "expense", "icon": "🎮", "color": "#f97316", "is_default": True},
    {"name": "Outros (Despesa)", "type": "expense", "icon": "➖", "color": "#6b7280", "is_default": True},
]


# ── Operações ────────────────────────────────────────────────────────────────

def list_categories(user_id: str) -> list[dict]:
    """Lista todas as categorias do usuário."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        res = client.table("categories").select("*").eq("user_id", user_id).order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Erro ao listar categorias: {e}")
        return []


def create_category(user_id: str, data: CategoryCreate) -> dict | None:
    """Cria uma nova categoria para o usuário."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        payload = data.model_dump()
        payload["user_id"] = user_id
        res = client.table("categories").insert(payload).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao criar categoria: {e}")
        return None


def update_category(category_id: str, user_id: str, data: CategoryUpdate) -> dict | None:
    """Atualiza categoria existente (RLS garante que user_id bate)."""
    client = get_supabase_client()
    if not client:
        return None

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return None

    try:
        res = (
            client.table("categories")
            .update(update_data)
            .eq("id", category_id)
            .eq("user_id", user_id)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao atualizar categoria: {e}")
        return None


def delete_category(category_id: str, user_id: str) -> bool:
    """Remove categoria (RLS garante isolamento)."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table("categories").delete().eq("id", category_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Erro ao remover categoria: {e}")
        return False


def seed_default_categories(user_id: str) -> int:
    """Cria categorias padrão para um novo usuário. Retorna quantidade criada."""
    client = get_supabase_client()
    if not client:
        return 0

    existing = list_categories(user_id)
    if existing:
        return 0  # Já tem categorias, não faz seed

    rows = [{"user_id": user_id, **cat} for cat in DEFAULT_CATEGORIES]
    try:
        res = client.table("categories").insert(rows).execute()
        count = len(res.data) if res.data else 0
        logger.info(f"Seed: {count} categorias criadas para {user_id}")
        return count
    except Exception as e:
        logger.error(f"Erro no seed de categorias: {e}")
        return 0
