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
from chaos_blackjack.ui.descriptions import RULE_NAMES, describe_modifier

_RULE_NAMES = RULE_NAMES
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
    ) for iid, cls in tuple(registry._items.items()) if getattr(cls, "codex_kind", "item") == "item"]


def _build_detail(item_id: str, config: RunConfig) -> str:
    from chaos_blackjack.codex.build_reference import detail

    return detail(item_id, config)


def build_entries(config: RunConfig) -> list[CodexEntry]:
    from chaos_blackjack.codex.build_reference import effect, price_label, related, timing
    from chaos_blackjack.poker_head.catalog import PRODUCTS

    return [CodexEntry("build", p.id, p.name, p.id, effect(p.id, config),
                       partial(_build_detail, p.id), None, i, p.kind, p.style,
                       timing(p.id), price_label(p.id, config), related(p.id))
            for i, p in enumerate(PRODUCTS.values())]


# Poker Head's environment rules (poker_head/environment.py): name and one-line summary per type.
_ENVIRONMENT = {
    "fixed": ("Card Rewrite", "Some cards count as a fixed value."),
    "shift": ("Card Shift", "Some cards count more or less."),
    "bust": ("Bust Limit", "Your bust limit falls, or the dealer's rises."),
    "tie": ("Ties to the House", "Equal totals go to the dealer."),
    "bust_outcome": ("Dealer Bust Pardon", "A dealer bust becomes a push."),
    "profit_cap": ("Withdrawal Limit", "A round's profit is capped."),
    "item_ban": ("Item Ban", "Your next consumable only lifts the ban."),
    "markup": ("Price Hike", "Consumables and permanents cost more."),
    "hidden": ("Face-Down Card", "Your second opening card is dealt face down."),
}


def _director(config: RunConfig):
    from chaos_blackjack.poker_head.director import Director

    settings = {k[len("chaos."):]: v for k, v in config.mode_settings.items() if k.startswith("chaos.")}
    return Director(settings, seed=0, rule_slots=int(config.mode_settings.get("chaos.rule_slots", 3)))


def _environment_detail(rule_type: str, config: RunConfig) -> str:
    from chaos_blackjack.poker_head.director import STAGE_NAMES, pool_summary

    d = _director(config)
    stages, example = [], None
    for index, (first, act, slots, budget) in enumerate(d.stages):
        weight = d.weights.get(rule_type, [0] * len(d.stages))[index]
        spec = d.pools[index].get(rule_type)
        last = d.stages[index + 1][0] - 1 if index + 1 < len(d.stages) else None
        rounds = f"rounds {first}–{last}" if last else f"round {first} on"
        if weight and spec:
            stages.append(f"{STAGE_NAMES[min(index, len(STAGE_NAMES) - 1)]} ({rounds}): {pool_summary(rule_type, spec)}")
            stage = d.stage(first)
            example = example or next(iter(d.variants(stage).get(rule_type, [])), None)
    text = _ENVIRONMENT[rule_type][1]
    if example is not None:
        text += f"\n\nFor example\n{example.title}: {example.effect_text()}\n\nGoes away\n{example.removal_text()}"
    text += "\n\nWhen it appears\n" + ("\n".join(stages) if stages else "Not in this profile's pools.")
    text += ("\n\nHow the dealer acts\nBefore you shop and bet each round, Poker Head may add one rule or replace "
             "one that has been in force for two rounds; it never changes the rules after the deal. Up to "
             f"{d.rule_slots} rules at once, one of each kind; fewer early on. A kind you clear waits two rounds "
             "before it can return, and one that ends waits a round.")
    return text


def environment_entries(config: RunConfig) -> list[CodexEntry]:
    from chaos_blackjack.poker_head.environment import TYPES

    return [CodexEntry("environment", t, _ENVIRONMENT[t][0], "ph_env_" + t, _ENVIRONMENT[t][1],
                       partial(_environment_detail, t), None, i, "environment")
            for i, t in enumerate(TYPES)]


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
    from chaos_blackjack.content.builtin_persona import HOST_NAMES

    mode = next(m for m in _modes() if m.id == mode_id)
    apply = getattr(mode, "apply", None)
    cfg = apply(config) if apply is not None else replace(config, **mode.overrides)
    num, den = cfg.blackjack_pays
    host = HOST_NAMES.get(getattr(mode, "host", ""), "")
    moves = " and ".join(m for m, on in (("double", cfg.allow_double), ("surrender", cfg.allow_surrender)) if on)
    text = mode.description
    if host:
        text += f" Your host: {host}."
    from chaos_blackjack.app.table_mechanics import table_goal

    goal = table_goal(cfg) or f"Turn {cfg.start_money} chips into {cfg.target_money}"
    text += (f" {goal}. Bet {cfg.min_bet} up to "
             f"{cfg.max_bet_fraction * 100:g}% of your bankroll; the dealer stands on {cfg.dealer_stand_on} and "
             f"blackjack pays {num}:{den}.")
    banned = " or ".join(m for m, on in (("double down", cfg.allow_double), ("surrender", cfg.allow_surrender))
                         if not on)
    if moves:
        text += f" You may {moves} on your first decision."
    if banned:
        text += f" No {banned} at this table."
    from chaos_blackjack.app.table_mechanics import table_factory

    if cfg.enable_chaos and getattr(table_factory(cfg), "environment_rules", False):
        text += " Before you shop and bet, the dealer may add or replace one environment rule; it grows harsher round by round."
    elif cfg.enable_chaos:
        pool = [r for r, _, w in cfg.chaos_stub if r and w > 0]
        if cfg.rule_pool is not None:
            pool = [r for r in pool if r in cfg.rule_pool]
        text += f" Before most hands one of {len(pool)} Chaos rules may change the game." if pool else ""
    else:
        text += " The rules never change."
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
    from chaos_blackjack.content.builtin_persona import default_persona

    persona = default_persona()
    entries = [CodexEntry("ai", "default", persona.name, persona.asset_id(persona.default),
                       "A sandboxed opponent that bends rules and offers unreliable advice.",
                       _ai_detail, None)]
    registry = _registry(config)
    for ai_id in getattr(registry, "ai_ids", lambda: ("default",))():
        if ai_id == "default":
            continue
        profile = registry.resolve_ai(ai_id)
        entries.append(CodexEntry("ai", ai_id, getattr(profile, "codex_name", None) or _title(ai_id),
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
                           ("item", item_entries), ("ai", ai_entries), ("build", build_entries),
                           ("environment", environment_entries)):
        register_codex_provider(kind, provider)
