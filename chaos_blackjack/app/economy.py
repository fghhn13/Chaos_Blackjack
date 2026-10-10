"""Run economy — bankroll, bets, settlement and streak rewards (pure helpers)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from chaos_blackjack.app.config import DEFAULT_REWARD_STREAK


@dataclass
class RunState:
    money: int
    start_money: int
    round: int
    target_money: int
    objective: str
    win_streak: int
    current_bet: int
    items: tuple[str, ...]


def bet_limits(money: int) -> tuple[int, int]:
    return (1, money // 2)


def can_bet(money: int) -> bool:
    lo, hi = bet_limits(money)
    return hi >= lo


def settle_money(money: int, bet: int, outcome: str) -> int:
    if outcome == "player":
        return money + bet
    if outcome == "dealer":
        return money - bet
    return money


def settlement_delta(bet: int, outcome: str) -> int:
    return settle_money(0, bet, outcome)


def update_streak_and_maybe_reward(
    *,
    run: RunState,
    outcome: str,
    reward_pool: tuple[str, ...],
    rng: random.Random,
    reward_streak: int = DEFAULT_REWARD_STREAK,
) -> str | None:
    if outcome == "player":
        run.win_streak += 1
        if run.win_streak >= reward_streak and reward_pool:
            reward = rng.choice(reward_pool)
            run.items = run.items + (reward,)
            run.win_streak = 0
            return reward
        return None
    run.win_streak = 0
    return None
