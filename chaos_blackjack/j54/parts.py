"""J-54's table parts (app/parts.py): deck, badges, contracts, goal.

They only read the table (j54/table.py) and the view; the J-54 layout in
chaos_blackjack/modes places them. Interim for the v2 table core: package C of
docs/design/J54_V2_SPEC.md rewrites these parts (heat map, meter, program) and
drops the Contracts tab.
"""

from __future__ import annotations

from collections import Counter

from chaos_blackjack.app.parts import PartContext, register_part
from chaos_blackjack.app.widgets import (
    Act, Badge, Badges, Bar, Bars, Entry, ListWidget, Progress, Row, Rows, Widget,
)
from chaos_blackjack.j54.deck_ops import LOW_RANKS, RANKS
from chaos_blackjack.j54.table import standard_cards

_JOKER_TONE = {"sealed": "muted", "in the deck": "gold", "captured": "good"}


def _is_j54(ctx: PartContext) -> bool:
    return ctx.table is not None and getattr(ctx.table, "id", "") == "j54"


def _deck(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    t, v = ctx.table, ctx.view
    bars = tuple(Bar(rank, n, "bad" if rank in LOW_RANKS else "") for rank, n in t.deck_counts())
    left = v.deck_count if v.player_cards else t.deck_size
    if variant == "compact":
        return (Bars(bars, compact=True, note=f"{left} / {t.deck_size}", act=Act("gui:panel", "deck"),
                     title="Deck"),)
    rows = [Row("Whole deck", f"{t.deck_size} cards")]
    if v.player_cards:
        rows.append(Row("Left this round", f"{v.deck_count} cards"))
    rows.append(Row("Joker", t.joker, _JOKER_TONE.get(t.joker, "")))
    rows.append(Row("Removed so far", f"{len(t.removed)} cards"))
    # Against a standard 52-card deck: fewer in red, more in green.
    standard = Counter(str(c.rank) for c in standard_cards())
    counts = dict(t.deck_counts())
    diff = tuple(Entry(rank, badge=f"{counts[rank] - standard[rank]:+d}",
                       tone="good" if counts[rank] > standard[rank] else "bad",
                       tooltip=f"{rank}: {counts[rank]} in the deck, {standard[rank]} in a standard deck")
                 for rank in RANKS if counts[rank] != standard[rank])
    plain = tuple(Bar(b.label, b.value) for b in bars)
    return (Bars(plain, title="Deck by rank", note="Every card of the run's deck; each round reshuffles them all.",
                 baseline=standard[RANKS[0]], baseline_label="Standard deck"),
            ListWidget(diff, title="Compared with a standard deck", empty="Same as a standard deck.", compact=True),
            Rows(tuple(rows)))


def _badges(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    t = ctx.table
    items = [Badge("j54_compute", f"{t.compute}/{t.compute_cap}", f"Compute {t.compute}/{t.compute_cap}.", "gold")]
    m = t.condition()
    if m is not None:
        note = f" {t.announcement}" if t.announcement else ""
        items.append(Badge(m.id, str(t.rounds_left()), f"{m.name}: {m.text}.{note}"))
    items.append(Badge(f"j54_joker_{t.joker.replace(' ', '_')}", t.joker.split()[-1].title(), f"Joker: {t.joker}.",
                       _JOKER_TONE.get(t.joker, "")))
    if t.firmware is not None:
        items.append(Badge(t.firmware.id, t.firmware.name.split()[0], f"{t.firmware.name}: {t.firmware.text}"))
    return (Badges(tuple(items)),)


def _contracts(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    return (ListWidget((), title="Contracts", empty="J-54 signs no contracts at this table."),)


def _goal(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    t, run = ctx.table, ctx.controller.run
    widgets: list[Widget] = [Progress("Bankroll", run.money, run.target_money, tone="gold", title="Goal")]
    program = t.public().program
    if program:  # the whole schedule is public only when the profile says so
        widgets.append(Rows(tuple(Row(f"Rounds {s['start']}-{s['end']}", s["name"],
                                      "gold" if i == t.segment else "muted" if i < t.segment else "")
                                  for i, s in enumerate(program)), title="Program"))
    return tuple(widgets)


register_part("j54.deck", _deck, available=_is_j54)
register_part("j54.badges", _badges, available=_is_j54)
register_part("j54.contracts", _contracts, available=_is_j54)
register_part("j54.goal", _goal, available=_is_j54)
