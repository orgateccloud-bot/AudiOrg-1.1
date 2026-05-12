"""Testes das rotas /finance — cobrem todos os endpoints com Supabase mockado."""
import os
from unittest.mock import patch

os.environ["JWT_SECRET_KEY"] = "a" * 64

import pytest
from fastapi.testclient import TestClient

from api.auth.security import create_access_token
from api.main import app

client = TestClient(app)


def _hdr() -> dict:
    token = create_access_token({"sub": "u-1", "email": "u@t.com", "role": "user"})
    return {"Authorization": f"Bearer {token}"}


# ── _require_supabase: 503 quando Supabase desabilitado ──────────────────────

class TestSupabaseDesabilitado:
    """is_supabase_enabled = False → todos retornam 503."""

    def test_get_profile_503(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=False):
            res = client.get("/finance/profile", headers=_hdr())
        assert res.status_code == 503

    def test_listar_categorias_503(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=False):
            res = client.get("/finance/categories", headers=_hdr())
        assert res.status_code == 503

    def test_listar_transacoes_503(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=False):
            res = client.get("/finance/transactions", headers=_hdr())
        assert res.status_code == 503

    def test_summary_503(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=False):
            res = client.get("/finance/summary", headers=_hdr())
        assert res.status_code == 503

    def test_listar_previsoes_503(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=False):
            res = client.get("/finance/predictions", headers=_hdr())
        assert res.status_code == 503


# ── Profile ──────────────────────────────────────────────────────────────────

class TestProfile:
    def test_get_profile_404_quando_nao_existe(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.prof_svc.get_profile", return_value=None):
            res = client.get("/finance/profile", headers=_hdr())
        assert res.status_code == 404

    def test_get_profile_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.prof_svc.get_profile",
                   return_value={"id": "p1", "name": "X"}):
            res = client.get("/finance/profile", headers=_hdr())
        assert res.status_code == 200
        assert res.json()["id"] == "p1"

    def test_update_profile_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.prof_svc.update_profile", return_value=None):
            res = client.put("/finance/profile", json={}, headers=_hdr())
        assert res.status_code == 404

    def test_update_profile_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.prof_svc.update_profile",
                   return_value={"id": "p1", "name": "Novo"}):
            res = client.put("/finance/profile", json={"name": "Novo"}, headers=_hdr())
        assert res.status_code == 200


# ── Categorias ───────────────────────────────────────────────────────────────

class TestCategorias:
    def test_listar_retorna_lista(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.list_categories",
                   return_value=[{"id": "c1", "name": "Comida"}]):
            res = client.get("/finance/categories", headers=_hdr())
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_criar_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.create_category",
                   return_value={"id": "c-novo"}):
            res = client.post(
                "/finance/categories",
                json={"name": "Lazer", "type": "expense"},
                headers=_hdr(),
            )
        assert res.status_code == 201

    def test_criar_falha_retorna_500(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.create_category", return_value=None):
            res = client.post(
                "/finance/categories",
                json={"name": "X", "type": "expense"},
                headers=_hdr(),
            )
        assert res.status_code == 500

    def test_atualizar_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.update_category", return_value=None):
            res = client.put(
                "/finance/categories/c1",
                json={"name": "Novo"},
                headers=_hdr(),
            )
        assert res.status_code == 404

    def test_atualizar_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.update_category",
                   return_value={"id": "c1"}):
            res = client.put(
                "/finance/categories/c1",
                json={"name": "X"},
                headers=_hdr(),
            )
        assert res.status_code == 200

    def test_remover_204(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.delete_category", return_value=True):
            res = client.delete("/finance/categories/c1", headers=_hdr())
        assert res.status_code == 204

    def test_remover_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.delete_category", return_value=False):
            res = client.delete("/finance/categories/c1", headers=_hdr())
        assert res.status_code == 404

    def test_seed_default(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.cat_svc.seed_default_categories", return_value=8):
            res = client.post("/finance/categories/seed", headers=_hdr())
        assert res.status_code == 201
        assert res.json()["created"] == 8


# ── Transações ───────────────────────────────────────────────────────────────

class TestTransacoes:
    def test_listar_repassa_filtros(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.list_transactions",
                   return_value=[]) as mock:
            res = client.get(
                "/finance/transactions?limit=10&offset=5&type=income",
                headers=_hdr(),
            )
        assert res.status_code == 200
        # Confirma filtros propagados
        kwargs = mock.call_args.kwargs
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5
        assert kwargs["type_filter"] == "income"

    def test_criar_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.create_transaction",
                   return_value={"id": "tx-1"}):
            res = client.post(
                "/finance/transactions",
                json={"amount": 100, "type": "expense", "description": "x"},
                headers=_hdr(),
            )
        assert res.status_code == 201

    def test_criar_falha_500(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.create_transaction", return_value=None):
            res = client.post(
                "/finance/transactions",
                json={"amount": 100, "type": "expense", "description": "x"},
                headers=_hdr(),
            )
        assert res.status_code == 500

    def test_atualizar_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.update_transaction", return_value=None):
            res = client.put(
                "/finance/transactions/tx-1",
                json={"amount": 50}, headers=_hdr(),
            )
        assert res.status_code == 404

    def test_atualizar_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.update_transaction",
                   return_value={"id": "tx-1"}):
            res = client.put(
                "/finance/transactions/tx-1",
                json={"amount": 50}, headers=_hdr(),
            )
        assert res.status_code == 200

    def test_remover_204(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.delete_transaction", return_value=True):
            res = client.delete("/finance/transactions/tx-1", headers=_hdr())
        assert res.status_code == 204

    def test_remover_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.delete_transaction", return_value=False):
            res = client.delete("/finance/transactions/tx-1", headers=_hdr())
        assert res.status_code == 404

    def test_summary_retorna_estrutura(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.tx_svc.get_summary",
                   return_value={"income": 1000, "expense": 400, "balance": 600}):
            res = client.get("/finance/summary?date_from=2025-01-01", headers=_hdr())
        assert res.status_code == 200
        assert res.json()["balance"] == 600


# ── Previsões ────────────────────────────────────────────────────────────────

class TestPrevisoes:
    def test_listar_sem_filtro(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.list_predictions",
                   return_value=[]):
            res = client.get("/finance/predictions", headers=_hdr())
        assert res.status_code == 200

    def test_listar_com_filtro_tipo(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.list_predictions",
                   return_value=[{"id": "p1"}]) as mock:
            res = client.get(
                "/finance/predictions?prediction_type=cashflow&limit=5",
                headers=_hdr(),
            )
        assert res.status_code == 200
        assert mock.call_args.kwargs["prediction_type"] == "cashflow"

    def _payload_pred(self):
        return {
            "prediction_type": "cashflow",
            "period_start": "2025-01-01",
            "period_end": "2025-01-31",
            "predicted_amount": 1000.0,
            "confidence_score": 0.8,
            "model_version": "v1",
        }

    def test_criar_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.create_prediction",
                   return_value={"id": "p1"}):
            res = client.post(
                "/finance/predictions",
                json=self._payload_pred(),
                headers=_hdr(),
            )
        assert res.status_code == 201

    def test_criar_falha_500(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.create_prediction",
                   return_value=None):
            res = client.post(
                "/finance/predictions",
                json=self._payload_pred(),
                headers=_hdr(),
            )
        assert res.status_code == 500

    def test_ultima_previsao_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.get_latest_prediction",
                   return_value=None):
            res = client.get("/finance/predictions/latest/cashflow", headers=_hdr())
        assert res.status_code == 404

    def test_ultima_previsao_sucesso(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.get_latest_prediction",
                   return_value={"id": "p1", "data": {}}):
            res = client.get("/finance/predictions/latest/cashflow", headers=_hdr())
        assert res.status_code == 200

    def test_remover_204(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.delete_prediction", return_value=True):
            res = client.delete("/finance/predictions/p1", headers=_hdr())
        assert res.status_code == 204

    def test_remover_404(self):
        with patch("api.routes.finance.is_supabase_enabled", return_value=True), \
             patch("api.routes.finance.pred_svc.delete_prediction", return_value=False):
            res = client.delete("/finance/predictions/p1", headers=_hdr())
        assert res.status_code == 404
