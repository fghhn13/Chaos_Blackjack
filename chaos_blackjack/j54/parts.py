"""J-54's table parts (app/parts.py): heat map, meter, badges, operations, goal, program.

They read only the view: its public snapshot (`view.table_public`,
public.py), the deck counts and the moves (`view.moves`) that enable each
clickable element, never the table object. The J-54 layout in
chaos_blackjack/modes places them (docs/design/TABLE_UI.md). The heat map and
the meter show direction and advice, never a plan: a green rank is one whose
removal helps you, a red one should stay; the meter's bands suggest a stake.
"""

from __future__ import annotations

from chaos_blackjack.app.parts import PartContext, register_part
from chaos_blackjack.app.widgets import (
    Act, Badge, Badges, Bar, Bars, Entry, ListWidget, Mark, Progress, Row, Rows, Widget,
)
from chaos_blackjack.j54.deck_ops import RANKS
from chaos_blackjack.j54.public import J54Snapshot, heat_text
from chaos_blackjack.j54.table import COLOURS, CUT, HOT_PURGE, IN_DECK, RELEASE, group_label

_JOKER_TONE = {"sealed": "muted", "in the deck": "gold", "captured": "good"}
_CAMP_TONE = {"classic": "", "anti": "warn", "loner": "chaos"}
_SUITS = {"r": "hearts, diamonds", "b": "spades, clubs"}  # words: the heading font has no suit glyphs
_FLOOR = 0.5   # pp: below this the strongest heat is still drawn faintly (a flat deck looks flat)


def _snapshot(ctx: PartContext) -> J54Snapshot | None:
    data = ctx.view.table_public
    return data if isinstance(data, J54Snapshot) else None


def _available(ctx: PartContext) -> bool:
    return _snapshot(ctx) is not None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _tone(pp: float) -> str:
    """Green when removing helps you, red when the cards should stay."""
    return "good" if pp > 0 else "bad" if pp < 0 else ""


def _shade(pp: float, scale: float) -> float:
    return min(1.0, abs(pp) / max(scale, _FLOOR))


def _cut_act(ctx: PartContext, group: str) -> Act | None:
    move = ctx.view.move(CUT, group)
    return Act(CUT, group, move.enabled) if move is not None and move.enabled else None


# ------------------------------------------------------------------ deck: the heat map


def _rank_tip(d: J54Snapshot, rank: str) -> str:
    groups = d.groups or {}
    parts = [f"{COLOURS[c]} {d.heat[f'{rank}{c}']:+.1f} pp ({groups.get(f'{rank}{c}', 0)} left)"
             for c in COLOURS if f"{rank}{c}" in d.heat]
    if not parts:
        return f"{rank}: none left in the deck."
    pp = d.rank_heat(rank)
    advice = "removing it helps you" if pp > 0 else "it should stay" if pp < 0 else "no effect"
    return f"{rank}: {pp:+.1f} pp, {advice}. " + "; ".join(parts) + "."


def _deck(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    d, v = _snapshot(ctx), ctx.view
    counts = dict(v.deck_counts)
    scale = max((abs(d.rank_heat(r)) for r in RANKS), default=0.0)
    cut = ctx.view.move(CUT, "")
    cut_act = Act(CUT, "", True) if cut is not None and cut.enabled else None
    if variant == "compact":
        # One bar per rank, coloured by heat; a click asks which group to cut (with each group's heat).
        bars = tuple(Bar(r, counts.get(r, 0), _tone(d.rank_heat(r)), _shade(d.rank_heat(r), scale),
                         _rank_tip(d, r) + (" Click to cut." if cut_act else ""), cut_act)
                     for r in RANKS)
        left = v.deck_count if v.player_cards else d.deck_size
        return (Bars(bars, compact=True, note=f"{left} / {d.deck_size}", act=Act("gui:panel", "deck"),
                     title="Deck heat"),)
    groups = d.groups or {}
    gscale = max((abs(pp) for pp in d.heat.values()), default=0.0)
    widgets: list[Widget] = []
    for c, colour in COLOURS.items():  # one strip per colour: each bar cuts its own group
        bars = tuple(Bar(r, groups.get(f"{r}{c}", 0), _tone(d.heat.get(f"{r}{c}", 0.0)),
                         _shade(d.heat.get(f"{r}{c}", 0.0), gscale),
                         f"{group_label(f'{r}{c}')}: {groups.get(f'{r}{c}', 0)} left, "
                         f"{heat_text(d.heat[f'{r}{c}'])}" if f"{r}{c}" in d.heat
                         else f"{group_label(f'{r}{c}')}: none left.",
                         _cut_act(ctx, f"{r}{c}"))
                     for r in RANKS)
        note = ("Green: removing a card helps you. Red: keep it. Click a bar to cut it."
                if c == "r" else "Heat in percentage points of your win chance, per card removed.")
        widgets.append(Bars(bars, title=f"{colour.title()} cards ({_SUITS[c]})", note=note, baseline=2,
                            baseline_label="Standard deck"))
    entries = tuple(Entry(r, _rank_tip(d, r).split(". ", 1)[-1], badge=f"{d.rank_heat(r):+.1f} pp",
                          tone=_tone(d.rank_heat(r)))
                    for r in sorted((r for r in RANKS if counts.get(r)), key=lambda r: -d.rank_heat(r)))
    widgets.append(ListWidget(entries, title="Heat by rank (both colours)", empty="The deck is empty."))
    rows = [Row("Whole deck", _plural(d.deck_size, "card"))]
    if v.player_cards:
        rows.append(Row("Left this round", _plural(v.deck_count, "card")))
    rows.append(Row("Joker", d.joker, _JOKER_TONE.get(d.joker, "")))
    rows.append(Row("Removed so far", _plural(d.removed, "card")))
    widgets.append(Rows(tuple(rows)))
    widgets.append(_removed_pile(d))
    return tuple(widgets)


_SUIT_WORDS = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}


def _removed_pile(d: J54Snapshot) -> Widget:
    # "5h" chips (the UI fonts have no suit glyphs), red for hearts and diamonds; the tooltip spells it out.
    entries = tuple(Entry(f"{card[:-1]}{_SUIT_WORDS[card[-1]][0]}", tone="bad" if card[-1] in "♥♦" else "",
                          tooltip=f"{card[:-1]} of {_SUIT_WORDS[card[-1]]}")
                    for card in d.removed_cards)
    return ListWidget(entries, title="Removed pile", empty="Nothing removed yet.", compact=True)


# ------------------------------------------------------------------ the meter


def _meter(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """The win chance as a gauge with the betting bands marked, and the band's suggested stake."""
    d = _snapshot(ctx)
    band = d.band
    stake = (f"{band['suggested']} ({band['stake_pct']}% of your chips)" if band["stake_pct"]
             else f"{band['suggested']} (the minimum)")
    marks = tuple(Mark(b["low"] * 10, f"{b['low']}%") for b in d.bands)
    tip = (f"Win chance of one hand from this deck under the condition and your firmware: {d.bar:.1%}. "
           f"Bands: " + ", ".join(f"from {b['low']}% stake {b['stake_pct']}%" for b in d.bands)
           + f"; below, the minimum. Suggested stake now: {stake}. Advice only; the bet range is unchanged.")
    tone = "good" if band["stake_pct"] else "muted"
    gauge = Progress("Win chance", round(d.bar * 1000), 1000, tone=tone, text=f"{d.bar:.1%}", marks=marks,
                     tooltip=tip, title="" if variant == "compact" else "Meter")
    # A guided player's one-time line, the first time the meter reaches its second band (j54/onboarding.py).
    hint = ((ListWidget((Entry("Band two reached", d.hint, tone="gold",
                               tooltip=f"J-54: {d.hint} Advice only; the bet range is unchanged."),)),)
            if d.hint else ())
    if variant == "compact":
        return (gauge, *hint)
    rows = [Row("Expected result", f"{d.ev:+.2f} bets per hand", "good" if d.ev > 0 else "bad" if d.ev < 0 else ""),
            Row("Suggested stake", stake, "gold" if band["stake_pct"] else "")]
    if d.joker == IN_DECK:
        rows.append(Row("Capture chance", f"{d.capture:.1%} per hand", "gold"))
    return (gauge, *hint, Rows(tuple(rows)))


# ------------------------------------------------------------------ badges and operations


def _badges(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    d = _snapshot(ctx)
    items = [Badge("j54_compute", f"{d.compute}/{d.compute_cap}",
                   f"Compute {d.compute}/{d.compute_cap}: it pays for cuts, purges and the Joker's release.", "gold")]
    m = d.condition
    if m is not None:
        items.append(Badge(m["id"], str(m["rounds_left"]),
                           f"Condition: {m['name']}. {m['text']}. {_plural(m['rounds_left'], 'round')} left "
                           f"({m['camp']} camp).", _CAMP_TONE.get(m["camp"], "")))
    if d.announcement:
        items.append(Badge("j54_next", "Next", d.announcement, "warn"))
    items.append(Badge(f"j54_joker_{d.joker.replace(' ', '_')}", d.joker.split()[-1].title(),
                       f"Joker: {d.joker}." + (f" Capture chance {d.capture:.1%} per hand." if d.joker == IN_DECK
                                               else ""), _JOKER_TONE.get(d.joker, "")))
    if d.firmware is not None:
        items.append(Badge(d.firmware["id"], d.firmware["name"].split()[0],
                           f"{d.firmware['name']}: {d.firmware['text']}"))
    if d.bounty is not None:
        items.append(Badge("j54_bounty", d.bounty["rank"],
                           f"Bounty: {d.bounty['chips']} chips for every {d.bounty['rank']} in your hand at "
                           "settlement, win or lose.", "gold"))
    return (Badges(tuple(items), title="Experiment"),)


_OPS = ((CUT, "j54_cut", "Cut"), (HOT_PURGE, "j54_hot_purge", "Purge"), (RELEASE, "j54_release", "Release"))


def _ops(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """Cut, Hot Purge and Release while betting: enabled by their moves, with the reason when not."""
    items = []
    for action, icon, text in _OPS:
        move = ctx.view.move(action, "")
        if move is None:
            continue
        tip = move.label + (". " + move.reason if not move.enabled and move.reason else
                            ": asks which group, with its heat." if action == CUT else
                            ": removes cards of one of the hottest ranks." if action == HOT_PURGE else
                            ": puts the sealed Joker into the deck for the rest of the run.")
        items.append(Badge(icon, text, tip, "" if move.enabled else "muted", Act(action, "", move.enabled)))
    return (Badges(tuple(items), title="Operations"),) if items else ()


# ------------------------------------------------------------------ run panel


def _goal(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    d, v = _snapshot(ctx), ctx.view
    counts = v.round >= d.target_from_round
    widgets: list[Widget] = [
        Progress("Chips", v.money, d.target, tone="gold" if counts else "", title="Goal",
                 text=f"{v.money} / {d.target}",
                 tooltip=f"Reach {d.target} chips at a settlement from round {d.target_from_round}."),
        Rows((Row("Round", f"{d.round} / {d.rounds}"),
              Row("The target counts", "now" if counts else f"from round {d.target_from_round}",
                  "good" if counts else "muted"),
              Row("Or capture", "hold the Joker when a hand you do not lose settles", _JOKER_TONE.get(d.joker, "")),
              Row("Joker", d.joker, _JOKER_TONE.get(d.joker, "")))),
    ]
    return tuple(widgets)


def _program(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    """The program as far as it is public (all of it when the profile reads it out), the firmware, the pile."""
    d = _snapshot(ctx)
    current = len(d.seen) - 1
    shown = d.program if d.program else d.seen
    entries = [Entry(s["name"], f"Rounds {s['start']}-{s['end']} · {s['camp']} camp",
                     icon=s["id"], badge="Now" if i == current else "Done" if i < current else "",
                     tone="gold" if i == current else "muted" if i < current else "")
               for i, s in enumerate(shown)]
    if not d.program and d.announcement:
        entries.append(Entry("Next condition", d.announcement, icon="j54_next", tone="warn"))
    fw = d.firmware
    return (ListWidget(tuple(entries), title="Program", empty="The program starts with round 1."),
            ListWidget((Entry(fw["name"], fw["text"], icon=fw["id"], badge="Firmware"),) if fw else (),
                       title="Firmware", empty="No firmware: your cards count as printed."),
            _removed_pile(d))


for _name, _builder in (("deck", _deck), ("meter", _meter), ("badges", _badges), ("ops", _ops),
                        ("goal", _goal), ("program", _program)):
    register_part("j54." + _name, _builder, available=_available)
