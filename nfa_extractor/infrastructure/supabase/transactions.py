"""
ORGATEC — Serviço de Transações Financeiras (Supabase).

CRUD + agregações para a tabela public.transactions.
Isolamento por user_id via RLS.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from nfa_extractor.infrastructure.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    category_id: str | None = None
    type: str = Field(..., pattern="^(income|expense)$")
    amount: float = Field(..., gt=0)
    description: str | None = None
    transaction_date: str | None = None  # ISO date, default: hoje


class TransactionUpdate(BaseModel):
    category_id: str | None = None
    type: str | None = Field(None, pattern="^(income|expense)$")
    amount: float | None = Field(None, gt=0)
    description: str | None = None
    transaction_date: str | None = None


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    category_id: str | None
    type: str
    amount: float
    description: str | None
    transaction_date: str
    created_at: str
    updated_at: str


class TransactionSummary(BaseModel):
    total_income: float
    total_expense: float
    balance: float
    transaction_count: int


# ── Operações ────────────────────────────────────────────────────────────────

def list_transactions(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    type_filter: str | None = None,
    category_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Lista transações com filtros opcionais."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = (
            client.table("transactions")
            .select("*, categories(name, icon, color)")
            .eq("user_id", user_id)
            .order("transaction_date", desc=True)
            .limit(limit)
            .offset(offset)
        )

        if type_filter:
            query = query.eq("type", type_filter)
        if category_id:
            query = query.eq("category_id", category_id)
        if date_from:
            query = query.gte("transaction_date", date_from)
        if date_to:
            query = query.lte("transaction_date", date_to)

        res = query.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Erro ao listar transações: {e}")
        return []


def create_transaction(user_id: str, data: TransactionCreate) -> dict | None:
    """Cria uma nova transação."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        payload = data.model_dump(exclude_none=True)
        payload["user_id"] = user_id
        if "transaction_date" not in payload:
            payload["transaction_date"] = date.today().isoformat()

        res = client.table("transactions").insert(payload).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao criar transação: {e}")
        return None


def update_transaction(tx_id: str, user_id: str, data: TransactionUpdate) -> dict | None:
    """Atualiza transação existente."""
    client = get_supabase_client()
    if not client:
        return None

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        return None

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        res = (
            client.table("transactions")
            .update(update_data)
            .eq("id", tx_id)
            .eq("user_id", user_id)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao atualizar transação: {e}")
        return None


def delete_transaction(tx_id: str, user_id: str) -> bool:
    """Remove transação."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table("transactions").delete().eq("id", tx_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Erro ao remover transação: {e}")
        return False


def get_summary(
    user_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> TransactionSummary:
    """Calcula resumo financeiro (receitas, despesas, saldo)."""
    client = get_supabase_client()
    if not client:
        return TransactionSummary(total_income=0, total_expense=0, balance=0, transaction_count=0)

    try:
        query = client.table("transactions").select("type, amount").eq("user_id", user_id)
        if date_from:
            query = query.gte("transaction_date", date_from)
        if date_to:
            query = query.lte("transaction_date", date_to)

        res = query.execute()
        rows = res.data or []

        total_income = sum(r["amount"] for r in rows if r["type"] == "income")
        total_expense = sum(r["amount"] for r in rows if r["type"] == "expense")

        return TransactionSummary(
            total_income=round(total_income, 2),
            total_expense=round(total_expense, 2),
            balance=round(total_income - total_expense, 2),
            transaction_count=len(rows),
        )
    except Exception as e:
        logger.error(f"Erro ao calcular resumo: {e}")
        return TransactionSummary(total_income=0, total_expense=0, balance=0, transaction_count=0)
