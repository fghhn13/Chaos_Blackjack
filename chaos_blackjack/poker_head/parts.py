"""Poker Head's table parts (app/parts.py): build, wallet, positions, prepared effects.

They read only the view and its public snapshot (`view.table_public`,
public.py), never the table object. Choices are drawn by the GUI's generic
choice dialog and table actions by the core `core.actions` part.
"""

from __future__ import annotations

from chaos_blackjack.app.parts import PartContext, register_part
from chaos_blackjack.app.widgets import Act, Entry, ListWidget, Progress, Row, Rows, Slot, Slots, Widget
from chaos_blackjack.poker_head.public import PokerHeadPublic
from chaos_blackjack.poker_head.table import DISCARD


def _snapshot(ctx: PartContext) -> PokerHeadPublic | None:
    data = ctx.view.table_public
    return data if isinstance(data, PokerHeadPublic) else None


def _available(ctx: PartContext) -> bool:
    return _snapshot(ctx) is not None


def _status(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """The build at a glance: core and permanents as icons (details in tooltips), then the numbers.
    The goal (net assets) is the bar under the bankroll in the top bar."""
    d = _snapshot(ctx)
    slots = []
    if d.core:
        slots.append(Slot(d.core.id, tooltip=f"Core: {d.core.name}: {d.core.description}", frame="special",
                          act=Act("gui:panel", "build")))
    slots += [Slot(x.id, tooltip=f"{x.name}: {x.description}", frame="permanent", act=Act("gui:panel", "build"))
              for x in d.equipped]
    core = d.core.name if d.core else "No core" if d.no_core else "Not chosen"
    empty = "No core yet" if not d.no_core else "No core this run"
    widgets: list[Widget] = [Slots(tuple(slots), title=f"Build {len(d.equipped)}/{d.slots}", empty=empty, columns=4)]
    if variant != "compact":
        widgets.insert(0, Progress("Net assets", max(0, d.net_assets), d.target, tone="gold"))
        widgets.append(Rows((Row("Core", core), Row("Minimum bet", str(d.min_bet))), title="Table"))
    else:
        widgets.append(Rows((Row("Minimum bet", str(d.min_bet)),)))
    widgets.append(Rows((Row("Dealer", f"{d.dealer_stage} ({d.dealer_slots} rule{'s' if d.dealer_slots != 1 else ''})"),)))
    return tuple(widgets)


def _loadout(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """Core and permanents; a permanent can be discarded before betting (it may be offered again)."""
    d = _snapshot(ctx)
    entries = []
    if d.core:
        entries.append(Entry(d.core.name, d.core.description, icon=d.core.id, badge="Core", tone="gold", frame="special"))
    for x in d.equipped:
        move = ctx.view.move(DISCARD, x.id)
        entries.append(Entry(x.name, x.description + ("  ·  Click to discard." if move else ""), icon=x.id,
                             badge="Permanent", frame="permanent", act=Act(DISCARD, x.id, move.enabled) if move else None,
                             tooltip=f"Discard {x.name}: frees its slot; it may be offered again." if move else ""))
    return (ListWidget(tuple(entries), title=f"Build ({len(d.equipped)}/{d.slots} slots)",
                       empty="Buy permanents in the shop."),)


def _wallet(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    d = _snapshot(ctx)
    rows = (Row("Cash", str(d.cash)), Row("Invested (at cost)", str(d.invested)),
            Row("Owed on loans", str(d.debt), "bad" if d.debt else ""),
            Row("Net assets", f"{d.net_assets}/{d.target}", "gold"))
    return (Rows(rows, title="Wallet"),)


def _finance(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    d = _snapshot(ctx)
    entries = []
    for p in d.positions:
        money = f"repay {p.debt}" if p.debt else f"principal {p.principal}"
        rounds = f"{p.remaining} round{'s' if p.remaining != 1 else ''} left"
        wins = f", {p.wins} win{'s' if p.wins != 1 else ''}" if p.id == "ph_bond" else ""
        entries.append(Entry(p.name, f"{money.capitalize()}; {rounds}{wins}.", icon=p.id, frame="special"))
    return (ListWidget(tuple(entries), title="Financial products", empty="No open positions."),)


def _preparations(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    d = _snapshot(ctx)
    entries = [Entry(x.name, x.description, icon=x.id, badge="This round", frame="consumable") for x in d.preparations]
    if d.forecast:
        note = " The deck has changed since." if d.forecast_changed else ""
        entries.append(Entry("Fate Forecast", "Your opening cards: " + " ".join(d.forecast) + "." + note,
                             icon="ph_oracle", tone="warn" if d.forecast_changed else ""))
    if d.next_rank:
        entries.append(Entry("Next rank", d.next_rank, icon="ph_peek"))
    if d.claim_refund:
        entries.append(Entry("Recovery Receipt", f"Win round {d.claim_round} to recover {d.claim_refund} chips.",
                             icon="ph_claim"))
    if d.ace_armed:
        entries.append(Entry("Comeback Ace", "Your next first opening card will be an ace.", icon="ph_ace"))
    return (ListWidget(tuple(entries), title="Prepared effects", empty="No prepared effects."),)


for _name, _builder in (("status", _status), ("loadout", _loadout), ("wallet", _wallet),
                        ("finance", _finance), ("preparations", _preparations)):
    register_part("poker_head." + _name, _builder, available=_available)
