"""Poker Head's environment rules: what the dealer changes about the table, as data.

Design: docs/design/POKER_HEAD_CHAOS_RULES_AND_AGENT.zh-CN.md. A rule is a
type plus explicit parameters (whose cards, which cards, what number, how
long); its English text, its signature and its effects all come from that
data, so a player always reads the actual numbers and targets.

Types (one of each at most; §4.2):

=============  =====================================================  ==============
type           effect                                                 duration
=============  =====================================================  ==============
fixed          a card group counts as a fixed value                   persistent
shift          card groups count more or less (one or two groups)     persistent
bust           an actor's base bust limit                             timed
tie            who wins an ordinary tie                               persistent
bust_outcome   what a bust leads to                                   timed
profit_cap     the round's profit is capped                           timed
item_ban       the next consumable only lifts the ban                 timed
markup         goods cost more                                        timed
hidden         your second opening card is face down                  timed
=============  =====================================================  ==============

This module holds the rule model, its text and the hand-value hooks. The
director (who adds or replaces rules) is separate; the money, item, shop and
display rules act through the table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any, Iterable

from chaos_blackjack.core.game_state import Card

ACTORS = ("player", "dealer", "both")
TYPES = ("fixed", "shift", "bust", "tie", "bust_outcome", "profit_cap", "item_ban", "markup", "hidden")
HAND_TYPES = ("fixed", "shift", "bust", "tie", "bust_outcome")

RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
NUMBER_RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10")
ODD = ("3", "5", "7", "9")
EVEN = ("2", "4", "6", "8", "10")
SUITS = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
RED = ("♥", "♦")
BLACK = ("♠", "♣")
BASE_VALUES = {**{r: int(r) for r in NUMBER_RANKS}, "J": 10, "Q": 10, "K": 10, "A": 11}


# --- card groups ---------------------------------------------------------------------


@dataclass(frozen=True)
class CardGroup:
    """Which cards a rule touches. Odd and even use the printed rank, never a changed value."""

    kind: str                      # ranks | odd | even | suit | red | black | all
    ranks: tuple[str, ...] = ()    # for kind "ranks"
    suit: str = ""                 # for kind "suit"

    def __post_init__(self) -> None:
        if self.kind not in ("ranks", "odd", "even", "suit", "red", "black", "all"):
            raise ValueError(f"Unknown card group {self.kind!r}")
        if self.kind == "ranks" and (not self.ranks or set(self.ranks) - set(RANKS)):
            raise ValueError(f"Card group needs known ranks, got {self.ranks!r}")
        if self.kind == "suit" and self.suit not in SUITS:
            raise ValueError(f"Card group needs a suit, got {self.suit!r}")

    def contains(self, card: Card) -> bool:
        rank = str(card.rank).upper()
        if self.kind == "ranks":
            return rank in self.ranks
        if self.kind == "odd":
            return rank in ODD
        if self.kind == "even":
            return rank in EVEN
        if self.kind == "suit":
            return card.suit == self.suit
        if self.kind == "red":
            return card.suit in RED
        if self.kind == "black":
            return card.suit in BLACK
        return rank in RANKS  # all (never J-54's Joker)

    def covers(self) -> frozenset[tuple[str, str]]:
        """Every (rank, suit) in the group, to test whether two groups overlap."""
        return frozenset((r, s) for r in RANKS for s in SUITS if self.contains(Card(_rank(r), s)))

    @property
    def has_ace(self) -> bool:
        return any(r == "A" for r, _ in self.covers())

    def label(self) -> str:
        """The cards in plain English, e.g. "7s", "J, Q and K", "odd number cards (3, 5, 7, 9)"."""
        if self.kind == "ranks":
            if len(self.ranks) == 1:
                return _plural_rank(self.ranks[0])
            return _join(list(self.ranks))
        if self.kind == "odd":
            return "odd number cards (3, 5, 7, 9)"
        if self.kind == "even":
            return "even number cards (2, 4, 6, 8, 10)"
        if self.kind == "suit":
            return SUITS[self.suit]
        if self.kind == "red":
            return "red cards (hearts and diamonds)"
        if self.kind == "black":
            return "black cards (spades and clubs)"
        return "all cards"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **({"ranks": list(self.ranks)} if self.ranks else {}),
                **({"suit": self.suit} if self.suit else {})}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "CardGroup":
        return CardGroup(str(d["kind"]), tuple(str(r) for r in d.get("ranks", ())), str(d.get("suit", "")))


def ranks(*values: str) -> CardGroup:
    return CardGroup("ranks", tuple(values))


def _rank(r: str):
    from chaos_blackjack.core.game_state import Rank

    return Rank(r)


def _plural_rank(rank: str) -> str:
    return {"A": "aces", "J": "jacks", "Q": "queens", "K": "kings"}.get(rank, f"{rank}s")


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# --- rules -----------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvRule:
    """One environment rule. `duration` 0 = persistent; `age` = settled rounds it has been in force."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    duration: int = 0
    age: int = 0
    name: str = ""            # display name (generated when empty)

    def __post_init__(self) -> None:
        if self.type not in TYPES:
            raise ValueError(f"Unknown environment rule type {self.type!r}")
        _validate(self)

    # --- identity -----------------------------------------------------------------
    @property
    def signature(self) -> str:
        """Type and parameters (not duration or age): the same signature is the same effect."""
        return f"{self.type}:{json.dumps(self.params, sort_keys=True, ensure_ascii=False)}"

    @property
    def timed(self) -> bool:
        return self.duration > 0

    @property
    def remaining(self) -> int | None:
        """Rounds left including the current one; None for a persistent rule."""
        return max(0, self.duration - self.age) if self.timed else None

    @property
    def expired(self) -> bool:
        return self.timed and self.age >= self.duration

    def aged(self) -> "EnvRule":
        """One more round settled."""
        return replace(self, age=self.age + 1)

    # --- typed parameters -------------------------------------------------------------
    @property
    def actor(self) -> str:
        return str(self.params.get("actor", "both"))

    def applies_to(self, actor: str) -> bool:
        return self.actor in (actor, "both")

    @property
    def group(self) -> CardGroup:
        return CardGroup.from_dict(self.params["group"])

    @property
    def shifts(self) -> tuple[tuple[CardGroup, int], ...]:
        return tuple((CardGroup.from_dict(g), int(d)) for g, d in self.params["shifts"])

    # --- hand-value hooks (player and dealer) --------------------------------------------
    def fixed_value(self, card: Card, actor: str) -> int | None:
        if self.type == "fixed" and self.applies_to(actor) and self.group.contains(card):
            return int(self.params["value"])
        return None

    def shift(self, card: Card, actor: str) -> int:
        if self.type != "shift" or not self.applies_to(actor):
            return 0
        return sum(d for g, d in self.shifts if g.contains(card))

    def base_bust_limit(self, actor: str) -> int | None:
        if self.type == "bust" and self.applies_to(actor):
            return int(self.params["limit"])
        return None

    def tie_result(self) -> str | None:
        return str(self.params["result"]) if self.type == "tie" else None

    # --- money, items, shop and display hooks ------------------------------------------------
    @property
    def profit_cap(self) -> int | None:
        return int(self.params["cap"]) if self.type == "profit_cap" else None

    @property
    def bans_items(self) -> bool:
        return self.type == "item_ban"

    @property
    def hides_second_card(self) -> bool:
        return self.type == "hidden"

    def price_factor(self, kind: str) -> Fraction:
        """Price multiplier for a product kind (markup: consumables and permanents only)."""
        if self.type == "markup" and kind in ("item", "consumable", "permanent"):
            return Fraction(100 + int(self.params["pct"]), 100)
        return Fraction(1)

    def bust_result(self, side: str) -> str | None:
        """The outcome when `side` busts (and the other side does not), or None."""
        if self.type == "bust_outcome" and self.params["side"] == side:
            return str(self.params["result"])
        return None

    # --- text ------------------------------------------------------------------------------
    @property
    def title(self) -> str:
        return self.name or _default_name(self)

    def effect_text(self) -> str:
        return _effect_text(self)

    @property
    def scope(self) -> str:
        """What the rule acts on, in a few words (§2: every rule shows its target)."""
        if self.type in ("fixed", "shift", "bust"):
            return {"player": "Your hand", "dealer": "The dealer's hand", "both": "Both hands"}[self.actor]
        return {"tie": "Ties", "bust_outcome": "Busts", "profit_cap": "Your winnings", "item_ban": "Your items",
                "markup": "The shop", "hidden": "Your hand"}[self.type]

    @property
    def icon(self) -> str:
        """Asset id of the rule type's icon (gui/assets/manifest.py)."""
        return "ph_env_" + self.type

    def duration_text(self) -> str:
        if not self.timed:
            return "In force until removed or replaced."
        n = self.remaining
        return f"{n} round{'s' if n != 1 else ''} left, this one included."

    def removal_text(self) -> str:
        if self.type == "item_ban":
            return "Sacrifice a consumable (it has no effect), or wait for it to end."
        if self.timed:
            return "It ends on its own; Clause Removal removes it sooner. Silence Seal suppresses it for a round."
        return "Clause Removal removes it, or the dealer may replace it. Silence Seal suppresses it for a round."

    @property
    def tier(self) -> int:
        """1 light, 2 medium, 3 heavy (rule_tier)."""
        return rule_tier(self)

    @property
    def tier_name(self) -> str:
        return TIER_NAMES[self.tier]

    def text(self) -> str:
        """Everything a player needs: effect, duration and how it goes away."""
        return f"{self.effect_text()} {self.duration_text()} {self.removal_text()}"

    # --- save ------------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "params": json.loads(json.dumps(self.params)), "duration": self.duration,
                "age": self.age, **({"name": self.name} if self.name else {})}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "EnvRule":
        return EnvRule(str(d["type"]), dict(d.get("params", {})), int(d.get("duration", 0)), int(d.get("age", 0)),
                       str(d.get("name", "")))


# --- constructors (keep parameters in one JSON-safe shape) ------------------------------------


def fixed(group: CardGroup, value: int, actor: str = "both", **kw) -> EnvRule:
    return EnvRule("fixed", {"actor": actor, "group": group.to_dict(), "value": value}, **kw)


def shift(*shifts: tuple[CardGroup, int], actor: str = "both", **kw) -> EnvRule:
    return EnvRule("shift", {"actor": actor, "shifts": [[g.to_dict(), d] for g, d in shifts]}, **kw)


# --- tiers -----------------------------------------------------------------------------------------
# From the simulator (2026-10-14, black-jack-sim): the change in a basic-strategy player's EV per bet with the
# rule in force. Heavy loses more than 0.12 of the bet (your bust limit 19, the dealer's 22/23, a dealer bust
# pardoned, high cards rewritten to 7 or less); medium 0.05-0.12 (your limit 20, every card shifted, high cards
# rewritten to 8 or shifted by 2, ties to the dealer) and the rules that work on money or information (item
# ban, Withdrawal Limit, a face-down card); everything else is light.
TIER_NAMES = ("", "Light", "Medium", "Heavy")
_HIGH = {"10", "J", "Q", "K"}


def rule_tier(r: EnvRule) -> int:
    p = r.params
    if r.type == "bust_outcome":
        return 3
    if r.type == "bust":
        if r.actor == "player":
            return 3 if int(p["limit"]) <= 19 else 2
        return 3 if int(p["limit"]) >= 22 else 1
    if r.type == "fixed":
        group = r.group
        if group.kind == "ranks" and len(group.ranks) > 1 and set(group.ranks) <= _HIGH:
            value = int(p["value"])
            return 3 if value <= 7 else 2 if value <= 8 else 1
        return 1
    if r.type == "shift":
        for group, delta in r.shifts:
            if group.kind == "all" or (group.kind == "ranks" and len(group.ranks) > 1 and set(group.ranks) <= _HIGH
                                       and abs(delta) >= 2):
                return 2
        return 1
    if r.type in ("tie", "profit_cap", "item_ban", "hidden"):
        return 2
    return 1


def bust(actor: str, limit: int, rounds: int = 2, **kw) -> EnvRule:
    return EnvRule("bust", {"actor": actor, "limit": limit}, duration=rounds, **kw)


def tie(result: str = "dealer", **kw) -> EnvRule:
    return EnvRule("tie", {"result": result}, **kw)


def bust_outcome(side: str = "dealer", result: str = "push", rounds: int = 2, **kw) -> EnvRule:
    return EnvRule("bust_outcome", {"side": side, "result": result}, duration=rounds, **kw)


def profit_cap(cap: int, rounds: int = 3, **kw) -> EnvRule:
    return EnvRule("profit_cap", {"cap": cap}, duration=rounds, **kw)


def item_ban(rounds: int = 2, **kw) -> EnvRule:
    return EnvRule("item_ban", {}, duration=rounds, **kw)


def markup(pct: int, rounds: int = 3, **kw) -> EnvRule:
    return EnvRule("markup", {"pct": pct}, duration=rounds, **kw)


def hidden(rounds: int = 2, **kw) -> EnvRule:
    return EnvRule("hidden", {}, duration=rounds, **kw)


# --- consistency -------------------------------------------------------------------------------


def conflict(rules: Iterable[EnvRule], new: EnvRule) -> str:
    """Why `new` cannot join `rules` ("" = it can): one rule per type (§4.2)."""
    for r in rules:
        if r.type == new.type:
            return f"A {new.type} rule is already in force."
    return ""


def _validate(r: EnvRule) -> None:
    p = r.params
    if r.type in ("fixed", "shift", "bust") and r.actor not in ACTORS:
        raise ValueError(f"{r.type}: actor must be one of {ACTORS}")
    if r.type == "fixed":
        value = int(p["value"])
        group = r.group
        if not 1 <= value <= 10:
            raise ValueError("fixed: value must be 1 to 10")
        if group.kind == "ranks" and len(group.ranks) == 1 and BASE_VALUES[group.ranks[0]] == value:
            raise ValueError("fixed: the value must differ from the card's own value")
    elif r.type == "shift":
        shifts = r.shifts
        if not 1 <= len(shifts) <= 2 or any(d == 0 for _, d in shifts):
            raise ValueError("shift: one or two groups, each with a non-zero change")
        if len(shifts) == 2 and shifts[0][0].covers() & shifts[1][0].covers():
            raise ValueError("shift: the two groups must not overlap")
    elif r.type == "bust":
        if r.actor == "both" or not 15 <= int(p["limit"]) <= 26:
            raise ValueError("bust: one actor and a limit from 15 to 26")
    elif r.type == "tie":
        if p["result"] not in ("dealer", "player", "push"):
            raise ValueError("tie: result is dealer, player or push")
    elif r.type == "bust_outcome":
        if p["side"] not in ("dealer", "player") or p["result"] not in ("dealer", "player", "push"):
            raise ValueError("bust_outcome: side dealer/player, result dealer/player/push")
    elif r.type == "profit_cap":
        if int(p["cap"]) < 0:
            raise ValueError("profit_cap: cap must not be negative")
    elif r.type == "markup":
        if int(p["pct"]) <= 0:
            raise ValueError("markup: pct must be positive")
    if r.type in ("bust", "bust_outcome", "profit_cap", "item_ban", "markup", "hidden") and r.duration <= 0:
        raise ValueError(f"{r.type} is a timed rule")


# --- text -----------------------------------------------------------------------------------------

_WHOSE = {"player": "Your", "dealer": "The dealer's", "both": "Both hands'"}


def _whose(actor: str, group: CardGroup) -> str:
    return f"{_WHOSE[actor]} {group.label()}"


def _effect_text(r: EnvRule) -> str:
    p = r.params
    if r.type == "fixed":
        text = f"{_whose(r.actor, r.group)} count as {p['value']} each."
        if r.group.has_ace:
            text += f" Aces count as {p['value']} and no longer switch between high and low."
        return text
    if r.type == "shift":
        parts = [f"{g.label()} {'+' if d > 0 else '−'}{abs(d)} each" for g, d in r.shifts]
        lead = {"player": "In your hand", "dealer": "In the dealer's hand", "both": "In both hands"}[r.actor]
        return f"{lead}: {_join(parts)}. A card never counts less than 1; aces shift both their values."
    if r.type == "bust":
        if r.actor == "player":
            return f"Your base bust limit is {p['limit']}: you bust above {p['limit']}. Cores and items add to it."
        return f"The dealer's bust limit is {p['limit']}: the dealer busts above {p['limit']}."
    if r.type == "tie":
        result = {"dealer": "the dealer wins", "player": "you win", "push": "it is a push"}[p["result"]]
        return f"When neither side busts and the totals are equal, {result}."
    if r.type == "bust_outcome":
        result = {"dealer": "the dealer wins", "player": "you win", "push": "the round is a push"}[p["result"]]
        if p["side"] == "dealer":
            return f"When the dealer busts and you have not, {result}."
        return f"When you bust, {result}."
    if r.type == "profit_cap":
        return (f"You keep at most {p['cap']} chips of this round's profit; the rest is lost. Returned principal, "
                "refunds, loan advances and buy-backs are not profit.")
    if r.type == "item_ban":
        return "The next consumable you use only lifts this ban: it is spent with no effect."
    if r.type == "markup":
        return (f"Consumables and permanents cost {p['pct']}% more. Financial products and rerolls keep their price.")
    return "Your second opening card is dealt face down; your total stays hidden until you stand."


_GROUP_NAMES = {"odd": "Odd", "even": "Even", "red": "Red", "black": "Black", "all": "Whole Deck"}
_RANK_NAMES = {"A": "Ace", "2": "Two", "3": "Three", "4": "Four", "5": "Five", "6": "Six", "7": "Seven",
               "8": "Eight", "9": "Nine", "10": "Ten", "J": "Jack", "Q": "Queen", "K": "King"}


def _group_name(g: CardGroup) -> str:
    if g.kind == "ranks":
        if g.ranks == ("J", "Q", "K"):
            return "Court"
        if g.ranks == ("10", "J", "Q", "K"):
            return "High Card"
        return _RANK_NAMES[g.ranks[0]] if len(g.ranks) == 1 else _join(list(g.ranks))
    if g.kind == "suit":
        return SUITS[g.suit].capitalize()[:-1]
    return _GROUP_NAMES[g.kind]


def _default_name(r: EnvRule) -> str:
    if r.type == "fixed":
        return f"{_group_name(r.group)} Rewrite"
    if r.type == "shift":
        groups = [g for g, _ in r.shifts]
        if len(groups) == 2:
            return f"{_group_name(groups[0])}-{_group_name(groups[1])} Shift"
        sign = "Up" if r.shifts[0][1] > 0 else "Down"
        return f"{_group_name(groups[0])} {sign}"
    if r.type == "bust":
        return "Fragile Player" if r.actor == "player" else "Dealer's Margin"
    if r.type == "tie":
        return {"dealer": "Ties to the House", "player": "Ties to the Player", "push": "Ties Stand"}[r.params["result"]]
    if r.type == "bust_outcome":
        return "Dealer Bust Pardon" if r.params["side"] == "dealer" else "Player Bust Pardon"
    return {"profit_cap": "Withdrawal Limit", "item_ban": "Item Ban", "markup": "Price Hike",
            "hidden": "Face-Down Card"}[r.type]


# --- hand values ------------------------------------------------------------------------------------


def card_values(card: Card, actor: str, rules: Iterable[EnvRule]) -> tuple[int, int]:
    """(high, low) of one card after the environment: fixed rewrite first, then shifts.

    A non-ace card has one value (high == low), at least 1. An ace keeps its
    high/low switch with both values shifted (low at least 1), unless a fixed
    rewrite pins it, which also ends the switch (§3.1–3.2).
    """
    rules = tuple(rules)
    rank = str(card.rank).upper()
    if rank not in BASE_VALUES:  # J-54's Joker: never valued here
        return 0, 0
    pinned = next((v for r in rules if (v := r.fixed_value(card, actor)) is not None), None)
    delta = sum(r.shift(card, actor) for r in rules)
    if pinned is not None:
        value = max(1, pinned + delta)
        return value, value
    if rank == "A":
        return max(1, 11 + delta), max(1, 1 + delta)
    value = max(1, BASE_VALUES[rank] + delta)
    return value, value


def base_bust_limit(actor: str, rules: Iterable[EnvRule], default: int = 21) -> int:
    """The actor's base bust limit before cores and items add to it."""
    return next((v for r in rules if (v := r.base_bust_limit(actor)) is not None), default)


def tie_result(rules: Iterable[EnvRule]) -> str | None:
    return next((v for r in rules if (v := r.tie_result()) is not None), None)


def bust_result(side: str, rules: Iterable[EnvRule]) -> str | None:
    return next((v for r in rules if (v := r.bust_result(side)) is not None), None)
