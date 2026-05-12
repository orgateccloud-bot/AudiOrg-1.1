"""
ORGATEC — Serviço de Previsões ML (Supabase).

CRUD para a tabela public.predictions.
Armazena resultados de modelos preditivos atrelados a tendências futuras.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from nfa_extractor.infrastructure.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)


# ── Schemas ──────────────────────────────────────────────────────────────────

class PredictionCreate(BaseModel):
    prediction_type: str = Field(..., pattern="^(cashflow|expense_trend|income_trend|anomaly)$")
    period_start: str  # ISO date
    period_end: str    # ISO date
    predicted_amount: float
    confidence_score: float = Field(..., ge=0, le=1)
    model_version: str
    input_summary: dict | None = None


class PredictionResponse(BaseModel):
    id: str
    user_id: str
    prediction_type: str
    period_start: str
    period_end: str
    predicted_amount: float
    confidence_score: float
    model_version: str
    input_summary: dict | None
    created_at: str
    updated_at: str


# ── Operações ────────────────────────────────────────────────────────────────

def list_predictions(
    user_id: str,
    prediction_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Lista previsões do usuário, mais recentes primeiro."""
    client = get_supabase_client()
    if not client:
        return []

    try:
        query = (
            client.table("predictions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if prediction_type:
            query = query.eq("prediction_type", prediction_type)

        res = query.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Erro ao listar previsões: {e}")
        return []


def create_prediction(user_id: str, data: PredictionCreate) -> dict | None:
    """Salva uma nova previsão gerada pelo modelo ML."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        payload = data.model_dump(exclude_none=True)
        payload["user_id"] = user_id

        res = client.table("predictions").insert(payload).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao criar previsão: {e}")
        return None


def get_latest_prediction(
    user_id: str,
    prediction_type: str,
) -> dict | None:
    """Busca a previsão mais recente de um tipo específico."""
    client = get_supabase_client()
    if not client:
        return None

    try:
        res = (
            client.table("predictions")
            .select("*")
            .eq("user_id", user_id)
            .eq("prediction_type", prediction_type)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar previsão: {e}")
        return None


def delete_prediction(prediction_id: str, user_id: str) -> bool:
    """Remove previsão."""
    client = get_supabase_client()
    if not client:
        return False

    try:
        client.table("predictions").delete().eq("id", prediction_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Erro ao remover previsão: {e}")
        return False
