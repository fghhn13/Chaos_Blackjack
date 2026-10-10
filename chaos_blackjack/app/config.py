"""Run configuration — every tunable of a run in one place (CLI / GUI share it).

Default values come from the `default` balance profile
(`chaos_blackjack/data/seed/default.sql`); front-ends build a config from
the player's chosen profile with `RunConfig.from_balance(load_balance())`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.data.balance import Balance, default_balance

_DEFAULTS = default_balance()

DEFAULT_START_MONEY = _DEFAULTS.start_money
DEFAULT_TARGET_MONEY = _DEFAULTS.target_money
# Shop: placeholder prices (not balanced yet), slots per restock, rounds per restock.
DEFAULT_SHOP_PRICES: dict[str, int] = _DEFAULTS.shop_prices
DEFAULT_SHOP_SLOTS = _DEFAULTS.shop_slots
DEFAULT_SHOP_REFRESH_ROUNDS = _DEFAULTS.shop_refresh_rounds
DEFAULT_DEALER_STAND_ON = _DEFAULTS.dealer_stand_on
DEFAULT_BLACKJACK_PAYS = _DEFAULTS.blackjack_pays
# Legacy streak reward, used only by the text CLI (ui/session.py).
DEFAULT_REWARD_STREAK = 2
DEFAULT_REWARD_POOL: tuple[str, ...] = ("peek", "shield", "swap")


@dataclass(frozen=True)
class RunConfig:
    start_money: int = DEFAULT_START_MONEY
    target_money: int = DEFAULT_TARGET_MONEY
    objective: str = _DEFAULTS.objective
    shop_prices: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SHOP_PRICES))
    shop_slots: int = DEFAULT_SHOP_SLOTS
    shop_refresh_rounds: int = DEFAULT_SHOP_REFRESH_ROUNDS
    dealer_stand_on: int = DEFAULT_DEALER_STAND_ON
    blackjack_pays: tuple[int, int] = DEFAULT_BLACKJACK_PAYS  # natural 21 payout ratio
    allow_double: bool = _DEFAULTS.allow_double
    allow_surrender: bool = _DEFAULTS.allow_surrender
    enable_chaos: bool = False
    seed: int | None = None
    balance_profile: str = _DEFAULTS.profile  # where the numbers came from (for saves / reports)

    @classmethod
    def from_balance(cls, balance: Balance, **overrides: Any) -> "RunConfig":
        """Config with every tunable from `balance`; `overrides` set the rest
        (enable_chaos, seed) or replace single values."""
        values: dict[str, Any] = {
            "start_money": balance.start_money,
            "target_money": balance.target_money,
            "objective": balance.objective,
            "shop_prices": balance.shop_prices,
            "shop_slots": balance.shop_slots,
            "shop_refresh_rounds": balance.shop_refresh_rounds,
            "dealer_stand_on": balance.dealer_stand_on,
            "blackjack_pays": balance.blackjack_pays,
            "allow_double": balance.allow_double,
            "allow_surrender": balance.allow_surrender,
            "balance_profile": balance.profile,
        }
        values.update(overrides)
        return cls(**values)
