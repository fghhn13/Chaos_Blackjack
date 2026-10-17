"""J-54's experiment conditions (docs/design/J54_V2_SPEC.md section 3).

A condition changes only **J-54's** cards: a value operation on the cards a
filter selects, or the total J-54 stands on. Each one belongs to a camp
(classic, anti, loner) that J-54's program (j54/program.py) alternates. The
numbers and the camp are the rule's params in the balance profile
(`chaos_rule.params`); the defaults below are used when a profile has none.

Value operations have the shape the evaluator's `Valuation` takes
(`{"op": "bonus"|"scale"|"set", "filter": ..., "amount"/"factor"/"value"}`),
and the firmware (j54/firmware.py) uses the same operations on the player's
cards. Filters: `color:black|red`, `parity:even|odd`, `suit:<s>`, `face`,
`low` (2-6), `rank:<R>`, `ranks:<R>-<R>`. An operation changes both values of
an ace (11 and 1); a Joker matches no filter.

The modifiers are actor-aware (`adjust_rank_value_for`, rules/modifiers.py),
so wherever one is in force the player's cards keep their values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.registry import register_rule

DEALER = "dealer"
CAMPS = ("classic", "anti", "loner")
RANK_ORDER = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")  # ranges, e.g. ranks:4-6
_NUMBER = {"A": 1, "J": 11, "Q": 12, "K": 13}
_BLACK, _RED = ("♠", "♣"), ("♥", "♦")
VALUE_OPS = ("bonus", "scale", "set")

# id -> (name, the change in a few words, default params)
CONDITIONS: dict[str, tuple[str, str, dict[str, Any]]] = {
    "j54_black_plus": ("Black Bias", "J-54's black cards count +{amount}",
                       {"camp": "classic", "op": "bonus", "filter": "color:black", "amount": 1}),
    "j54_even_plus": ("Even Bias", "J-54's even ranks (2 4 6 8 10 Q) count +{amount}",
                      {"camp": "classic", "op": "bonus", "filter": "parity:even", "amount": 2}),
    "j54_hearts_scale": ("Heart Gain", "J-54's hearts count ×{factor}",
                         {"camp": "classic", "op": "scale", "filter": "suit:♥", "factor": 2}),
    "j54_stand_19": ("High Threshold", "J-54 stands on {threshold}", {"camp": "classic", "threshold": 19}),
    "j54_stand_15": ("Low Threshold", "J-54 stands on {threshold}", {"camp": "anti", "threshold": 15}),
    "j54_low_plus": ("Low Bias", "J-54's low cards (2-6) count +{amount}",
                     {"camp": "anti", "op": "bonus", "filter": "low", "amount": 3}),
    "j54_faces_set": ("Face Reset", "J-54's J, Q and K count {value}",
                      {"camp": "loner", "op": "set", "filter": "face", "value": 5}),
}


def _rank_number(rank: str) -> int:
    return _NUMBER.get(rank, 0) or int(rank)


def matches(card: Card, flt: str) -> bool:
    """Whether a card passes a value filter (a Joker never does)."""
    rank, suit = str(card.rank).upper(), card.suit
    if rank == "JK":
        return False
    kind, _, arg = flt.partition(":")
    if kind == "color":
        return suit in (_BLACK if arg == "black" else _RED)
    if kind == "parity":  # A 1, J 11, Q 12, K 13: the even ranks are 2 4 6 8 10 Q
        return _rank_number(rank) % 2 == (0 if arg == "even" else 1)
    if kind == "suit":
        return suit == arg
    if kind == "face":
        return rank in ("J", "Q", "K")
    if kind == "low":
        return rank in ("2", "3", "4", "5", "6")
    if kind == "rank":
        return rank == arg.upper()
    if kind == "ranks":
        lo, _, hi = arg.upper().partition("-")
        return RANK_ORDER.index(lo) <= RANK_ORDER.index(rank) <= RANK_ORDER.index(hi or lo)
    raise ValueError(f"Unknown card filter {flt!r}")


def check_filter(flt: str) -> str:
    """`flt` when it is a valid filter (raises ValueError otherwise)."""
    matches(Card(Rank("2"), "♠"), flt)
    kind, _, arg = flt.partition(":")
    if kind in ("rank", "ranks") and any(r not in RANK_ORDER for r in arg.upper().split("-")):
        raise ValueError(f"Unknown rank in filter {flt!r}")
    return flt


def apply_value(rule: Mapping[str, Any], card: Card, value: int) -> int:
    """One value operation on a card's value (unchanged when the filter does not match)."""
    if not matches(card, str(rule["filter"])):
        return value
    op = rule["op"]
    if op == "bonus":
        return value + int(rule["amount"])
    if op == "scale":
        return value * int(rule["factor"])
    if op == "set":
        return int(rule["value"])
    raise ValueError(f"Unknown value operation {op!r}")


@dataclass(frozen=True)
class ConditionModifier:
    """One of J-54's conditions: a value operation on J-54's cards, or J-54's stand threshold."""

    id: str
    name: str
    camp: str
    rule: Mapping[str, Any] | None = None   # {"op", "filter", "amount"/"factor"/"value"}; None = no value change
    threshold: int | None = None            # the total J-54 stands on; None = the profile's
    text: str = ""
    chaos_flags: frozenset[str] = field(default_factory=frozenset)

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value  # without an actor nothing changes: the condition is J-54's alone

    def adjust_rank_value_for(self, card: Card, base_value: int, actor: str) -> int:
        if actor != DEALER or self.rule is None:
            return base_value
        return apply_value(self.rule, card, base_value)

    def describe(self) -> str:
        return f"{self.name}: {self.text}."

    def valuation(self) -> tuple[Mapping[str, Any], ...]:
        """The condition's value rules in the evaluator's shape (J-54's side)."""
        return (dict(self.rule),) if self.rule is not None else ()


def build_condition(rule_id: str, params: Mapping[str, Any]) -> ConditionModifier:
    name, text, default = CONDITIONS[rule_id]
    spec = {**default, **params}
    camp = str(spec["camp"])
    if camp not in CAMPS:
        raise ValueError(f"{rule_id}: unknown camp {camp!r}; expected one of {', '.join(CAMPS)}")
    rule = None
    if "op" in spec:
        op = str(spec["op"])
        if op not in VALUE_OPS:
            raise ValueError(f"{rule_id}: unknown value operation {op!r}")
        key = {"bonus": "amount", "scale": "factor", "set": "value"}[op]
        rule = {"op": op, "filter": check_filter(str(spec["filter"])), key: int(spec[key])}
    threshold = int(spec["threshold"]) if spec.get("threshold") is not None else None
    if rule is None and threshold is None:
        raise ValueError(f"{rule_id}: a condition needs a value operation or a threshold")
    return ConditionModifier(rule_id, name, camp, rule, threshold, text.format(**spec))


# Collection demos: (player, dealer, deck) where the condition changes J-54's total.
_DEMO_DEALS: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "j54_black_plus": (("10♥", "8♦"), ("10♣", "7♠"), ("2♣",)),
    "j54_even_plus": (("10♠", "9♥"), ("Q♣", "6♦"), ("2♣",)),
    "j54_hearts_scale": (("10♠", "7♦"), ("4♥", "10♣"), ("2♣",)),
    "j54_stand_19": (("10♠", "8♥"), ("10♣", "6♦"), ("2♣", "3♠", "K♦")),
    "j54_stand_15": (("10♠", "8♥"), ("10♣", "6♦"), ("2♣", "3♠", "K♦")),
    "j54_low_plus": (("10♠", "7♥"), ("10♣", "4♦"), ("2♣",)),
    "j54_faces_set": (("10♠", "8♥"), ("K♣", "Q♦"), ("2♣", "3♠", "K♦")),
}


def _demo(rule_id: str):
    from chaos_blackjack.codex.models import DemoScript, DemoStep as Step

    player, dealer, deck = _DEMO_DEALS[rule_id]
    threshold = "threshold" in CONDITIONS[rule_id][2]
    return DemoScript(player, dealer, deck, True, (
        Step("deal", caption="A fixed deal at J-54's table."),
        Step("apply_rule", rule_id, "J-54's condition is in force: it changes J-54's cards only, never yours."),
        Step("stand", caption="Reveal J-54's hand."),
        Step("dealer", caption="At J-54's table J-54 stands on the condition's total." if threshold
             else "J-54's total counts the condition; yours stays as printed."),
    ))


# What a camp means for the player, for the Collection.
CAMP_TEXT = {
    "classic": "Classic camp: it leans the way plain blackjack does, so the heat map keeps its usual colours.",
    "anti": "Anti camp: it leans the other way, so the heat map turns around; cards worth keeping may now be "
            "worth cutting.",
    "loner": "Loner camp: it goes its own way; read the heat map afresh.",
}


def _codex_detail(rule_id: str, config) -> str:
    """The Collection page: what the condition does with the profile's numbers, its camp, and how long."""
    from chaos_blackjack.j54.table import _settings

    m = build_condition(rule_id, config.chaos_rule_params.get(rule_id, {}))
    low, _, high = str(_settings(config)["segment_len"]).partition(",")
    return (f"{m.text}. It changes J-54's cards only, never yours. {CAMP_TEXT[m.camp]} J-54 runs one condition "
            f"at a time, each for {low} to {high or low} rounds, and on a condition's last round it names the "
            "next one's camp, so you can keep compute for the new map.")


def _plugin(rule_id: str) -> type:
    name, text, default = CONDITIONS[rule_id]

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> ConditionModifier:
        return build_condition(rule_id, params)

    return type(f"Condition_{rule_id}", (), {
        "id": rule_id, "codex_name": name,
        "codex_summary": f"{text.format(**default)}. {str(default['camp']).title()} camp.",
        "codex_detail": staticmethod(lambda config: _codex_detail(rule_id, config)),
        "codex_category": "condition",
        "from_params": from_params, "codex_demo": _demo(rule_id),
    })


for _rule_id in CONDITIONS:
    register_rule(_rule_id, _plugin(_rule_id))
