"""Run configuration — every tunable of a run in one place (CLI / GUI share it)."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_START_MONEY = 100
DEFAULT_TARGET_MONEY = 400
DEFAULT_REWARD_STREAK = 2
DEFAULT_REWARD_POOL: tuple[str, ...] = ("peek", "shield", "swap")
DEFAULT_DEALER_STAND_ON = 17


@dataclass(frozen=True)
class RunConfig:
    start_money: int = DEFAULT_START_MONEY
    target_money: int = DEFAULT_TARGET_MONEY
    objective: str = "double_money"
    reward_streak: int = DEFAULT_REWARD_STREAK
    reward_pool: tuple[str, ...] = DEFAULT_REWARD_POOL
    dealer_stand_on: int = DEFAULT_DEALER_STAND_ON
    enable_chaos: bool = False
    seed: int | None = None
