"""Parts — named pieces of table information, each turned into widgets.

A part reads the controller (never changes it) and returns widgets
(app/widgets.py) for a variant: `compact` (side columns), `full` (the run
panel) or `tail` (a few recent lines). Parts are composed per mode by a
layout (app/layout.py); the GUI draws whatever they return. A new table
mechanic adds parts — and maybe controller actions — but no GUI code.

    register_part("curse.meter", build_meter, available=lambda ctx: ctx.table is not None)

Core parts: core.items, core.actions, core.rules, core.log, core.run_stats. J-54's are in
chaos_blackjack/j54/parts.py. Parts that need the GUI itself (the host
portrait, the deck pile, the buttons, the live feed) are native GUI
components with the same ids (gui/components/side_column.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chaos_blackjack.app.help_text import ITEM_HELP
from chaos_blackjack.app.view import Action, GameView
from chaos_blackjack.app.widgets import (
    Act, Entry, ListWidget, Log, LogLine, Progress, Row, Rows, Slot, Slots, Widget,
)

if TYPE_CHECKING:
    from chaos_blackjack.app.controller import GameController

VARIANTS = ("compact", "full", "tail")


@dataclass(frozen=True)
class PartContext:
    controller: "GameController"
    view: GameView

    @property
    def table(self):
        return self.controller.table


Builder = Callable[[PartContext, str], tuple[Widget, ...]]


@dataclass(frozen=True)
class Part:
    id: str
    build: Builder
    available: Callable[[PartContext], bool] = lambda ctx: True


_PARTS: dict[str, Part] = {}


def register_part(part_id: str, build: Builder, *, available: Callable[[PartContext], bool] | None = None) -> Part:
    part = Part(part_id, build, available or (lambda ctx: True))
    _PARTS[part_id] = part
    return part


def get_part(part_id: str) -> Part | None:
    _load_builtin_parts()
    return _PARTS.get(part_id)


def build_part(part_id: str, ctx: PartContext, variant: str = "full") -> tuple[Widget, ...]:
    """Widgets of a part (empty when it is unknown or not available here)."""
    part = get_part(part_id)
    if part is None or not part.available(ctx):
        return ()
    return tuple(part.build(ctx, variant))


def _load_builtin_parts() -> None:
    import chaos_blackjack.j54.parts  # noqa: F401  (registers j54.*)
    import chaos_blackjack.poker_head.parts  # noqa: F401


def title(entry_id: str) -> str:
    return entry_id.replace("_", " ").title()


def rule_name(ctx: PartContext, rule_id: str) -> str:
    from chaos_blackjack.ui.descriptions import RULE_NAMES

    factory = ctx.controller.registry._chaos_rules.get(rule_id)  # noqa: SLF001 - no public lookup yet
    return getattr(factory, "codex_name", None) or RULE_NAMES.get(rule_id) or title(rule_id)


# ------------------------------------------------------------------ core


def _items(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """Held items; each is enabled by its own move (GameController.moves), with when and why not."""
    v = ctx.view
    held = [i for i in v.items if i.count > 0]

    def note(i) -> str:
        """When it can be used, and why not now (unless that is just the wrong phase); a ban first."""
        if i.note:
            return i.note
        when = f"{i.when}." if i.when else ""
        if i.usable or not i.reason or i.reason == f"{i.when} only.":
            return when
        return f"{when} Not now: {i.reason}".strip()

    def help_of(i) -> str:
        return i.description or ITEM_HELP.get(i.id, "")

    if variant == "compact":
        slots = tuple(Slot(i.id, i.count, f"{i.name or title(i.id)}: {help_of(i)} ({note(i).strip()})",
                           hotkey=str(n + 1) if n < 9 else "", act=Act(Action.USE_ITEM, i.id, i.usable), frame=i.group)
                      for n, i in enumerate(held))
        return (Slots(slots, title="Items", empty="No items"),)
    entries = tuple(Entry(i.name or title(i.id), f"{help_of(i)}  ·  {note(i)}" if note(i) else help_of(i),
                          icon=i.id, badge=f"×{i.count}",
                          tone="warn" if i.note else "" if i.usable else "muted",
                          act=Act(Action.USE_ITEM, i.id, i.usable), frame=i.group)
                    for i in held)
    return (ListWidget(entries, title="Items", empty="No items. Buy them in the shop while betting."),)


def _actions(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """The table's own moves (e.g. a once-per-round permanent), enabled as the controller says."""
    entries = tuple(Entry(m.label, m.reason, act=Act(m.action, m.arg, m.enabled), tone="" if m.enabled else "muted")
                    for m in ctx.view.moves if m.table and m.listed)
    return (ListWidget(entries, title="Table actions"),) if entries else ()


def _detail(name: str, text: str) -> str:
    """A rule description without the "<name>: " prefix rule descriptions start with."""
    head, sep, rest = text.partition(": ")
    return rest if sep and head.lower() == name.lower() else text


def _rule_entry(ctx: PartContext, r, full: bool) -> Entry:
    """One rule card: name, then (full) what it acts on, its effect, how long and how it goes away."""
    name = r.name or rule_name(ctx, r.id)
    if not r.effect:  # a Chaos AI modifier: its description is the whole story
        return Entry(name, _detail(name, r.description), icon=r.icon or r.id, tone="chaos", tooltip=r.description)
    left = "Until removed" if r.remaining is None else f"{r.remaining} round{'s' if r.remaining != 1 else ''}"
    badge = "Silenced" if r.silenced else f"{r.tier} · {left}" if r.tier else left
    text = f"{r.effect}  {r.removal}" if full else r.effect
    return Entry(f"{name} · {r.scope}" if full else name, text, icon=r.icon or r.id,
                 tone="muted" if r.silenced else "warn" if r.tier == "Heavy" else "chaos", badge=badge,
                 tooltip=(f"{r.tier} rule. " if r.tier else "") + f"{r.scope}: {r.description}"
                 + (" Silenced this round." if r.silenced else ""))


def _rules(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    v = ctx.view
    active = tuple(_rule_entry(ctx, r, variant != "compact") for r in v.active_rules)
    own_rules = any(r.effect for r in v.active_rules) or (ctx.table is not None and ctx.table.active_rules() is not None)
    if variant == "compact":
        empty = "None yet" if v.chaos_enabled else "Chaos off"
        return (ListWidget(active, title="Active rules", empty=empty, compact=len(active) > 1),)
    widgets: list[Widget] = [ListWidget(active, title="Rules in force" if own_rules else "Active this round",
                                        empty="No rule in force." if v.chaos_enabled else "This table never bends the rules.")]
    cfg = ctx.controller.config
    if cfg.enable_chaos and not own_rules:
        from chaos_blackjack.ui.descriptions import describe_modifier

        pool = [rid for rid, _, weight in cfg.chaos_stub if rid and weight > 0
                and rid not in cfg.disabled_rules and (cfg.rule_pool is None or rid in cfg.rule_pool)]
        entries = []
        for rid in pool:
            params = {**dict(next((p for r, p, _ in cfg.chaos_stub if r == rid), {})), **cfg.chaos_rule_params.get(rid, {})}
            mod = ctx.controller.registry.build_chaos_rule(rid, params)
            name = rule_name(ctx, rid)
            entries.append(Entry(name, _detail(name, describe_modifier(mod)) if mod else "", icon=rid))
        widgets.append(ListWidget(tuple(entries), title="Rules this dealer may use"))
    return tuple(widgets)


def _log(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    entries = ctx.controller.run_log.entries
    if variant == "tail":
        entries = entries[-3:]
    lines = tuple(LogLine(e.round, e.category, e.text) for e in entries)
    from chaos_blackjack.app.run_log import CATEGORIES

    return (Log(lines, categories=CATEGORIES, title="Run log"),)


def _run_stats(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    v, s = ctx.view, ctx.controller.run_log.stats
    widgets: list[Widget] = []
    if v.target_money > 0 and ctx.table is None:  # a table with its own goal shows it in its parts
        widgets.append(Progress("Bankroll", v.money, v.target_money, tone="gold", title="Goal"))
    widgets.append(Rows((
        Row("Round", str(v.round)),
        Row("Bankroll", str(v.money)),
        Row("Hands played", str(s["hands"])),
        Row("Won / lost / pushed", f"{s['wins']} / {s['losses']} / {s['pushes']}"),
        Row("Naturals", str(s["naturals"])),
        Row("Highest bankroll", str(max(s["peak"], v.money))),
        *((Row("Fees paid", str(s["fees"])),) if s["fees"] else ()),
    ), title="This run"))
    return tuple(widgets)


register_part("core.items", _items)
register_part("core.actions", _actions)
register_part("core.rules", _rules)
register_part("core.log", _log)
register_part("core.run_stats", _run_stats)

__all__ = ["PartContext", "Part", "VARIANTS", "build_part", "get_part", "register_part", "rule_name", "title"]
