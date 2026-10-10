"""Run economy — bankroll, bets, settlement and streak rewards (pure helpers)."""

from __future__ import annotations

import random
from dataclasses import dataclass

from chaos_blackjack.app.config import DEFAULT_BLACKJACK_PAYS, DEFAULT_REWARD_STREAK


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


# Round outcomes. "player" / "dealer" / "push" come from the RuleEngine;
# the controller adds "blackjack" (natural 21) and "surrender".
WIN_OUTCOMES = frozenset({"player", "blackjack"})


def settlement_delta(
    bet: int,
    outcome: str,
    *,
    blackjack_pays: tuple[int, int] = DEFAULT_BLACKJACK_PAYS,
) -> int:
    """Bankroll change for one round. Fractions round in the house's favour."""
    if outcome == "player":
        return bet
    if outcome == "blackjack":
        num, den = blackjack_pays
        return bet * num // den
    if outcome == "dealer":
        return -bet
    if outcome == "surrender":
        return -(bet - bet // 2)  # half the bet comes back
    return 0


def settle_money(money: int, bet: int, outcome: str, **kwargs) -> int:
    return money + settlement_delta(bet, outcome, **kwargs)


def update_streak_and_maybe_reward(
    *,
    run: RunState,
    outcome: str,
    reward_pool: tuple[str, ...],
    rng: random.Random,
    reward_streak: int = DEFAULT_REWARD_STREAK,
) -> str | None:
    if outcome in WIN_OUTCOMES:
        run.win_streak += 1
        if run.win_streak >= reward_streak and reward_pool:
            reward = rng.choice(reward_pool)
            run.items = run.items + (reward,)
            run.win_streak = 0
            return reward
        return None
    run.win_streak = 0
    return None
