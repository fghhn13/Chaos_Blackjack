"""J-54's table parts (app/parts.py): deck, badges, contracts, goal.

They only read the table (j54/table.py) and the view; the J-54 layout in
chaos_blackjack/modes places them.
"""

from __future__ import annotations

from collections import Counter

from chaos_blackjack.app.parts import PartContext, register_part
from chaos_blackjack.app.widgets import (
    Act, Badge, Badges, Bar, Bars, Entry, ListWidget, Progress, Row, Rows, Widget,
)
from chaos_blackjack.j54.contracts import CONTRACTS, contract_spec, describe
from chaos_blackjack.j54.deck_ops import LOW_RANKS, RANKS
from chaos_blackjack.j54.table import standard_cards

_TRIGGER_TAG = {"now": "now", "win": "on win", "loss": "on loss", "natural": "on natural"}
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
    if t.protocol == "capture":
        rows.append(Row("Joker", t.joker_state(), _JOKER_TONE.get(t.joker_state(), "")))
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
    t, run = ctx.table, ctx.controller.run
    items: list[Badge] = []
    if t.protocol == "capture":
        state = t.joker_state()
        items.append(Badge(f"j54_joker_{state.replace(' ', '_')}", state.split()[-1].title(),
                           f"Joker: {state}. Draw it yourself to win.", _JOKER_TONE.get(state, "")))
    else:
        items.append(Badge("j54_goal", f"{run.money}/{t.capital_target}", f"Capital: reach {t.capital_target} chips.",
                           "gold"))
    fee = t.fee(run.round)
    step = int(t.settings["fee_step_rounds"])
    to_next = step - (max(1, run.round) - 1) % step
    nxt = t.fee(run.round + to_next)
    items.append(Badge("j54_fee", str(fee), f"Compute fee {fee} per round; {nxt} in {to_next} round"
                                            f"{'s' if to_next != 1 else ''}.", "warn" if fee else ""))
    for item_id in t.pending:
        trigger = contract_spec(item_id, t.config.item_params).trigger
        items.append(Badge(item_id, _TRIGGER_TAG[trigger], f"{CONTRACTS[item_id].name}: {describe(item_id, t.config.item_params)}",
                           act=Act("gui:panel", "contracts")))
    if t.freeze:
        items.append(Badge("j54_freeze", str(t.freeze), f"Freeze: J-54 adds no cards for {t.freeze} more rounds.",
                           "good"))
    return (Badges(tuple(items)),)


def _contracts(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    t = ctx.table
    params = t.config.item_params
    pending = tuple(Entry(CONTRACTS[c].name, describe(c, params), icon=c,
                          badge=_TRIGGER_TAG[contract_spec(c, params).trigger]) for c in t.pending)
    signed = tuple(Entry(CONTRACTS[c].name, f"Round {r}", icon=c) for r, c in reversed(t.signed))
    return (ListWidget(pending, title="Waiting to trigger", empty="No contract is waiting."),
            ListWidget(signed, title="Signed this run", empty="No contract signed yet."))


def _goal(ctx: PartContext, variant: str) -> tuple[Widget, ...]:
    t, run = ctx.table, ctx.controller.run
    from chaos_blackjack.j54.table import PROTOCOLS

    widgets: list[Widget] = []
    if t.protocol == "capital":
        widgets.append(Progress("Bankroll", run.money, t.capital_target, tone="gold", title="Protocol: Capital"))
    else:
        widgets.append(Rows((Row("Protocol", PROTOCOLS[t.protocol]),
                             Row("Joker", t.joker_state(), _JOKER_TONE.get(t.joker_state(), "")),
                             Row("Experiment", "started" if t.experiment else "not started")), title="Protocol"))
    step = int(t.settings["fee_step_rounds"])
    current = (max(1, run.round) - 1) // step
    rows = tuple(Row(f"Rounds {i * step + 1}-{(i + 1) * step}",
                     f"{t.fee(i * step + 1)} chip{'s' if t.fee(i * step + 1) != 1 else ''}",
                     "gold" if i == current else "muted" if i < current else "")
                 for i in range(max(current + 3, 5)))
    widgets.append(Rows(rows, title="Compute fee"))
    return tuple(widgets)


register_part("j54.deck", _deck, available=_is_j54)
register_part("j54.badges", _badges, available=_is_j54)
register_part("j54.contracts", _contracts, available=_is_j54)
register_part("j54.goal", _goal, available=_is_j54)
