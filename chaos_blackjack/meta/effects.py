"""Upgrade effects — what a meta upgrade does to a run's RunConfig.

An effect is code; an upgrade is a `meta_upgrade` row naming an effect and
its params. A new upgrade of an existing kind needs only a row in
data/seed/default.sql; a new kind of effect is registered here (or from a
plugin) with `register_effect`.

`apply(config, amount, params)` gets the level (permanent) or 1 (one copy of
a consumable) and returns the new config. `title` / `describe` give
player-facing text.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from chaos_blackjack.app.config import RunConfig

Apply = Callable[[RunConfig, int, dict[str, Any]], RunConfig]
Text = Callable[[dict[str, Any], int], str]


@dataclass(frozen=True)
class Effect:
    id: str
    apply: Apply
    title: Callable[[dict[str, Any]], str]
    describe: Text          # (params, level or copies) -> sentence


_EFFECTS: dict[str, Effect] = {}


def register_effect(effect: Effect) -> Effect:
    _EFFECTS[effect.id] = effect
    return effect


def get_effect(effect_id: str) -> Effect:
    try:
        return _EFFECTS[effect_id]
    except KeyError:
        raise KeyError(f"Unknown upgrade effect {effect_id!r}; known: {', '.join(sorted(_EFFECTS))}") from None


def effect_ids() -> list[str]:
    return sorted(_EFFECTS)


def _item_name(item: str) -> str:
    return item.replace("_", " ").title()


# ------------------------------------------------------------------ built-ins

register_effect(Effect(
    "run.start_money_add",
    apply=lambda c, n, p: replace(c, start_money=c.start_money + n * int(p.get("amount", 0))),
    title=lambda p: "Deeper Pockets",
    describe=lambda p, n: f"Start every run with +{int(p.get('amount', 0)) * max(n, 1)} chips.",
))

register_effect(Effect(
    "shop.slots_add",
    apply=lambda c, n, p: replace(c, shop_slots=c.shop_slots + n * int(p.get("amount", 0))),
    title=lambda p: "Wider Shelves",
    describe=lambda p, n: f"The shop offers {int(p.get('amount', 0)) * max(n, 1)} more item(s).",
))


def _discount(c: RunConfig, n: int, p: dict[str, Any]) -> RunConfig:
    pct = min(90, n * int(p.get("pct", 0)))
    prices = {item: max(1, round(price * (100 - pct) / 100)) for item, price in c.shop_prices.items()}
    return replace(c, shop_prices=prices)


register_effect(Effect(
    "shop.discount_pct",
    apply=_discount,
    title=lambda p: "Regular Customer",
    describe=lambda p, n: f"Shop prices are {min(90, int(p.get('pct', 0)) * max(n, 1))}% lower (at least 1).",
))

register_effect(Effect(
    "meta.bring_kinds_add",
    apply=lambda c, n, p: replace(c, bring_kinds=c.bring_kinds + n * int(p.get("amount", 0))),
    title=lambda p: "Bag Space",
    describe=lambda p, n: f"Bring {int(p.get('amount', 0)) * max(n, 1)} more kind(s) of consumable to each run.",
))

register_effect(Effect(
    "shop.free_rerolls_add",
    apply=lambda c, n, p: replace(c, free_rerolls=c.free_rerolls + n * int(p.get("amount", 0))),
    title=lambda p: "Reroll Pass",
    describe=lambda p, n: f"Reroll the table shop {int(p.get('amount', 0)) * max(n, 1)} time(s) per run for free.",
))

register_effect(Effect(
    "run.starting_item",
    apply=lambda c, n, p: replace(c, starting_items=c.starting_items + (str(p["item"]),) * n),
    title=lambda p: f"Starter: {_item_name(str(p.get('item', '?')))}",
    describe=lambda p, n: f"Start the run with a {_item_name(str(p.get('item', '?')))} in your inventory.",
))

register_effect(Effect(
    "unlock_mode",
    apply=lambda c, n, p: c,  # read by the mode picker, not by the run
    title=lambda p: f"Mode: {str(p.get('mode', '?')).title()}",
    describe=lambda p, n: f"Unlocks the {str(p.get('mode', '?')).title()} game mode.",
))

__all__ = ["Effect", "effect_ids", "get_effect", "register_effect"]
