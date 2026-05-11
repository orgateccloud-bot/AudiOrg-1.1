"""
Testes para a camada Supabase — todos com mocks (sem conexão real).
Testa schemas, lógica de serviço e tratamento de erros.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ["JWT_SECRET_KEY"] = "a" * 64

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nfa_extractor.infrastructure.supabase.categories import (
    DEFAULT_CATEGORIES,
    CategoryCreate,
    create_category,
    delete_category,
    list_categories,
    seed_default_categories,
)
from nfa_extractor.infrastructure.supabase.client import is_supabase_enabled
from nfa_extractor.infrastructure.supabase.predictions import (
    PredictionCreate,
    create_prediction,
    get_latest_prediction,
    list_predictions,
)
from nfa_extractor.infrastructure.supabase.profiles import (
    ProfileUpdate,
    get_profile,
    update_profile,
)
from nfa_extractor.infrastructure.supabase.transactions import (
    TransactionCreate,
    TransactionSummary,
    create_transaction,
    delete_transaction,
    get_summary,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_supabase():
    """Cria mock do cliente Supabase com cadeia de chamadas."""
    client = MagicMock()
    # Configurar cadeia fluente: client.table("x").select("*").eq(...).execute()
    return client


def _mock_response(data=None):
    """Cria mock de resposta do Supabase."""
    resp = MagicMock()
    resp.data = data or []
    return resp


# ── Testes: Schemas Pydantic ─────────────────────────────────────────────────

class TestSchemas:

    def test_category_create_valida(self):
        cat = CategoryCreate(name="Alimentação", type="expense")
        assert cat.name == "Alimentação"
        assert cat.type == "expense"

    def test_category_create_type_invalido(self):
        with pytest.raises(Exception):
            CategoryCreate(name="X", type="invalid")

    def test_transaction_create_valida(self):
        tx = TransactionCreate(type="income", amount=1500.0)
        assert tx.amount == 1500.0

    def test_transaction_create_valor_negativo(self):
        with pytest.raises(Exception):
            TransactionCreate(type="expense", amount=-100)

    def test_prediction_create_valida(self):
        pred = PredictionCreate(
            prediction_type="cashflow",
            period_start="2026-05-01",
            period_end="2026-05-31",
            predicted_amount=50000.0,
            confidence_score=0.87,
            model_version="v1.0",
        )
        assert pred.confidence_score == 0.87

    def test_prediction_score_fora_do_range(self):
        with pytest.raises(Exception):
            PredictionCreate(
                prediction_type="cashflow",
                period_start="2026-05-01",
                period_end="2026-05-31",
                predicted_amount=50000.0,
                confidence_score=1.5,  # > 1 -> inválido
                model_version="v1.0",
            )

    def test_transaction_summary(self):
        s = TransactionSummary(total_income=5000, total_expense=3000, balance=2000, transaction_count=10)
        assert s.balance == 2000

    def test_profile_update_parcial(self):
        p = ProfileUpdate(display_name="Veloso")
        assert p.display_name == "Veloso"
        assert p.currency is None


# ── Testes: Categories Service ───────────────────────────────────────────────

class TestCategories:

    @patch("nfa_extractor.infrastructure.supabase.categories.get_supabase_client")
    def test_list_categories(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            _mock_response([{"id": "1", "name": "Salário", "type": "income"}])
        )
        result = list_categories("user-123")
        assert len(result) == 1
        assert result[0]["name"] == "Salário"

    @patch("nfa_extractor.infrastructure.supabase.categories.get_supabase_client")
    def test_create_category(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.insert.return_value.execute.return_value = (
            _mock_response([{"id": "new-1", "name": "Transporte", "type": "expense"}])
        )
        result = create_category("user-123", CategoryCreate(name="Transporte", type="expense"))
        assert result is not None
        assert result["name"] == "Transporte"

    @patch("nfa_extractor.infrastructure.supabase.categories.get_supabase_client")
    def test_delete_category(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _mock_response()
        )
        assert delete_category("cat-1", "user-123") is True

    def test_list_categories_sem_supabase(self):
        with patch("nfa_extractor.infrastructure.supabase.categories.get_supabase_client", return_value=None):
            assert list_categories("user-123") == []

    @patch("nfa_extractor.infrastructure.supabase.categories.get_supabase_client")
    @patch("nfa_extractor.infrastructure.supabase.categories.list_categories")
    def test_seed_default_categories(self, mock_list, mock_client):
        mock_list.return_value = []  # Nenhuma existente
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.insert.return_value.execute.return_value = (
            _mock_response([{} for _ in DEFAULT_CATEGORIES])
        )
        count = seed_default_categories("user-123")
        assert count == len(DEFAULT_CATEGORIES)

    @patch("nfa_extractor.infrastructure.supabase.categories.get_supabase_client")
    @patch("nfa_extractor.infrastructure.supabase.categories.list_categories")
    def test_seed_skip_se_ja_tem(self, mock_list, mock_client):
        mock_list.return_value = [{"id": "1"}]  # Já tem categorias
        count = seed_default_categories("user-123")
        assert count == 0


# ── Testes: Transactions Service ─────────────────────────────────────────────

class TestTransactions:

    @patch("nfa_extractor.infrastructure.supabase.transactions.get_supabase_client")
    def test_create_transaction(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.insert.return_value.execute.return_value = (
            _mock_response([{"id": "tx-1", "amount": 1500.0, "type": "income"}])
        )
        result = create_transaction("user-123", TransactionCreate(type="income", amount=1500.0))
        assert result is not None
        assert result["amount"] == 1500.0

    @patch("nfa_extractor.infrastructure.supabase.transactions.get_supabase_client")
    def test_delete_transaction(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            _mock_response()
        )
        assert delete_transaction("tx-1", "user-123") is True

    def test_create_sem_supabase(self):
        with patch("nfa_extractor.infrastructure.supabase.transactions.get_supabase_client", return_value=None):
            assert create_transaction("user-123", TransactionCreate(type="expense", amount=100)) is None

    @patch("nfa_extractor.infrastructure.supabase.transactions.get_supabase_client")
    def test_get_summary(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = _mock_response([
            {"type": "income", "amount": 5000},
            {"type": "income", "amount": 3000},
            {"type": "expense", "amount": 2000},
        ])
        summary = get_summary("user-123")
        assert summary.total_income == 8000.0
        assert summary.total_expense == 2000.0
        assert summary.balance == 6000.0
        assert summary.transaction_count == 3

    def test_get_summary_sem_supabase(self):
        with patch("nfa_extractor.infrastructure.supabase.transactions.get_supabase_client", return_value=None):
            s = get_summary("user-123")
            assert s.balance == 0


# ── Testes: Predictions Service ──────────────────────────────────────────────

class TestPredictions:

    @patch("nfa_extractor.infrastructure.supabase.predictions.get_supabase_client")
    def test_create_prediction(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.insert.return_value.execute.return_value = _mock_response([{
            "id": "pred-1",
            "prediction_type": "cashflow",
            "predicted_amount": 50000.0,
            "confidence_score": 0.87,
        }])
        data = PredictionCreate(
            prediction_type="cashflow",
            period_start="2026-05-01",
            period_end="2026-05-31",
            predicted_amount=50000.0,
            confidence_score=0.87,
            model_version="v1.0",
        )
        result = create_prediction("user-123", data)
        assert result is not None
        assert result["confidence_score"] == 0.87

    @patch("nfa_extractor.infrastructure.supabase.predictions.get_supabase_client")
    def test_get_latest_prediction(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        chain = client.table.return_value.select.return_value.eq.return_value.eq.return_value
        chain.order.return_value.limit.return_value.execute.return_value = _mock_response([{
            "id": "pred-latest",
            "prediction_type": "expense_trend",
        }])
        result = get_latest_prediction("user-123", "expense_trend")
        assert result is not None
        assert result["prediction_type"] == "expense_trend"

    def test_list_predictions_sem_supabase(self):
        with patch("nfa_extractor.infrastructure.supabase.predictions.get_supabase_client", return_value=None):
            assert list_predictions("user-123") == []


# ── Testes: Profiles Service ─────────────────────────────────────────────────

class TestProfiles:

    @patch("nfa_extractor.infrastructure.supabase.profiles.get_supabase_client")
    def test_get_profile(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = _mock_response([{
            "id": "user-123",
            "display_name": "Veloso",
            "currency": "BRL",
        }])
        result = get_profile("user-123")
        assert result is not None
        assert result["display_name"] == "Veloso"

    @patch("nfa_extractor.infrastructure.supabase.profiles.get_supabase_client")
    def test_update_profile(self, mock_client):
        client = _mock_supabase()
        mock_client.return_value = client
        client.table.return_value.update.return_value.eq.return_value.execute.return_value = _mock_response([{
            "id": "user-123",
            "display_name": "Veloso Updated",
        }])
        result = update_profile("user-123", ProfileUpdate(display_name="Veloso Updated"))
        assert result["display_name"] == "Veloso Updated"

    def test_get_profile_sem_supabase(self):
        with patch("nfa_extractor.infrastructure.supabase.profiles.get_supabase_client", return_value=None):
            assert get_profile("user-123") is None


# ── Testes: Client ───────────────────────────────────────────────────────────

class TestClient:

    def test_supabase_desabilitado_sem_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("nfa_extractor.infrastructure.supabase.client.get_supabase_client") as mock:
                mock.return_value = None
                assert is_supabase_enabled() is False
