"""
ORGATEC – Rotas Financeiras (Supabase).

Endpoints para categorias, transações, previsões e resumo financeiro.
Todas protegidas por JWT. RLS do Supabase garante isolamento por usuário.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth.security import TokenData, get_current_user
from nfa_extractor.infrastructure.supabase import categories as cat_svc
from nfa_extractor.infrastructure.supabase import predictions as pred_svc
from nfa_extractor.infrastructure.supabase import profiles as prof_svc
from nfa_extractor.infrastructure.supabase import transactions as tx_svc
from nfa_extractor.infrastructure.supabase.client import is_supabase_enabled

router = APIRouter(prefix="/finance", tags=["Financeiro"])


def _require_supabase():
    if not is_supabase_enabled():
        raise HTTPException(status_code=503, detail="Supabase não configurado.")


# ── Profile ──────────────────────────────────────────────────────────────────

@router.get("/profile")
def get_profile(user: TokenData = Depends(get_current_user)):
    _require_supabase()
    profile = prof_svc.get_profile(user.sub)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return profile


@router.put("/profile")
def update_profile(
    data: prof_svc.ProfileUpdate,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = prof_svc.update_profile(user.sub, data)
    if not result:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return result


# ── Categorias ───────────────────────────────────────────────────────────────

@router.get("/categories")
def listar_categorias(user: TokenData = Depends(get_current_user)):
    _require_supabase()
    return cat_svc.list_categories(user.sub)


@router.post("/categories", status_code=201)
def criar_categoria(
    data: cat_svc.CategoryCreate,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = cat_svc.create_category(user.sub, data)
    if not result:
        raise HTTPException(status_code=500, detail="Erro ao criar categoria.")
    return result


@router.put("/categories/{category_id}")
def atualizar_categoria(
    category_id: str,
    data: cat_svc.CategoryUpdate,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = cat_svc.update_category(category_id, user.sub, data)
    if not result:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return result


@router.delete("/categories/{category_id}", status_code=204)
def remover_categoria(
    category_id: str,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    if not cat_svc.delete_category(category_id, user.sub):
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")


@router.post("/categories/seed", status_code=201)
def seed_categorias(user: TokenData = Depends(get_current_user)):
    """Cria categorias padrão para o usuário (idempotente)."""
    _require_supabase()
    count = cat_svc.seed_default_categories(user.sub)
    return {"created": count}


# ── Transações ───────────────────────────────────────────────────────────────

@router.get("/transactions")
def listar_transacoes(
    user: TokenData = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    type: str | None = Query(None, pattern="^(income|expense)$"),
    category_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    _require_supabase()
    return tx_svc.list_transactions(
        user.sub, limit=limit, offset=offset,
        type_filter=type, category_id=category_id,
        date_from=date_from, date_to=date_to,
    )


@router.post("/transactions", status_code=201)
def criar_transacao(
    data: tx_svc.TransactionCreate,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = tx_svc.create_transaction(user.sub, data)
    if not result:
        raise HTTPException(status_code=500, detail="Erro ao criar transação.")
    return result


@router.put("/transactions/{tx_id}")
def atualizar_transacao(
    tx_id: str,
    data: tx_svc.TransactionUpdate,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = tx_svc.update_transaction(tx_id, user.sub, data)
    if not result:
        raise HTTPException(status_code=404, detail="Transação não encontrada.")
    return result


@router.delete("/transactions/{tx_id}", status_code=204)
def remover_transacao(
    tx_id: str,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    if not tx_svc.delete_transaction(tx_id, user.sub):
        raise HTTPException(status_code=404, detail="Transação não encontrada.")


@router.get("/summary")
def resumo_financeiro(
    user: TokenData = Depends(get_current_user),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Retorna resumo: receitas, despesas, saldo e total de transações."""
    _require_supabase()
    return tx_svc.get_summary(user.sub, date_from=date_from, date_to=date_to)


# ── Previsões ────────────────────────────────────────────────────────────────

@router.get("/predictions")
def listar_previsoes(
    user: TokenData = Depends(get_current_user),
    prediction_type: str | None = Query(None, pattern="^(cashflow|expense_trend|income_trend|anomaly)$"),
    limit: int = Query(20, ge=1, le=100),
):
    _require_supabase()
    return pred_svc.list_predictions(user.sub, prediction_type=prediction_type, limit=limit)


@router.post("/predictions", status_code=201)
def criar_previsao(
    data: pred_svc.PredictionCreate,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = pred_svc.create_prediction(user.sub, data)
    if not result:
        raise HTTPException(status_code=500, detail="Erro ao criar previsão.")
    return result


@router.get("/predictions/latest/{prediction_type}")
def ultima_previsao(
    prediction_type: str,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    result = pred_svc.get_latest_prediction(user.sub, prediction_type)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhuma previsão encontrada.")
    return result


@router.delete("/predictions/{prediction_id}", status_code=204)
def remover_previsao(
    prediction_id: str,
    user: TokenData = Depends(get_current_user),
):
    _require_supabase()
    if not pred_svc.delete_prediction(prediction_id, user.sub):
        raise HTTPException(status_code=404, detail="Previsão não encontrada.")
