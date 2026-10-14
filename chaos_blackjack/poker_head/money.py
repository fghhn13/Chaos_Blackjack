"""Poker Head's chip amounts scale with the run's starting cash (docs/design/CARRIED_CHIPS.zh-CN.md §11).

A balance profile writes every chip amount at this table (prices, money
products, the minimum bet curve, the declined-core cash, rerolls, Withdrawal
Limit caps) for a reference bankroll, `mode.chaos.money_base`. A run that
starts with more or less cash gets every amount multiplied by
`start_money / money_base`, so each one stays the same share of the bankroll.
Card numbers, percentages and multipliers never scale.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig

# Chip amounts inside money products' params (the principal is the shop price).
MONEY_PARAMS = {"ph_deposit": ("payout",), "ph_bond": ("payout", "failure"), "ph_stock": ("payout",),
                "ph_loan": ("advance", "repay")}
# Chip-valued table settings ("chaos.<name>"); min_bets is a comma list.
MONEY_SETTINGS = ("bet_step_add", "decline_cash", "reroll_step_add")


def factor(config: "RunConfig") -> Fraction:
    return Fraction(config.start_money, int(config.mode_settings.get("chaos.money_base", config.start_money)))


def chips(amount: int, f: Fraction) -> int:
    """`amount` scaled by `f`, rounded half up; a positive amount stays at least one chip."""
    if f == 1 or amount == 0:
        return amount
    return max(1, math.floor(amount * f + Fraction(1, 2))) if amount > 0 else -chips(-amount, f)


def core_cash(settings: dict) -> dict[str, int]:
    """Chips a core costs (negative) or brings (positive) when chosen: mode.chaos.core_cash, a JSON object."""
    raw = settings.get("chaos.core_cash") or "{}"
    return {str(k): int(v) for k, v in (json.loads(raw) if isinstance(raw, str) else raw).items()}


def scaled(config: "RunConfig") -> "RunConfig":
    """The config with every chip amount of this table scaled to the run's starting cash."""
    f = factor(config)
    if f == 1:
        return config
    settings = dict(config.mode_settings)
    for name in MONEY_SETTINGS:
        key = "chaos." + name
        if key in settings:
            settings[key] = chips(int(settings[key]), f)
    settings["chaos.min_bets"] = ",".join(str(chips(int(x), f)) for x in str(settings["chaos.min_bets"]).split(","))
    if settings.get("chaos.core_cash"):
        settings["chaos.core_cash"] = json.dumps({k: chips(int(v), f) for k, v in core_cash(settings).items()})
    params = {k: dict(v) for k, v in config.item_params.items()}
    for item_id, keys in MONEY_PARAMS.items():
        for key in keys:
            if key in params.get(item_id, {}):
                params[item_id][key] = chips(int(params[item_id][key]), f)
    return replace(config, mode_settings=settings, item_params=params,
                   shop_prices={k: chips(v, f) for k, v in config.shop_prices.items()},
                   shop_reroll_price=chips(config.shop_reroll_price, f))
