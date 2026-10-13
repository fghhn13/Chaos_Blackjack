"""Parts — named pieces of table information, each turned into widgets.

A part reads the controller (never changes it) and returns widgets
(app/widgets.py) for a variant: `compact` (side columns), `full` (the run
panel) or `tail` (a few recent lines). Parts are composed per mode by a
layout (app/layout.py); the GUI draws whatever they return. A new table
mechanic adds parts — and maybe controller actions — but no GUI code.

    register_part("curse.meter", build_meter, available=lambda ctx: ctx.table is not None)

Core parts: core.items, core.rules, core.log, core.run_stats. J-54's are in
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


def title(entry_id: str) -> str:
    return entry_id.replace("_", " ").title()


def rule_name(ctx: PartContext, rule_id: str) -> str:
    from chaos_blackjack.ui.descriptions import RULE_NAMES

    factory = ctx.controller.registry._chaos_rules.get(rule_id)  # noqa: SLF001 - no public lookup yet
    return getattr(factory, "codex_name", None) or RULE_NAMES.get(rule_id) or title(rule_id)


# ------------------------------------------------------------------ core


def _items(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    v = ctx.view
    usable = v.can(Action.USE_ITEM)
    help_of = {i.id: i.description or ITEM_HELP.get(i.id, "") for i in v.items}
    if variant == "compact":
        slots = tuple(Slot(i.id, i.count, f"{title(i.id)}: {help_of[i.id]}", hotkey=str(n + 1) if n < 9 else "",
                           act=Act("use_item", i.id, usable)) for n, i in enumerate(v.items) if i.count > 0)
        return (Slots(slots, title="Items", empty="No items"),)
    entries = tuple(Entry(title(i.id), help_of[i.id], icon=i.id, badge=f"×{i.count}",
                          act=Act("use_item", i.id, usable)) for i in v.items if i.count > 0)
    note = "Use items on your turn." if not usable else "Click an item to use it."
    return (ListWidget(entries, title="Items", empty=f"No items. {note}"),)


def _detail(name: str, text: str) -> str:
    """A rule description without the "<name>: " prefix rule descriptions start with."""
    head, sep, rest = text.partition(": ")
    return rest if sep and head.lower() == name.lower() else text


def _rules(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    v = ctx.view
    active = tuple(Entry(rule_name(ctx, r.id), _detail(rule_name(ctx, r.id), r.description), icon=r.id, tone="chaos",
                         tooltip=r.description) for r in v.active_rules)
    if variant == "compact":
        empty = "None yet" if v.chaos_enabled else "Chaos off"
        return (ListWidget(active, title="Active rules", empty=empty, compact=len(active) > 1),)
    widgets: list[Widget] = [ListWidget(active, title="Active this round",
                                        empty="No rule this round." if v.chaos_enabled else "This table never bends the rules.")]
    cfg = ctx.controller.config
    if cfg.enable_chaos:
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
register_part("core.rules", _rules)
register_part("core.log", _log)
register_part("core.run_stats", _run_stats)

__all__ = ["PartContext", "Part", "VARIANTS", "build_part", "get_part", "register_part", "rule_name", "title"]
