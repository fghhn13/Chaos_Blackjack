"""Run configuration — every tunable of a run in one place (CLI / GUI share it).

Default values come from the `default` balance profile
(`chaos_blackjack/data/seed/default.sql`); front-ends build a config from
the player's chosen profile with `RunConfig.from_balance(load_balance())`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
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


def _multiple(start: int, multiple: float) -> int:
    """start × multiple, rounded half up."""
    return math.floor(start * multiple + 0.5)


@dataclass(frozen=True)
class RunConfig:
    start_money: int = DEFAULT_START_MONEY
    target_money: int = DEFAULT_TARGET_MONEY
    # Goal as a multiple of the starting cash (docs/design/CARRIED_CHIPS.zh-CN.md §4); 0 = use target_money.
    # The target is then also the table's ceiling: winnings above it are not paid.
    target_multiple: float = 0.0
    # Full Haul: from start_money × this, the player may leave with a win (a table that offers it); 0 = never.
    exit_multiple: float = 0.0
    objective: str = _DEFAULTS.objective
    shop_prices: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SHOP_PRICES))
    shop_slots: int = DEFAULT_SHOP_SLOTS
    shop_refresh_rounds: int = DEFAULT_SHOP_REFRESH_ROUNDS
    # Items whose shop_prices entry is a percentage of the bankroll (see app/shop.py).
    shop_bankroll_pct: tuple[str, ...] = _DEFAULTS.shop_bankroll_pct
    # Optional pricing floor retained for saved/custom configurations.
    # New runs price against their current bankroll, with a one-chip minimum.
    shop_price_floor: int = 0
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
    # Mode (docs/design/AI_MODES.md): the mode id, who hosts the table (a bundled
    # host id; None = runs from before hosts, shown as Poker Head) and the
    # allowed Chaos rules (None = all).
    mode: str = ""
    host: str | None = None
    rule_pool: tuple[str, ...] | None = None
    # Numbers of a mode's own mechanics ("<mode id>.<name>", e.g. "j54.capital_target").
    mode_settings: dict[str, Any] = field(default_factory=lambda: dict(_DEFAULTS.mode_settings))

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
            "shop_price_floor": 0,
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
            "mode_settings": dict(balance.mode_settings),
        }
        values.update(overrides)
        return cls(**values)

    def resolved(self) -> "RunConfig":
        """target_money from target_multiple, when one is set (call again after changing start_money)."""
        if not self.target_multiple:
            return self
        return replace(self, target_money=_multiple(self.start_money, self.target_multiple))

    @property
    def exit_money(self) -> int:
        """Net assets from which Full Haul may be taken (0 = never)."""
        return _multiple(self.start_money, self.exit_multiple) if self.exit_multiple else 0

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
        if values.get("rule_pool") is not None:
            values["rule_pool"] = tuple(values["rule_pool"])
        if "chaos_stub" in values:
            values["chaos_stub"] = tuple((str(r), dict(p), float(w)) for r, p, w in values["chaos_stub"])
        values.update(overrides)
        return cls(**values)
