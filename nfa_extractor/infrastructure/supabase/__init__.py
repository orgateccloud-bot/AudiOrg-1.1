from nfa_extractor.infrastructure.supabase.client import get_supabase_client, is_supabase_enabled
from nfa_extractor.infrastructure.supabase.profiles import get_profile, update_profile
from nfa_extractor.infrastructure.supabase.categories import (
    list_categories, create_category, update_category, delete_category, seed_default_categories,
)
from nfa_extractor.infrastructure.supabase.transactions import (
    list_transactions, create_transaction, update_transaction, delete_transaction, get_summary,
)
from nfa_extractor.infrastructure.supabase.predictions import (
    list_predictions, create_prediction, get_latest_prediction, delete_prediction,
)

__all__ = [
    "get_supabase_client", "is_supabase_enabled",
    "get_profile", "update_profile",
    "list_categories", "create_category", "update_category", "delete_category", "seed_default_categories",
    "list_transactions", "create_transaction", "update_transaction", "delete_transaction", "get_summary",
    "list_predictions", "create_prediction", "get_latest_prediction", "delete_prediction",
]
