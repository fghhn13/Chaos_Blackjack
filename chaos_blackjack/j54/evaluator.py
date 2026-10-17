"""J-54's exact evaluator: the meter (win probability, EV, capture) and the heat map.

Ported from the rule lab's evaluator (docs/design/J54_V2_SPEC.md section 5;
the rules are docs/design/J54_PRIMITIVES.md section 4). Pure Python, standard
library only, no controller or table imports: the table builds a `Valuation`
from the active condition and the firmware and asks an `Evaluator` about the
deck the next round is dealt from.

Model
-----
* Every draw is independent with the deck's proportions (i.i.d., "infinite
  deck"). This is exact for a deck read card by card with replacement and
  close for a full deck: on the 52-card deck the win probability is within a
  few tenths of a point of real hands dealt without replacement.
* Order of play: player, J-54, player, J-54 (hole card). J-54 peeks for an
  original-card natural (A plus 10/J/Q/K by rank, whatever the rules make
  them worth) and naturals settle first: J-54's natural beats every hand but
  the player's natural (a push); the player's natural wins and pays 3:2.
* The player sees J-54's up card and hits or stands to maximise the
  objective: the win probability for `win` / `push` / `loss` / `capture` (ties
  broken by win minus loss), the expected result for `ev`. Only hit and stand
  are modelled: no double, no surrender, no items.
* J-54 draws until its best total reaches `dealer_stand_on` (it stands on a
  soft total too) and busts above `dealer_bust`; the player busts above
  `player_bust`. An ace (or the Joker for the player) counts 11 while that
  keeps the total within the side's own bust line.
* Effect rules are stateless and per side: J-54's `dealer_rules` change only
  the values of the cards J-54 draws, the firmware's `player_rules` only the
  player's. Each rule is applied in order to the card's base value:
  `{"op": "bonus", "filter": "color:black", "amount": 1}`,
  `{"op": "scale", "filter": "suit:♥", "factor": 2}`,
  `{"op": "set", "filter": "face", "value": 5}` (`set` drops an ace's soft
  value unless `"soft": true`). Filters: `any` (every card but the Joker),
  `all`, `joker`, `rank:7`, `ranks:4-6` (A=1 ... K=13), `suit:♥` (or `S H D
  C`), `color:red|black`, `parity:odd|even` (by rank number: 2 4 6 8 10 Q are
  even), `face` (J Q K), `number` (2-10), `low` (2-6), `high` (10 J Q K A),
  `ten` (10 J Q K), `card:A♠`; `&` is AND, `|` is OR, a leading `!` negates
  an atom.
* The Joker is a soft ace (1 or 11) for the player and never part of a
  natural; player rules whose filter matches it (`all`, `joker`) apply to it.
  When J-54 draws it, J-54 swaps in the next card, so it counts 0 for J-54
  and is modelled by drawing J-54's cards from the deck without the Joker.
  `capture` is the probability that the player draws the Joker during the
  hand (in the first two cards or by hitting under the win-maximising
  policy), whatever the outcome; 0 without a Joker.
* `heat(deck)` gives, per rank+colour group present ("5r", "Kb"; the Joker is
  never a group), the change of the win probability in percentage points
  when one card of the group is removed (spread over the group's suits by
  their counts); positive means removing the card helps the player.

Limits
------
* i.i.d. draws ignore that the cards already dealt leave the deck. The error
  grows as the deck shrinks: decks below ~30 cards are under-read by 1-4 pp
  (the lab's Monte Carlo, montecarlo.py; J54_PRIMITIVES.md section 12).
* A hand holds at most 8 cards when some card is worth 0 or less to that side
  (otherwise a total could stop growing); with positive values there is no
  cap, as in the game.
* Results are cached by (composition, valuation) in a bounded module cache;
  the same deck under the same valuation returns the same object.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.j54.deck_ops import JOKER, RANKS, SUITS

__all__ = ["Evaluator", "HandStats", "Valuation", "clear_cache", "group_of", "parse_filter"]

RED = ("♥", "♦")
COLOURS = ("r", "b")            # heat group suffixes: red, black
MAX_CARDS = 8                   # per hand, only when a card is worth <= 0 to that side
CACHE_LIMIT = 20_000
SIDES = ("player", "dealer")

_RANK_NUMBER = {r: i + 1 for i, r in enumerate(
    ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"))}
_TENS = ("10", "J", "Q", "K")
_SUIT_ALIASES = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
_OPS = {"bonus": "amount", "scale": "factor", "set": "value"}
_EPS = 1e-12
BUST = None

CardKey = tuple[str, str]       # (rank, suit); the Joker is (JOKER, "")
Filter = Callable[[str, str], bool]


# ---------------------------------------------------------------------------
# Data


@dataclass(frozen=True)
class Valuation:
    """How cards are worth and when each side stops: everything the evaluator
    needs besides the deck. Rules are mappings `{"op", "filter", "amount" /
    "factor" / "value"}` (see the module docstring); lists are accepted and
    stored as tuples. Hashable and comparable by content."""

    dealer_rules: tuple[Mapping[str, Any], ...] = ()
    player_rules: tuple[Mapping[str, Any], ...] = ()
    dealer_stand_on: int = 17
    player_bust: int = 21
    dealer_bust: int = 21
    joker_in_deck: bool = False      # add one Joker to a deck that holds none

    def __post_init__(self) -> None:
        object.__setattr__(self, "dealer_rules", tuple(self.dealer_rules))
        object.__setattr__(self, "player_rules", tuple(self.player_rules))

    def key(self) -> tuple:
        return (_freeze(self.dealer_rules), _freeze(self.player_rules), int(self.dealer_stand_on),
                int(self.player_bust), int(self.dealer_bust), bool(self.joker_in_deck))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Valuation) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())


@dataclass(frozen=True)
class HandStats:
    """One hand from a deck: probabilities under the win-maximising policy,
    `ev` (in bets, a natural pays 3:2) under the EV-maximising one."""

    win: float
    push: float
    loss: float
    ev: float
    capture: float = 0.0
    natural: float = 0.0     # P(the player wins with a natural); part of `win`

    @property
    def bar(self) -> float:
        return self.win


@dataclass(frozen=True)
class _PClass:
    """A card as the player draws it."""
    value: int
    soft: bool
    nat: str | None          # "A" / "T" for naturals, else None
    joker: bool


@dataclass(frozen=True)
class _DClass:
    """A card as J-54 draws it."""
    value: int
    soft: bool
    nat: str | None


@dataclass
class _Solved:
    win: float
    push: float
    loss: float
    natural: float
    ev: float | None
    capture: float
    # J-54's up-card class -> decide(hard, soft, n) -> hit?
    deciders: dict[_DClass, Callable[[int, bool, int], bool]] = field(default_factory=dict)
    player_capped: bool = False


# ---------------------------------------------------------------------------
# Cards and filters


def _card_key(card: Card) -> CardKey:
    rank = str(card.rank).strip().upper()
    if rank == JOKER:
        return (JOKER, "")
    if rank not in _RANK_NUMBER:
        raise ValueError(f"Unknown rank {card.rank!r}")
    suit = _SUIT_ALIASES.get(str(card.suit).upper(), str(card.suit))
    if suit and suit not in SUITS:
        raise ValueError(f"Unknown suit {card.suit!r}")
    return (rank, suit)


def group_of(card: Card) -> str | None:
    """The heat group of a card ("5r", "Kb"); None for the Joker and for a
    card without a suit."""
    rank, suit = _card_key(card)
    if rank == JOKER or not suit:
        return None
    return rank + ("r" if suit in RED else "b")


def _rank_range(text: str) -> tuple[int, int]:
    lo, _, hi = text.partition("-")
    try:
        lo_n = _RANK_NUMBER[lo.strip().upper()]
        hi_n = _RANK_NUMBER[hi.strip().upper()] if hi else lo_n
    except KeyError:
        raise ValueError(f"Unknown rank range {text!r}") from None
    return lo_n, hi_n


def _atom(text: str) -> Filter:
    key, _, arg = text.strip().partition(":")
    key, arg = key.strip().lower(), arg.strip()
    if key == "any":
        return lambda r, s: r != JOKER
    if key == "all":
        return lambda r, s: True
    if key == "joker":
        return lambda r, s: r == JOKER
    if key in ("rank", "ranks"):
        lo, hi = _rank_range(arg)
        return lambda r, s: r != JOKER and lo <= _RANK_NUMBER[r] <= hi
    if key == "suit":
        want = _SUIT_ALIASES.get(arg.upper(), arg)
        if want not in SUITS:
            raise ValueError(f"Unknown suit in filter {text!r}")
        return lambda r, s: r != JOKER and s == want
    if key in ("color", "colour"):
        if arg.lower() not in ("red", "black"):
            raise ValueError(f"Unknown colour in filter {text!r}")
        red = arg.lower() == "red"
        return lambda r, s: r != JOKER and bool(s) and (s in RED) == red
    if key == "parity":
        if arg.lower() not in ("odd", "even"):
            raise ValueError(f"Unknown parity in filter {text!r}")
        odd = arg.lower() == "odd"
        return lambda r, s: r != JOKER and (_RANK_NUMBER[r] % 2 == 1) == odd
    if key == "face":
        return lambda r, s: r in ("J", "Q", "K")
    if key == "number":
        return lambda r, s: r not in (JOKER, "J", "Q", "K", "A")
    if key == "low":
        return lambda r, s: r in ("2", "3", "4", "5", "6")
    if key == "high":
        return lambda r, s: r in ("10", "J", "Q", "K", "A")
    if key == "ten":
        return lambda r, s: r in _TENS
    if key == "card":
        target = _card_key(Card(arg[:-1], arg[-1])) if arg.upper() != JOKER else (JOKER, "")
        return lambda r, s: (r, s) == target
    raise ValueError(f"Unknown filter {text!r}")


def _negate(f: Filter) -> Filter:
    return lambda r, s: not f(r, s)


def parse_filter(text: str) -> Filter:
    """Compile a filter (see the module docstring) to a test on (rank, suit)."""
    alternatives = []
    for part in str(text).split("|"):
        atoms = []
        for raw in part.split("&"):
            raw = raw.strip()
            neg = raw.startswith("!")
            f = _atom(raw[1:] if neg else raw)
            atoms.append(_negate(f) if neg else f)
        alternatives.append(atoms)
    return lambda r, s: any(all(a(r, s) for a in atoms) for atoms in alternatives)


def _compile(rules: Iterable[Mapping[str, Any]]) -> list[tuple[str, Any, bool, Filter]]:
    out = []
    for rule in rules:
        op = str(rule.get("op", ""))
        if op not in _OPS:
            raise ValueError(f"Unknown rule op {op!r}; expected one of {', '.join(_OPS)}")
        param = _OPS[op]
        if param not in rule:
            raise ValueError(f"Rule {dict(rule)!r} needs {param!r}")
        out.append((op, int(rule[param]), bool(rule.get("soft", False)),
                    parse_filter(rule.get("filter", "all"))))
    return out


def _base_value(rank: str, side: str) -> tuple[int, bool]:
    if rank == JOKER:
        return (1, True) if side == "player" else (0, False)
    if rank == "A":
        return 1, True
    return min(_RANK_NUMBER[rank], 10), False


def _best(hard: int, soft: bool, limit: int) -> int:
    return hard + 10 if soft and hard + 10 <= limit else hard


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


# ---------------------------------------------------------------------------
# The evaluator

_CACHE: dict[tuple, Any] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _cached(key: tuple, make: Callable[[], Any]) -> Any:
    hit = _CACHE.get(key)
    if hit is None:
        hit = make()
        if len(_CACHE) >= CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key] = hit
    return hit


class Evaluator:
    """Evaluates decks under one valuation. Decks are iterables of the game's
    `Card` (the Joker is `Card(Rank("JK"), "")`)."""

    def __init__(self, valuation: Valuation) -> None:
        self.valuation = valuation
        self._vkey = valuation.key()
        self._rules = {"player": _compile(valuation.player_rules),
                       "dealer": _compile(valuation.dealer_rules)}
        self._pclass: dict[CardKey, _PClass] = {}
        self._dclass: dict[CardKey, _DClass] = {}

    # -- card values ----------------------------------------------------

    def value(self, card: Card, side: str) -> tuple[int, bool]:
        """(hard value, counts as a soft ace) of a card for "player" or
        "dealer" (J-54) under this valuation."""
        if side not in SIDES:
            raise ValueError(f"Unknown side {side!r}; expected one of {', '.join(SIDES)}")
        return self._value(_card_key(card), side)

    def _value(self, key: CardKey, side: str) -> tuple[int, bool]:
        rank, suit = key
        value, soft = _base_value(rank, side)
        if rank == JOKER and side == "dealer":
            return value, soft
        for op, arg, soft_set, match in self._rules[side]:
            if not match(rank, suit):
                continue
            if op == "set":
                value, soft = arg, soft_set
            elif op == "scale":
                value *= arg
            else:
                value += arg
        return value, soft

    def _player(self, key: CardKey) -> _PClass:
        c = self._pclass.get(key)
        if c is None:
            v, s = self._value(key, "player")
            c = self._pclass[key] = _PClass(v, s, _natural(key), key[0] == JOKER)
        return c

    def _dealer(self, key: CardKey) -> _DClass:
        c = self._dclass.get(key)
        if c is None:
            v, s = self._value(key, "dealer")
            c = self._dclass[key] = _DClass(v, s, _natural(key))
        return c

    # -- public queries ---------------------------------------------------

    def stats(self, deck: Iterable[Card]) -> HandStats:
        comp = self._composition(deck)
        return _cached(("stats", self._vkey, _comp_key(comp)), lambda: self._stats(comp))

    def heat(self, deck: Iterable[Card]) -> dict[str, float]:
        """{group: pp} for the rank+colour groups present, in rank order
        (2 ... A), red before black. Treat the result as read-only: it is
        cached."""
        comp = self._composition(deck)
        return _cached(("heat", self._vkey, _comp_key(comp)), lambda: self._heat(comp))

    def should_hit(self, deck: Iterable[Card], up: Card, hand: Iterable[Card]) -> bool:
        """Whether the win-maximising policy for `deck` hits `hand` against
        J-54's up card `up` (for simulations and tests)."""
        comp = self._composition(deck)
        solved = _cached(("policy", self._vkey, _comp_key(comp)),
                         lambda: self._solve(comp, want_ev=False, keep_policy=True))
        up_class = self._dealer(_card_key(up))
        decide = solved.deciders.get(up_class)
        if decide is None:
            raise ValueError(f"J-54's up card {up} is not in the deck")
        hard, soft, n = 0, False, 0
        for c in hand:
            k = self._player(_card_key(c))
            hard, soft, n = hard + k.value, soft or k.soft, n + 1
        return decide(hard, soft, n if solved.player_capped else 2)

    # -- internals ----------------------------------------------------------

    def _composition(self, deck: Iterable[Card]) -> dict[CardKey, float]:
        comp: dict[CardKey, float] = {}
        for card in deck:
            key = _card_key(card)
            comp[key] = comp.get(key, 0.0) + 1.0
        if self.valuation.joker_in_deck and (JOKER, "") not in comp:
            comp[(JOKER, "")] = 1.0
        return comp

    def _stats(self, comp: dict[CardKey, float]) -> HandStats:
        s = self._solve(comp, want_ev=True, keep_policy=False)
        return HandStats(s.win, s.push, s.loss, s.ev or 0.0, s.capture, s.natural)

    def _heat(self, comp: dict[CardKey, float]) -> dict[str, float]:
        base = self._solve(comp, want_ev=False, keep_policy=False).win
        groups: dict[str, list[CardKey]] = {}
        for key, n in comp.items():
            rank, suit = key
            if rank == JOKER or not suit or n <= 1e-9:
                continue
            groups.setdefault(rank + ("r" if suit in RED else "b"), []).append(key)
        out: dict[str, float] = {}
        for rank in RANKS:
            for colour in COLOURS:
                cards = groups.get(rank + colour)
                if not cards:
                    continue
                total = sum(comp[k] for k in cards)
                take = min(1.0, total)
                new = dict(comp)
                for k in cards:
                    new[k] -= comp[k] * take / total
                    if new[k] <= 1e-9:
                        del new[k]
                if not any(k[0] != JOKER for k in new):
                    continue
                win = self._solve(new, want_ev=False, keep_policy=False).win
                # Rounded so that exactly equal groups tie instead of differing
                # in the last float bit.
                out[rank + colour] = round((win - base) * 100.0 / take, 9)
        return out

    def _solve(self, comp: dict[CardKey, float], want_ev: bool, keep_policy: bool) -> _Solved:
        v = self.valuation
        lim_p, lim_d, stand_on = int(v.player_bust), int(v.dealer_bust), int(v.dealer_stand_on)

        total = sum(n for n in comp.values() if n > 0)
        d_total = sum(n for k, n in comp.items() if n > 0 and k[0] != JOKER)
        if d_total <= _EPS:
            raise ValueError("The deck holds no card besides the Joker")
        acc_p: dict[_PClass, float] = {}
        acc_d: dict[_DClass, float] = {}
        for key, n in comp.items():
            if n <= _EPS:
                continue
            pc = self._player(key)
            acc_p[pc] = acc_p.get(pc, 0.0) + n / total
            if key[0] != JOKER:
                dc = self._dealer(key)
                acc_d[dc] = acc_d.get(dc, 0.0) + n / d_total
        p_items = tuple(acc_p.items())
        d_items = tuple(acc_d.items())
        p_joker = sum(p for k, p in p_items if k.joker)
        # Count cards only when a card can leave the total unchanged.
        p_step = 1 if any(k.value <= 0 for k, _ in p_items) else 0
        d_step = 1 if any(k.value <= 0 for k, _ in d_items) else 0

        @lru_cache(maxsize=None)
        def dealer(hard: int, soft: bool, n: int) -> tuple[tuple[int | None, float], ...]:
            best = _best(hard, soft, lim_d)
            if best > lim_d:
                return ((BUST, 1.0),)
            if best >= stand_on or (d_step and n >= MAX_CARDS):
                return ((best, 1.0),)
            out: dict[int | None, float] = {}
            for k, p in d_items:
                for res, q in dealer(hard + k.value, soft or k.soft, n + d_step):
                    out[res] = out.get(res, 0.0) + p * q
            return tuple(out.items())

        # The player's two-card starts: (hard, soft, natural, holds the Joker).
        starts: dict[tuple[int, bool, bool, bool], float] = {}
        for a, pa in p_items:
            for b, pb in p_items:
                nat = {a.nat, b.nat} == {"A", "T"}
                key = (a.value + b.value, a.soft or b.soft, nat, a.joker or b.joker)
                starts[key] = starts.get(key, 0.0) + pa * pb
        n0 = 2

        def player_solver(outcomes: tuple[tuple[int | None, float], ...]):
            """The player's play against one up card's final totals. A factory
            so that each up card's recursive functions refer to themselves."""

            @lru_cache(maxsize=None)
            def stand(best: int) -> tuple[float, float, float]:
                w = p = l = 0.0
                for res, q in outcomes:
                    if res is BUST or best > res:
                        w += q
                    elif best == res:
                        p += q
                    else:
                        l += q
                return w, p, l

            hits: dict[tuple[int, bool, int], bool] = {}

            @lru_cache(maxsize=None)
            def play(hard: int, soft: bool, n: int) -> tuple[float, float, float]:
                """(win, push, loss) under the win-maximising policy."""
                best = _best(hard, soft, lim_p)
                if best > lim_p:
                    return 0.0, 0.0, 1.0
                s = stand(best)
                if p_step and n >= MAX_CARDS:
                    hits[(hard, soft, n)] = False
                    return s
                w = p = l = 0.0
                for k, pk in p_items:
                    a, b, c = play(hard + k.value, soft or k.soft, n + p_step)
                    w += pk * a
                    p += pk * b
                    l += pk * c
                take = w > s[0] + _EPS or (abs(w - s[0]) <= _EPS and w - l > s[0] - s[2] + _EPS)
                hits[(hard, soft, n)] = take
                return (w, p, l) if take else s

            @lru_cache(maxsize=None)
            def play_ev(hard: int, soft: bool, n: int) -> float:
                """Expected result in bets under the EV-maximising policy."""
                best = _best(hard, soft, lim_p)
                if best > lim_p:
                    return -1.0
                w, _, l = stand(best)
                s = w - l
                if p_step and n >= MAX_CARDS:
                    return s
                h = sum(pk * play_ev(hard + k.value, soft or k.soft, n + p_step) for k, pk in p_items)
                return h if h > s + _EPS else s

            @lru_cache(maxsize=None)
            def chase(hard: int, soft: bool, n: int) -> float:
                """P(the player draws the Joker from here on, holding none)."""
                if _best(hard, soft, lim_p) > lim_p or not hits.get((hard, soft, n), False):
                    return 0.0
                return sum(pk if k.joker else pk * chase(hard + k.value, soft or k.soft, n + p_step)
                           for k, pk in p_items)

            return play, play_ev, chase, hits

        win = push = loss = natural = ev = capture = 0.0
        deciders: dict[_DClass, Callable[[int, bool, int], bool]] = {}

        for up, pu in d_items:
            # J-54's hole card: its natural, and the final totals without one.
            p_dnat = 0.0
            dist: dict[int | None, float] = {}
            for hole, ph in d_items:
                if {up.nat, hole.nat} == {"A", "T"}:
                    p_dnat += ph
                    continue
                for res, q in dealer(up.value + hole.value, up.soft or hole.soft, 2):
                    dist[res] = dist.get(res, 0.0) + ph * q
            if p_dnat < 1.0 - _EPS:
                outcomes = tuple((res, q / (1.0 - p_dnat)) for res, q in dist.items())
            else:
                outcomes = ()

            play, play_ev, chase, hits = player_solver(outcomes)

            for (hard, soft, nat, jk), ps in starts.items():
                pr = pu * ps
                if jk:
                    capture += pr
                if p_dnat > 0.0:
                    if nat:
                        push += pr * p_dnat
                    else:
                        loss += pr * p_dnat
                        ev -= pr * p_dnat
                rest = pr * (1.0 - p_dnat)
                if rest <= 0.0:
                    continue
                if nat:
                    win += rest
                    natural += rest
                    ev += rest * 1.5
                    continue
                w, p, l = play(hard, soft, n0)
                win += rest * w
                push += rest * p
                loss += rest * l
                if want_ev:
                    ev += rest * play_ev(hard, soft, n0)
                if p_joker > 0.0 and not jk:
                    capture += rest * chase(hard, soft, n0)

            if keep_policy:
                def decide(hard: int, soft: bool, n: int, play=play, hits=hits) -> bool:
                    if _best(hard, soft, lim_p) > lim_p:
                        return False
                    play(hard, soft, n)
                    return hits.get((hard, soft, n), False)
                deciders[up] = decide

        return _Solved(win, push, loss, natural, ev if want_ev else None, capture,
                       deciders, bool(p_step))


def _natural(key: CardKey) -> str | None:
    rank = key[0]
    if rank == "A":
        return "A"
    if rank in _TENS:
        return "T"
    return None


def _comp_key(comp: Mapping[CardKey, float]) -> tuple:
    return tuple(sorted((r, s, round(n, 9)) for (r, s), n in comp.items() if n > 1e-9))
