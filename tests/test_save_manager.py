"""SaveManager tests: save/load/list round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from chaos_blackjack.core.run_state import (
    CardSnapshot,
    GameStateSnapshot,
    ModifierSnapshot,
    RunSaveData,
)
import chaos_blackjack.core.save_manager as save_manager


@pytest.mark.parametrize("name_in", ["save_1", "save_1.json", "  save_2  "])
def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch, name_in: str) -> None:
    # Redirect save directory to a temp folder.
    monkeypatch.setattr(save_manager, "SAVE_DIR", tmp_path / "saves")

    snap = GameStateSnapshot(
        player_hand=[CardSnapshot(rank="9", suit=""), CardSnapshot(rank="A", suit="")],
        dealer_hand=[CardSnapshot(rank="K", suit=""), CardSnapshot(rank="2", suit="")],
        deck=[CardSnapshot(rank="10", suit="")],
        phase="PLAYER_TURN",
        chaos_budget_remaining=3,
        inventory=["peek", "swap"],
    )

    data = RunSaveData(
        version=1,
        money=120,
        start_money=100,
        round=3,
        items=["peek", "swap"],
        objective="double_money",
        win_streak=1,
        target_money=400,
        current_bet=20,
        enable_chaos=False,
        game_state=snap,
        active_modifiers=[ModifierSnapshot(id="reverse_bust", params={})],
        chaos_actions_this_turn=0,
    )

    save_manager.save_game(data, name=name_in)

    fname = save_manager.normalize_save_name(name_in)
    assert fname in save_manager.list_saves()
    loaded = save_manager.load_game(fname)
    assert loaded == data

