"""Deck operations — the one engine behind J-54's rules, contracts and entropy.

An operation is data (a JSON object in the balance profile):

    {"when": "now", "select": "low", "op": "remove", "count": 6}

* `when`   — `now` (when it is announced) or `round_end` (after the hand settles)
* `select` — which cards: `rank:<R>`, `random_rank`, `low` (2-6), `high`
  (10-A), `any`, `drawn` (both hands this round), `player_hand`,
  `dealer_up`, `removed` (cards deleted earlier in the run)
* `op`     — `add`, `remove`, `copy`, `move_top`, `move_bottom`, `return`
* `count`  — a number, or `"all"`

A new rule or contract is a row with these four fields (and a name), no code.
`now` operations also change the cards left in this round's deck; between
rounds they change the deck for the next shuffle. Moves only reorder this
round's deck. Deletions never take the deck below its minimum size, and no
operation ever touches a Joker.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.core.game_state import Card, Rank

JOKER = "JK"
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("♠", "♥", "♦", "♣")
LOW_RANKS = ("2", "3", "4", "5", "6")
HIGH_RANKS = ("10", "J", "Q", "K", "A")

WHEN = ("now", "round_end")
OPS = ("add", "remove", "copy", "move_top", "move_bottom", "return")
# Which selections each operation accepts.
_SELECTS: dict[str, tuple[str, ...]] = {
    "add": ("rank", "random_rank", "low", "high", "any"),
    "remove": ("rank", "random_rank", "low", "high", "any", "drawn"),
    "copy": ("drawn", "player_hand", "dealer_up"),
    "move_top": ("rank", "random_rank", "low", "high", "any"),
    "move_bottom": ("rank", "random_rank", "low", "high", "any"),
    "return": ("removed",),
}


def is_joker(card: Card) -> bool:
    return str(card.rank).upper() == JOKER


def _kind(select: str) -> str:
    return "rank" if select.startswith("rank:") else select


@dataclass(frozen=True)
class DeckOp:
    op: str
    select: str
    count: int | None = 1      # None = all
    when: str = "now"

    @staticmethod
    def from_params(params: dict[str, Any]) -> "DeckOp":
        op, select = str(params.get("op", "")), str(params.get("select", "any"))
        when = str(params.get("when", "now"))
        raw = params.get("count", 1)
        count = None if raw == "all" else int(raw)
        if op not in OPS:
            raise ValueError(f"Unknown deck operation {op!r}; expected one of {', '.join(OPS)}")
        if when not in WHEN:
            raise ValueError(f"Unknown time {when!r}; expected one of {', '.join(WHEN)}")
        if _kind(select) not in _SELECTS[op]:
            raise ValueError(f"{op} cannot select {select!r}; it takes {', '.join(_SELECTS[op])}")
        if _kind(select) == "rank" and select[5:].upper() not in RANKS:
            raise ValueError(f"Unknown rank in {select!r}")
        if op == "add" and count is None:
            raise ValueError("add needs a number of cards")
        if op.startswith("move") and when != "now":
            raise ValueError("moves reorder this round's deck, so they happen now")
        if count is not None and count < 1:
            raise ValueError("count must be at least 1")
        return DeckOp(op, select, count, when)

    def describe(self, rank: str | None = None) -> str:
        """Plain English, e.g. "delete 6 low cards (2-6) from the deck"."""
        n, kind = self.count, _kind(self.select)
        if kind == "rank":
            rank = self.select[5:].upper()
        noun = _noun(kind, n != 1, rank)
        if kind in ("player_hand", "dealer_up"):
            some = noun
        elif n is None:
            some = "all cards" if kind == "any" else f"all {noun}"
        else:
            some = f"{n} {noun}"
        if self.op == "add":
            text = f"add {some} to the deck"
        elif self.op == "remove":
            text = f"delete {some} from the deck"
        elif self.op == "copy":
            text = f"copy {some} into the deck" + ("" if n is None else f" (up to {n})")
        elif self.op == "return":
            text = f"shuffle {some} back into the deck"
        else:
            text = f"move {some} to the {'top' if self.op == 'move_top' else 'bottom'} of this round's deck"
        return ("after the hand, " if self.when == "round_end" else "") + text


def _noun(kind: str, plural: bool, rank: str | None) -> str:
    cards = "cards" if plural else "card"
    if kind == "rank" or (kind == "random_rank" and rank):
        return f"{cards} of rank {rank}"
    return {
        "random_rank": f"{cards} of one random rank",
        "low": f"low {cards} (2-6)",
        "high": f"high {cards} (10-A)",
        "any": f"random {cards}",
        "drawn": f"{cards} drawn this round",
        "player_hand": "your hand",
        "dealer_up": "the dealer's face-up card",
        "removed": f"removed {cards}",
    }[kind]


@dataclass
class DeckContext:
    """What an operation may touch. `deck` is this round's remaining deck
    (None between rounds); `cards` is every card of the run's deck."""

    cards: list[Card]
    removed: list[Card]
    rng: Callable[[], random.Random]
    min_deck: int
    deck: list[Card] | None = None
    player: tuple[Card, ...] = ()
    dealer: tuple[Card, ...] = ()


@dataclass
class OpResult:
    cards: list[Card] = field(default_factory=list)   # the cards added, deleted, copied, moved or returned
    rank: str | None = None                            # the rank drawn for `random_rank`

    def summary(self, op: DeckOp) -> str:
        names = ", ".join(str(c.rank) for c in self.cards) if self.cards else "nothing"
        verb = {"add": "added", "remove": "deleted", "copy": "copied", "return": "returned",
                "move_top": "moved to the top", "move_bottom": "moved to the bottom"}[op.op]
        if op.op.startswith("move"):
            return f"{len(self.cards)} card{'s' if len(self.cards) != 1 else ''} {verb}"
        return f"{verb} {names}"


def _matches(card: Card, kind: str, rank: str | None) -> bool:
    r = str(card.rank)
    if is_joker(card):
        return False
    if kind in ("rank", "random_rank"):
        return r == rank
    if kind == "low":
        return r in LOW_RANKS
    if kind == "high":
        return r in HIGH_RANKS
    return True


def apply(op: DeckOp, ctx: DeckContext) -> OpResult:
    """Apply `op`, changing `ctx.cards`, `ctx.removed` and `ctx.deck` in place."""
    kind = _kind(op.select)
    rank = op.select[5:].upper() if kind == "rank" else None
    live = ctx.deck is not None and op.when == "now"
    if op.op == "add":
        rng = ctx.rng()
        if kind == "random_rank":
            rank = rng.choice(RANKS)
        pool = {"low": LOW_RANKS, "high": HIGH_RANKS}.get(kind, RANKS)
        new = [Card(Rank(rank or rng.choice(pool)), rng.choice(SUITS)) for _ in range(op.count or 0)]
        _insert(ctx, new, live)
        return OpResult(new, rank if kind == "random_rank" else None)
    if op.op == "copy":
        source = {"player_hand": ctx.player, "dealer_up": ctx.dealer[:1],
                  "drawn": (*ctx.player, *ctx.dealer)}[kind]
        new = [Card(c.rank, c.suit) for c in source if not is_joker(c)][:op.count]
        _insert(ctx, new, live)
        return OpResult(new)
    if op.op == "return":
        rng = ctx.rng()
        picked = rng.sample(ctx.removed, len(ctx.removed) if op.count is None else min(op.count, len(ctx.removed)))
        for card in picked:
            ctx.removed.remove(card)
        _insert(ctx, picked, live)
        return OpResult(picked)
    # remove / move: pick existing cards
    if kind == "drawn":
        pool = [c for c in (*ctx.player, *ctx.dealer) if not is_joker(c)]
    else:
        source = ctx.deck if live else ctx.cards
        if source is None:  # a move with no round in play does nothing
            return OpResult()
        if kind == "random_rank":
            present = sorted({str(c.rank) for c in source if not is_joker(c)}, key=RANKS.index)
            rank = ctx.rng().choice(present) if present else None
        pool = [c for c in source if _matches(c, kind, rank)]
    rng = ctx.rng()
    picked = rng.sample(pool, len(pool) if op.count is None else min(op.count, len(pool)))
    resolved = rank if kind == "random_rank" else None
    if op.op == "remove":
        gone = []
        for card in picked:
            if len(ctx.cards) <= ctx.min_deck or card not in ctx.cards:
                continue
            ctx.cards.remove(card)
            ctx.removed.append(card)
            if live and kind != "drawn" and ctx.deck is not None:
                ctx.deck.remove(card)
            gone.append(card)
        return OpResult(gone, resolved)
    # moves: this round's deck only
    assert ctx.deck is not None
    for card in picked:
        ctx.deck.remove(card)
    if op.op == "move_top":
        ctx.deck[0:0] = picked
    else:
        ctx.deck.extend(picked)
    return OpResult(picked, resolved)


def _insert(ctx: DeckContext, new: list[Card], live: bool) -> None:
    ctx.cards.extend(new)
    if live and ctx.deck is not None:
        rng = ctx.rng()
        for card in new:
            ctx.deck.insert(rng.randint(0, len(ctx.deck)), card)
