"""Live registry adapters. This module never imports the GUI or constructs an AI."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, replace
from functools import partial

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex.demo import rule_params
from chaos_blackjack.codex.models import CodexEntry
from chaos_blackjack.codex.registry import register_codex_provider
from chaos_blackjack.codex.scripts import ITEM_DEMOS, RULE_DEMOS
from chaos_blackjack.registry import auto_load_plugins, get_registry
from chaos_blackjack.ui.descriptions import describe_modifier

_RULE_NAMES = {
    "modify_card_value": "Value Shift", "great_crash": "Great Crash",
    "odd_even_chaos": "Odd-Even Chaos", "suit_power": "Suit Power",
    "fragile_bust": "Fragile Bust", "reverse_bust": "Reverse Bust",
    "tiebreaker_shift": "Tiebreaker Shift",
}
_RULE_SUMMARIES = {
    "modify_card_value": "Shift the value of every card.",
    "great_crash": "Face cards and tens take a new value.",
    "odd_even_chaos": "Even and odd numeric ranks change differently.",
    "suit_power": "Red and black suits change differently.",
    "fragile_bust": "The table's bust threshold falls.",
    "reverse_bust": "A player bust becomes a push.",
    "tiebreaker_shift": "Equal totals award a win instead of a push.",
}
_ITEM_SUMMARIES = {
    "peek": "Reveal the next card's rank.",
    "swap": "Replace your first card with the top deck card.",
    "shield": "Dispel all active Chaos rules for this round.",
    "danger_radar": "Learn whether your next hit would bust.",
    "fate_oracle": "Reveal the ranks of the next cards.",
    "hole_card_hacker": "Reveal the dealer's hidden card.",
}


def _title(entry_id: str) -> str:
    return entry_id.replace("_", " ").title()


def _registry(config: RunConfig):
    auto_load_plugins()
    packs = getattr(config, "content_packs", ())
    if packs:
        from chaos_blackjack.content.loader import load_content_packs

        return load_content_packs(packs).registry
    return get_registry()


def _rule_detail(rule_id: str, config: RunConfig) -> str:
    modifier = _registry(config).build_chaos_rule(rule_id, rule_params(rule_id, config))
    if modifier is None:
        raise ValueError(f"Rule is no longer registered: {rule_id!r}")
    text = describe_modifier(modifier)
    if rule_id == "reverse_bust":
        text += " A hit that busts still ends the hand immediately, but the bet is returned instead of lost."
    if rule_id == "odd_even_chaos":
        text += " Only numeric ranks from 2 through 9 change; aces, tens and face cards keep their values."
    if rule_id in config.disabled_rules:
        text += " Disabled for AI selection in this balance profile; the demo previews its effect."
    return text


def rule_entries(config: RunConfig) -> list[CodexEntry]:
    auto_load_plugins()
    # Registry has no public enumeration API on the M4a base. Keep the
    # compatibility seam here, rather than changing A's shared files.
    registry = _registry(config)
    return [CodexEntry(
        "rule", rid, getattr(factory, "codex_name", _RULE_NAMES.get(rid, _title(rid))),
        getattr(factory, "codex_icon", rid),
        getattr(factory, "codex_summary", _RULE_SUMMARIES.get(rid, "A registered Chaos rule.")),
        getattr(factory, "codex_detail", partial(_rule_detail, rid)),
        getattr(factory, "codex_demo", RULE_DEMOS.get(rid)),
        getattr(factory, "codex_order", 0),
    ) for rid, factory in tuple(registry._chaos_rules.items())]


def _item_detail(item_id: str, config: RunConfig) -> str:
    registry = _registry(config)
    help_fn = getattr(registry, "describe_item", lambda iid: "")
    text = _ITEM_SUMMARIES.get(item_id, help_fn(item_id) or f"Registered item: {_title(item_id)}.")
    if item_id == "fate_oracle":
        defaults = RunConfig().item_params[item_id]
        count = max(1, int(config.item_params.get(item_id, {}).get("cards", defaults["cards"])))
        text = f"Reveal the ranks of the next {count} cards, or all remaining cards if fewer remain."
    elif item_id == "danger_radar":
        text += " The answer uses the rules in force, including Chaos value changes and bust limits."
    elif item_id == "shield":
        text += " It is consumed only when at least one rule can be dispelled."
    elif item_id not in _ITEM_SUMMARIES and config.item_params.get(item_id):
        text += " Parameters: " + json.dumps(config.item_params[item_id], sort_keys=True)
    price = config.shop_prices.get(item_id)
    if price is None:
        text += " Not offered by this balance profile's shop."
    elif item_id in getattr(config, "shop_bankroll_pct", ()):
        text += (f" Shop price: {price}% of your bankroll when the stock rolls "
                 f"({max(1, int(price * config.shop_price_floor / 100 + 0.5))} chips at the least).")
    else:
        text += f" Shop price: {price} chips."
    text += (f" The shop offers up to {config.shop_slots} different items and restocks every "
             f"{config.shop_refresh_rounds} rounds. A successful use consumes one copy.")
    return text


def item_entries(config: RunConfig) -> list[CodexEntry]:
    auto_load_plugins()
    registry = _registry(config)
    help_fn = getattr(registry, "describe_item", lambda iid: "")
    return [CodexEntry(
        "item", iid, getattr(cls, "codex_name", _title(iid)), getattr(cls, "codex_icon", iid),
        getattr(cls, "codex_summary", _ITEM_SUMMARIES.get(iid, help_fn(iid) or "A registered table item.")),
        getattr(cls, "codex_detail", partial(_item_detail, iid)),
        getattr(cls, "codex_demo", ITEM_DEMOS.get(iid)), getattr(cls, "codex_order", 0),
    ) for iid, cls in tuple(registry._items.items())]


@dataclass(frozen=True)
class _BuiltinMode:
    id: str
    name: str
    description: str
    icon: str
    overrides: dict
    unlocked_by: str | None = None


def _modes():
    try:
        module = importlib.import_module("chaos_blackjack.modes")
    except ModuleNotFoundError as exc:
        if exc.name != "chaos_blackjack.modes":
            raise
        return [
            _BuiltinMode("normal", "Classic", "Plain blackjack with the shop. The Chaos AI stays out of it.", "mode_normal", {"enable_chaos": False}),
            _BuiltinMode("chaos", "Chaos", "The Chaos AI can change the rules each round.", "mode_chaos", {"enable_chaos": True}),
        ]
    # Agent A owns this registry. Discover it at query time, so installing
    # modes after the codex is imported immediately replaces the fallback.
    return module.modes()


def _mode_detail(mode_id: str, config: RunConfig) -> str:
    mode = next(m for m in _modes() if m.id == mode_id)
    cfg = replace(config, **mode.overrides)
    num, den = cfg.blackjack_pays
    text = (f"{mode.description} Start with {cfg.start_money} chips and reach {cfg.target_money}. "
            f"Bets range from {cfg.min_bet} to {cfg.max_bet_fraction * 100:g}% of your bankroll, rounded down. "
            f"Dealer stands on {cfg.dealer_stand_on} or more. Natural blackjack pays {num}:{den}. "
            f"Double down is {'enabled' if cfg.allow_double else 'disabled'}; "
            f"surrender is {'enabled' if cfg.allow_surrender else 'disabled'}.")
    if mode.unlocked_by:
        text += f" Unlock requirement: {mode.unlocked_by}."
    return text


def mode_entries(config: RunConfig) -> list[CodexEntry]:
    return [CodexEntry("mode", m.id, m.name, m.icon, m.description,
                       partial(_mode_detail, m.id), None, getattr(m, "order", index))
            for index, m in enumerate(_modes())]


def _ai_detail(config: RunConfig) -> str:
    from chaos_blackjack.ai.permissions_loader import load_permission_profile

    allowed = load_permission_profile("easy")["allowed_rules"]
    available = [r for r in allowed if r not in config.disabled_rules]
    name = lambda rid: _RULE_NAMES.get(rid, _title(rid))
    choices = [f"{name(rid)} (weight {weight:g})" for rid, _params, weight in config.chaos_stub
               if weight > 0 and rid in available]
    return (
        "Chaos proposes structured actions; the permission policy checks them before they affect the table. "
        "The offline AI draws from the balance profile's weighted choices, while the optional model chooses its own action. "
        "Fixed rule parameters always override the proposal. "
        f"Enabled rule choices: {', '.join(map(name, available)) or 'none'}. "
        f"Offline weighted choices: {', '.join(choices) or 'none'}. "
        f"Portrait advice guides with probability {config.chaos_guidance_probability * 100:g}%; other advice may mislead. "
        f"Run memory is {'enabled' if config.chaos_memory_enabled else 'disabled'}, "
        f"with a limit of {config.chaos_memory_limit} events."
    )


def ai_entries(config: RunConfig) -> list[CodexEntry]:
    entries = [CodexEntry("ai", "default", "Chaos AI", "chaos_calm",
                       "A sandboxed opponent that bends rules and offers unreliable advice.",
                       _ai_detail, None)]
    registry = _registry(config)
    for ai_id in getattr(registry, "ai_ids", lambda: ("default",))():
        if ai_id == "default":
            continue
        profile = registry.resolve_ai(ai_id)
        entries.append(CodexEntry("ai", ai_id, getattr(profile, "codex_name", _title(ai_id)),
                                  getattr(profile, "codex_icon", "chaos_calm"), profile.description,
                                  partial(_pack_ai_detail, ai_id), getattr(profile, "codex_demo", None)))
    return entries


def _pack_ai_detail(ai_id: str, config: RunConfig) -> str:
    profile = _registry(config).resolve_ai(ai_id)
    rules = [rid for rid in profile.permissions.get("allowed_rules", ()) if rid not in config.disabled_rules]
    names = [_RULE_NAMES.get(rid, _title(rid)) for rid in rules]
    return (f"{profile.description} Allowed rules: {', '.join(names) or 'none'}. "
            f"Portrait advice guides with probability {config.chaos_guidance_probability * 100:g}%. "
            "Fixed rule parameters from the selected balance profile override AI proposals.")


def install() -> None:
    for kind, provider in (("rule", rule_entries), ("mode", mode_entries),
                           ("item", item_entries), ("ai", ai_entries)):
        register_codex_provider(kind, provider)
