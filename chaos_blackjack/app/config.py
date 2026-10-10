"""Run configuration — every tunable of a run in one place (CLI / GUI share it)."""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_START_MONEY = 100
DEFAULT_TARGET_MONEY = 400
# Shop: placeholder prices (not balanced yet), slots per restock, rounds per restock.
DEFAULT_SHOP_PRICES: dict[str, int] = {
    "peek": 10,
    "danger_radar": 10,
    "swap": 20,
    "hole_card_hacker": 25,
    "fate_oracle": 25,
    "shield": 30,
}
DEFAULT_SHOP_SLOTS = 3
DEFAULT_SHOP_REFRESH_ROUNDS = 2
# Legacy streak reward, used only by the text CLI (ui/session.py).
DEFAULT_REWARD_STREAK = 2
DEFAULT_REWARD_POOL: tuple[str, ...] = ("peek", "shield", "swap")
DEFAULT_DEALER_STAND_ON = 17
DEFAULT_BLACKJACK_PAYS = (3, 2)


@dataclass(frozen=True)
class RunConfig:
    start_money: int = DEFAULT_START_MONEY
    target_money: int = DEFAULT_TARGET_MONEY
    objective: str = "double_money"
    shop_prices: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SHOP_PRICES))
    shop_slots: int = DEFAULT_SHOP_SLOTS
    shop_refresh_rounds: int = DEFAULT_SHOP_REFRESH_ROUNDS
    dealer_stand_on: int = DEFAULT_DEALER_STAND_ON
    blackjack_pays: tuple[int, int] = DEFAULT_BLACKJACK_PAYS  # natural 21 payout ratio
    allow_double: bool = True
    allow_surrender: bool = True
    enable_chaos: bool = False
    seed: int | None = None
    chaos_guidance_probability: float = 0.5
    chaos_memory_enabled: bool = False
    chaos_memory_limit: int = 32

    def __post_init__(self) -> None:
        if not 0 <= self.chaos_guidance_probability <= 1:
            raise ValueError("Chaos guidance probability must be between 0 and 1")
        if self.chaos_memory_limit < 1:
            raise ValueError("Chaos memory limit must be positive")
