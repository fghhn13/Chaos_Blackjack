"""SQLite-backed game data: balance profiles, run saves and preferences.

Game logic never imports this package's database code directly; front-ends
load a `Balance` and build a `RunConfig` from it.
"""

from chaos_blackjack.data.balance import (
    Balance,
    BalanceError,
    ChaosRuleBalance,
    ShopItemBalance,
    active_profile,
    clone_profile,
    default_balance,
    load_balance,
)
from chaos_blackjack.data.db import connect, db_path
from chaos_blackjack.data.prefs import get_pref, set_pref
from chaos_blackjack.data.saves import SaveNotFound, delete_run, import_json_saves, list_runs, load_run, save_run

__all__ = [
    "Balance", "BalanceError", "ChaosRuleBalance", "ShopItemBalance", "active_profile", "clone_profile", "connect", "db_path",
    "default_balance", "delete_run", "get_pref", "import_json_saves", "list_runs", "load_balance",
    "load_run", "save_run", "set_pref", "SaveNotFound",
]
