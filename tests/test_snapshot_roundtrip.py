"""Snapshot round-trip tests for GameState <-> GameStateSnapshot."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.ui.session import _game_state_to_snapshot, _snapshot_to_game_state


def test_game_state_snapshot_roundtrip() -> None:
    st = GameState(
        player_hand=(Card(Rank("7"), "♠"), Card(Rank("A"), "♥")),
        dealer_hand=(Card(Rank("K"), "♣"), Card(Rank("2"), "♦")),
        deck=(Card(Rank("10"), "♠"), Card(Rank("9"), "♣")),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=2,
        inventory=("peek", "swap"),
    )
    snap = _game_state_to_snapshot(st)
    st2 = _snapshot_to_game_state(snap)
    assert st2 == st

