"""Run configuration — every tunable of a run in one place (CLI / GUI share it).

Default values come from the `default` balance profile
(`chaos_blackjack/data/seed/default.sql`); front-ends build a config from
the player's chosen profile with `RunConfig.from_balance(load_balance())`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from chaos_blackjack.data.balance import Balance, config_fingerprint, default_balance

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
    # Items whose shop_prices entry is a percentage of the bankroll (see app/shop.py).
    shop_bankroll_pct: tuple[str, ...] = _DEFAULTS.shop_bankroll_pct
    # Bankroll that percentage prices never go below: the profile's start bankroll,
    # unchanged by upgrades so a richer start does not raise opening prices.
    shop_price_floor: int = DEFAULT_START_MONEY
    shop_reroll_price: int = _DEFAULTS.shop_reroll_price
    free_rerolls: int = 0          # rerolls per run that cost nothing (Reroll Pass)
    bring_kinds: int = _DEFAULTS.meta_bring_kinds  # consumable kinds a player may bring
    dealer_stand_on: int = DEFAULT_DEALER_STAND_ON
    blackjack_pays: tuple[int, int] = DEFAULT_BLACKJACK_PAYS  # natural 21 payout ratio
    allow_double: bool = _DEFAULTS.allow_double
    allow_surrender: bool = _DEFAULTS.allow_surrender
    min_bet: int = _DEFAULTS.min_bet
    max_bet_fraction: float = _DEFAULTS.max_bet_fraction  # of the bankroll, rounded down
    # Chaos: fixed params per rule (win over the AI's), rules switched off, and
    # what the offline Chaos AI picks: (rule_id, AI params, weight).
    chaos_rule_params: dict[str, dict[str, Any]] = field(default_factory=lambda: _DEFAULTS.chaos_rule_params)
    disabled_rules: tuple[str, ...] = _DEFAULTS.disabled_rules
    chaos_stub: tuple[tuple[str, dict[str, Any], float], ...] = _DEFAULTS.chaos_stub
    item_params: dict[str, dict[str, Any]] = field(default_factory=lambda: _DEFAULTS.item_params)
    enable_chaos: bool = False
    seed: int | None = None
    content_packs: tuple[str, ...] = ()
    ai_id: str = "default"
    starting_items: tuple[str, ...] = ()
    use_llm: bool | None = None
    chaos_guidance_probability: float = _DEFAULTS.chaos_guidance_probability
    chaos_memory_enabled: bool = _DEFAULTS.chaos_memory_enabled
    chaos_memory_limit: int = _DEFAULTS.chaos_memory_limit
    balance_profile: str = _DEFAULTS.profile  # where the numbers came from (for saves / reports)

    def __post_init__(self) -> None:
        if not 0 <= self.chaos_guidance_probability <= 1:
            raise ValueError("Chaos guidance probability must be between 0 and 1")
        if self.chaos_memory_limit < 1:
            raise ValueError("Chaos memory limit must be positive")

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
            "shop_bankroll_pct": balance.shop_bankroll_pct,
            "shop_price_floor": balance.start_money,
            "shop_reroll_price": balance.shop_reroll_price,
            "bring_kinds": balance.meta_bring_kinds,
            "dealer_stand_on": balance.dealer_stand_on,
            "blackjack_pays": balance.blackjack_pays,
            "allow_double": balance.allow_double,
            "allow_surrender": balance.allow_surrender,
            "min_bet": balance.min_bet,
            "max_bet_fraction": balance.max_bet_fraction,
            "chaos_rule_params": balance.chaos_rule_params,
            "disabled_rules": balance.disabled_rules,
            "chaos_stub": balance.chaos_stub,
            "item_params": balance.item_params,
            "chaos_guidance_probability": balance.chaos_guidance_probability,
            "chaos_memory_enabled": balance.chaos_memory_enabled,
            "chaos_memory_limit": balance.chaos_memory_limit,
            "balance_profile": balance.profile,
        }
        values.update(overrides)
        return cls(**values)

    @property
    def balance_hash(self) -> str:
        """Fingerprint of the numbers (not the profile name, seed or chaos switch)."""
        return config_fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready copy (agent run files keep the numbers a run started with)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any], **overrides: Any) -> "RunConfig":
        """Inverse of `to_dict`; unknown keys are ignored, missing ones use defaults."""
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        if "blackjack_pays" in values:
            values["blackjack_pays"] = tuple(int(x) for x in values["blackjack_pays"])
        if "disabled_rules" in values:
            values["disabled_rules"] = tuple(values["disabled_rules"])
        for key in ("content_packs", "starting_items", "shop_bankroll_pct"):
            if key in values:
                values[key] = tuple(values[key])
        if "chaos_stub" in values:
            values["chaos_stub"] = tuple((str(r), dict(p), float(w)) for r, p, w in values["chaos_stub"])
        values.update(overrides)
        return cls(**values)
