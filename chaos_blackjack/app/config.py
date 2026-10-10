"""Run configuration — every tunable of a run in one place (CLI / GUI share it)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_START_MONEY = 100
DEFAULT_TARGET_MONEY = 400
DEFAULT_REWARD_STREAK = 2
DEFAULT_REWARD_POOL: tuple[str, ...] = ("peek", "shield", "swap")
DEFAULT_DEALER_STAND_ON = 17
DEFAULT_BLACKJACK_PAYS = (3, 2)


@dataclass(frozen=True)
class RunConfig:
    start_money: int = DEFAULT_START_MONEY
    target_money: int = DEFAULT_TARGET_MONEY
    objective: str = "double_money"
    reward_streak: int = DEFAULT_REWARD_STREAK
    reward_pool: tuple[str, ...] = DEFAULT_REWARD_POOL
    dealer_stand_on: int = DEFAULT_DEALER_STAND_ON
    blackjack_pays: tuple[int, int] = DEFAULT_BLACKJACK_PAYS  # natural 21 payout ratio
    allow_double: bool = True
    allow_surrender: bool = True
    enable_chaos: bool = False
    seed: int | None = None
    content_packs: tuple[str, ...] = ()
    ai_id: str = "default"
    starting_items: tuple[str, ...] = ()
    use_llm: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunConfig:
        values = dict(data)
        for key in ("reward_pool", "blackjack_pays", "content_packs", "starting_items"):
            if key in values:
                values[key] = tuple(values[key])
        return cls(**values)
