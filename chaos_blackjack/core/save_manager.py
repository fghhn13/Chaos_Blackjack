"""Save/load for the text CLI — a thin wrapper over the SQLite save store.

Saves live in `data/game.db` (`chaos_blackjack.data.saves`). Old JSON files in
`chaos_blackjack/saves/` can be imported with
`python -m chaos_blackjack.data import-saves`.
"""

from __future__ import annotations

from chaos_blackjack.core.run_state import RunSaveData


def normalize_save_name(name: str) -> str:
    from chaos_blackjack.data.saves import normalize_save_name as normalize

    return normalize(name)


def list_saves() -> list[str]:
    from chaos_blackjack.data.saves import list_runs

    return [s.name for s in list_runs()]


def save_game(data: RunSaveData, name: str = "save_1") -> str:
    from chaos_blackjack.data.saves import save_run

    return save_run(data, name)


def load_game(name: str) -> RunSaveData:
    from chaos_blackjack.data.saves import load_run

    return load_run(name)
