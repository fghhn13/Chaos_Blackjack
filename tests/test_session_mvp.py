"""Session-level MVP economy helpers."""

from __future__ import annotations

import random

from chaos_blackjack.contracts.items import ItemResult
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.ui.session import (
    MVP_REWARD_STREAK,
    RunState,
    _apply_item_effects,
    _bet_limits,
    _settle_money,
    _update_streak_and_maybe_reward,
)


def test_bet_limits_half_money_floor() -> None:
    assert _bet_limits(100) == (1, 50)
    assert _bet_limits(9) == (1, 4)


def test_settle_money_outcomes() -> None:
    assert _settle_money(100, 20, "player") == 120
    assert _settle_money(100, 20, "dealer") == 80
    assert _settle_money(100, 20, "push") == 100


def test_streak_reward_grants_item_and_resets() -> None:
    run = RunState(
        money=100,
        start_money=100,
        round=1,
        target_money=400,
        objective="double_money",
        win_streak=MVP_REWARD_STREAK - 1,
        current_bet=10,
        items=("peek",),
    )
    reward = _update_streak_and_maybe_reward(
        run=run,
        outcome="player",
        reward_pool=("shield",),
        rng=random.Random(1),
    )
    assert reward == "shield"
    assert run.win_streak == 0
    assert run.items == ("peek", "shield")


def test_streak_resets_on_loss() -> None:
    run = RunState(
        money=100,
        start_money=100,
        round=1,
        target_money=400,
        objective="double_money",
        win_streak=1,
        current_bet=10,
        items=(),
    )
    reward = _update_streak_and_maybe_reward(
        run=run,
        outcome="dealer",
        reward_pool=("shield",),
        rng=random.Random(1),
    )
    assert reward is None
    assert run.win_streak == 0


def test_apply_item_effects_swap_replaces_first_player_card() -> None:
    st = GameState(
        player_hand=(Card(Rank("7"), ""), Card(Rank("3"), "")),
        dealer_hand=(Card(Rank("9"), ""), Card(Rank("2"), "")),
        deck=(Card(Rank("K"), ""), Card(Rank("10"), "")),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=("swap",),
    )
    result = ItemResult(
        ok=True,
        message="swap",
        extra={"swap_top_into_first_player_card": True},
    )
    s2 = _apply_item_effects(st, result)
    assert [c.rank for c in s2.player_hand] == ["K", "3"]
    assert [c.rank for c in s2.deck] == ["10"]

