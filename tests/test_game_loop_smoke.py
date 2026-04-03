"""GameLoop smoke — one round structures without hanging."""

from __future__ import annotations

from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import GamePhase


def test_new_round_and_chaos_phase() -> None:
    loop = GameLoop()
    st = loop.new_round(seed=12345)
    assert st.phase == GamePhase.PLAYER_TURN
    assert len(st.player_hand) == 2
    st2 = loop.apply_chaos_phase(st)
    assert st2.chaos_budget_remaining <= st.chaos_budget_remaining


def test_run_round_until_done_resolves() -> None:
    loop = GameLoop()
    st = loop.new_round(seed=999)
    final = loop.run_round_until_done(st)
    assert final.phase == GamePhase.RESOLVED
    assert loop.outcome_label(final) in ("player", "dealer", "push")
