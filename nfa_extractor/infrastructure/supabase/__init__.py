from nfa_extractor.infrastructure.supabase.categories import (
    create_category,
    delete_category,
    list_categories,
    seed_default_categories,
    update_category,
)
from nfa_extractor.infrastructure.supabase.client import get_supabase_client, is_supabase_enabled
from nfa_extractor.infrastructure.supabase.predictions import (
    create_prediction,
    delete_prediction,
    get_latest_prediction,
    list_predictions,
)
from nfa_extractor.infrastructure.supabase.profiles import get_profile, update_profile
from nfa_extractor.infrastructure.supabase.transactions import (
    create_transaction,
    delete_transaction,
    get_summary,
    list_transactions,
    update_transaction,
)

__all__ = [
    "get_supabase_client", "is_supabase_enabled",
    "get_profile", "update_profile",
    "list_categories", "create_category", "update_category", "delete_category", "seed_default_categories",
    "list_transactions", "create_transaction", "update_transaction", "delete_transaction", "get_summary",
    "list_predictions", "create_prediction", "get_latest_prediction", "delete_prediction",
]
