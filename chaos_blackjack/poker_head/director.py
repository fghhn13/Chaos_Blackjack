"""Poker Head's offline director: one environment action per round, growing with the round.

Design: docs/design/POKER_HEAD_CHAOS_RULES_AND_AGENT.zh-CN.md §6–7. The
director reads only the seed, the round, the rules in force (with age and
duration), how earlier rules left the table and its stage settings — never
the player's build, items, bets, cards or the future deck — so it changes
the environment without hunting a build.

Each round, before shopping and betting:

1. find the stage (action chance, rule slots, pressure budget, type weights, variant pool);
2. list legal additions (a free slot) or, when full, legal replacements of
   one persistent rule that has been in force two full rounds;
3. roll the action chance; no action keeps the table as it is;
4. pick a type by weight among types with a legal variant, then a variant uniformly;
5. commit once; nothing later in the round adds or redraws.

Limits: one rule per type, the stage's slots (and the table's rule_slots),
the pressure budget, at most one rule of pressure 3+, never Face-Down Card
with Item Ban, a type cools down after the player clears it (2 actions) or it
ends (1 action), and a replaced signature does not return for 2 actions.

Every number is a `mode.chaos.director.*` setting of the balance profile;
`DEFAULTS` mirror the shipped values for profiles cloned before them.
Randomness: one stream per round and purpose, seeded by the run seed, so
looking, shopping, saving and loading never change a decision.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Iterable

from chaos_blackjack.poker_head import environment as env
from chaos_blackjack.poker_head.money import chips
from chaos_blackjack.poker_head.environment import NUMBER_RANKS, RANKS, CardGroup, EnvRule, ranks

COURT = ("J", "Q", "K")
HIGH = ("10", "J", "Q", "K")
# Groups a "single group" shift may pick (besides single ranks).
_GROUPS = (CardGroup("odd"), CardGroup("even"), CardGroup("red"), CardGroup("black"),
           *(CardGroup("suit", suit=s) for s in ("♠", "♥", "♦", "♣")), ranks(*COURT), ranks(*HIGH))
TYPE_ORDER = env.TYPES  # tie-break order when choosing which rule to replace
STAGE_NAMES = ("Probing", "Pressure", "Control", "Onslaught")  # the stages, by index
MIN_AGE_TO_REPLACE = 2
HIGH_PRESSURE = 3

DEFAULTS: dict[str, Any] = {
    # [first round, action chance, rule slots, pressure budget]
    # Softened 2026-10-14 after playtests: later stages, fewer actions, smaller budgets.
    "stages": [[1, 0.40, 1, 1], [5, 0.60, 2, 3], [9, 0.75, 2, 5], [13, 0.85, 3, 6]],
    "weights": {"shift": [45, 35, 25, 20], "fixed": [35, 20, 15, 10], "bust": [0, 10, 15, 15],
                "tie": [0, 10, 10, 10], "bust_outcome": [0, 0, 10, 15], "profit_cap": [0, 0, 10, 15],
                "item_ban": [0, 5, 5, 5], "markup": [20, 10, 5, 5], "hidden": [0, 10, 5, 5]},
    # Per stage. fixed: largest change of one number card and the court/high values;
    # shift: changes of one rank, of one group, of a compound pair, of all cards.
    "pools": [
        {"fixed": {"single": 2, "group": [8, 9]}, "shift": {"rank": [1, -1]},
         "markup": [[10, 3]]},
        {"fixed": {"single": 3, "group": [7, 8]},
         "shift": {"rank": [1, -1], "group": [1, -1], "compound": [1]},
         "bust": [["player", 20, 2], ["dealer", 22, 2]], "tie": ["dealer"], "item_ban": [2],
         "markup": [[20, 3]], "hidden": [2]},
        {"fixed": {"single": 4, "group": [6, 7, 8]},
         "shift": {"rank": [1, -1, 2, -2], "group": [1, -1, 2, -2], "all": [1, -1]},
         "bust": [["player", 19, 2], ["player", 20, 2], ["dealer", 22, 2], ["dealer", 23, 2]],
         "tie": ["dealer"], "bust_outcome": [["dealer", "push", 2]], "profit_cap": [[50, 3]],
         "item_ban": [2], "markup": [[30, 3]], "hidden": [2]},
        {"fixed": {"single": 4, "group": [5, 6, 7]},
         "shift": {"rank": [1, -1, 2, -2], "group": [1, -1, 2, -2], "all": [1, 2, -1]},
         "bust": [["player", 19, 2], ["player", 20, 2], ["dealer", 22, 2], ["dealer", 23, 2]],
         "tie": ["dealer"], "bust_outcome": [["dealer", "push", 2]], "profit_cap": [[40, 3], [30, 3]],
         "item_ban": [3], "markup": [[40, 3]], "hidden": [3]},
    ],
    "pressure": {"fixed": 1, "shift_local_1": 1, "shift_local_2": 2, "shift_compound": 2, "shift_all": 2,
                 "bust": {"player:20": 2, "player:19": 3, "dealer:22": 2, "dealer:23": 3},
                 "tie": 2, "bust_outcome": 3, "profit_cap": {"50": 2, "40": 3, "30": 4},
                 "item_ban": {"2": 2, "3": 3}, "markup": {"10": 1, "20": 1, "30": 2, "40": 2}, "hidden": 2},
    # Actions a type waits after the player clears it / after it ends; actions a replaced effect waits.
    "cooldown_cleared": 2, "cooldown_expired": 1, "cooldown_replaced": 2,
}


@dataclass(frozen=True)
class Stage:
    index: int
    act: float
    slots: int
    budget: int


@dataclass(frozen=True)
class Action:
    kind: str                       # added | replaced | calm
    rule: EnvRule | None = None
    replaced: EnvRule | None = None


class Director:
    def __init__(self, settings: dict[str, Any], seed: int | str, rule_slots: int = 3,
                 money: Fraction = Fraction(1)) -> None:
        def get(key):
            value = settings.get("director." + key, DEFAULTS[key])
            return json.loads(value) if isinstance(value, str) else value
        self.stages = [list(s) for s in get("stages")]
        self.weights = get("weights")
        self.pools = get("pools")
        self.pressures = get("pressure")
        self.cooldowns = {"cleared": int(get("cooldown_cleared")), "expired": int(get("cooldown_expired")),
                          "replaced": int(get("cooldown_replaced"))}
        self.seed = seed
        self.rule_slots = rule_slots
        self.money = money  # Withdrawal Limit caps are chips: they scale with the starting cash (money.py)

    # --- stages and pressure ------------------------------------------------------------------
    def stage(self, round_no: int) -> Stage:
        index = max(i for i, s in enumerate(self.stages) if round_no >= s[0]) if round_no >= self.stages[0][0] else 0
        _, act, slots, budget = self.stages[index]
        return Stage(index, float(act), min(int(slots), self.rule_slots), int(budget))

    def pressure(self, rule: EnvRule) -> int:
        p, table = rule.params, self.pressures
        if rule.type == "fixed":
            return int(table["fixed"])
        if rule.type == "shift":
            shifts = rule.shifts
            if len(shifts) == 2:
                return int(table["shift_compound"])
            group, delta = shifts[0]
            if group.kind == "all":
                return int(table["shift_all"])
            return int(table["shift_local_2" if abs(delta) >= 2 else "shift_local_1"])
        if rule.type == "bust":
            return int(table["bust"][f"{p['actor']}:{p['limit']}"])
        if rule.type == "profit_cap":
            return int(table["profit_cap"][str(p.get("ref", p["cap"]))])
        if rule.type == "item_ban":
            return int(table["item_ban"][str(rule.duration)])
        if rule.type == "markup":
            return int(table["markup"][str(p["pct"])])
        return int(table[rule.type])

    # --- variants -------------------------------------------------------------------------------
    def variants(self, stage: Stage) -> dict[str, list[EnvRule]]:
        """Every rule the stage may create, by type (the weights decide which types are in play)."""
        pool = self.pools[stage.index]
        out: dict[str, list[EnvRule]] = {}
        for kind, spec in pool.items():
            if not self.weights.get(kind, [0] * 4)[stage.index]:
                continue
            out[kind] = [self._scaled(r) for r in _make(kind, spec)]
        return {k: v for k, v in out.items() if v}

    def _scaled(self, rule: EnvRule) -> EnvRule:
        """A Withdrawal Limit's cap in this run's chips; `ref` keeps the profile's amount (pressure key)."""
        if rule.type != "profit_cap" or self.money == 1:
            return rule
        cap = rule.profit_cap
        return replace(rule, params={"cap": chips(cap, self.money), "ref": cap})

    # --- decisions ------------------------------------------------------------------------------
    def decide(self, round_no: int, rules: list[EnvRule], history: list[dict]) -> Action:
        """This round's one action (no state changes here; the table commits it)."""
        stage = self.stage(round_no)
        variants = self.variants(stage)
        adds: dict[str, list[EnvRule]] = {}
        if len(rules) < stage.slots:
            adds = self._legal(variants, rules, None, round_no, history, stage)
        targets = []
        if not adds:
            targets = sorted((r for r in rules if not r.timed and r.age >= MIN_AGE_TO_REPLACE),
                             key=lambda r: (self.pressure(r), -r.age, TYPE_ORDER.index(r.type)))
        if not adds and not targets:
            return Action("calm")
        if self._rng(round_no, "act").random() >= stage.act:
            return Action("calm")
        if adds:
            return Action("added", self._pick(adds, stage, round_no))
        for target in targets:
            rest = [r for r in rules if r is not target]
            legal = self._legal(variants, rest, target, round_no, history, stage)
            if legal:
                return Action("replaced", self._pick(legal, stage, round_no), target)
        return Action("calm")

    def _legal(self, variants, rules, replacing, round_no, history, stage) -> dict[str, list[EnvRule]]:
        blocked_types, blocked_signatures = self._cooling(round_no, history)
        if replacing is not None:
            blocked_signatures = blocked_signatures | {replacing.signature}
        base = sum(self.pressure(r) for r in rules)
        high = sum(1 for r in rules if self.pressure(r) >= HIGH_PRESSURE)
        kinds = {r.type for r in rules}
        out: dict[str, list[EnvRule]] = {}
        for kind, rows in variants.items():
            if kind in kinds or kind in blocked_types:
                continue
            if {kind, *kinds} >= {"hidden", "item_ban"}:
                continue
            legal = []
            for rule in rows:
                pressure = self.pressure(rule)
                if rule.signature in blocked_signatures or base + pressure > stage.budget:
                    continue
                if pressure >= HIGH_PRESSURE and high:
                    continue
                # Within a type, a replacement only strengthens or changes tack (never weakens).
                if replacing is not None and replacing.type == kind and pressure < self.pressure(replacing):
                    continue
                legal.append(rule)
            if legal:
                out[kind] = legal
        return out

    def _cooling(self, round_no: int, history: list[dict]) -> tuple[set[str], set[str]]:
        types, signatures = set(), set()
        for h in history:
            cause, since = h["cause"], round_no - int(h["round"])
            if cause in ("removed", "sacrificed") and since <= self.cooldowns["cleared"]:
                types.add(h["type"])
            elif cause == "expired" and since <= self.cooldowns["expired"]:
                types.add(h["type"])
            elif cause == "replaced" and since <= self.cooldowns["replaced"]:
                signatures.add(h["signature"])
        return types, signatures

    def _pick(self, legal: dict[str, list[EnvRule]], stage: Stage, round_no: int) -> EnvRule:
        kinds = [k for k in TYPE_ORDER if k in legal]
        weights = [self.weights[k][stage.index] for k in kinds]
        kind = self._rng(round_no, "type").choices(kinds, weights=weights)[0]
        return self._rng(round_no, "variant").choice(legal[kind])

    def _rng(self, round_no: int, purpose: str) -> random.Random:
        return random.Random(f"{self.seed}:director:{round_no}:{purpose}")


def _make(kind: str, spec) -> Iterable[EnvRule]:
    """Rules of one type from a pool entry (see DEFAULTS["pools"])."""
    if kind == "fixed":
        for rank in NUMBER_RANKS:
            own = int(rank)
            for value in range(max(1, own - int(spec["single"])), min(10, own + int(spec["single"])) + 1):
                if value != own:
                    yield env.fixed(ranks(rank), value)
        for group in (ranks(*COURT), ranks(*HIGH)):
            for value in spec.get("group", []):
                if value != 10:
                    yield env.fixed(group, int(value))
    elif kind == "shift":
        for delta in spec.get("rank", []):
            for rank in RANKS:
                yield env.shift((ranks(rank), int(delta)))
        for delta in spec.get("group", []):
            for group in _GROUPS:
                yield env.shift((group, int(delta)))
        for delta in spec.get("compound", []):
            d = int(delta)
            yield env.shift((CardGroup("even"), d), (CardGroup("odd"), -d))
            yield env.shift((CardGroup("odd"), d), (CardGroup("even"), -d))
            yield env.shift((CardGroup("red"), d), (CardGroup("black"), -d))
            yield env.shift((CardGroup("black"), d), (CardGroup("red"), -d))
        for delta in spec.get("all", []):
            yield env.shift((CardGroup("all"), int(delta)))
    elif kind == "bust":
        for actor, limit, rounds in spec:
            yield env.bust(str(actor), int(limit), int(rounds))
    elif kind == "tie":
        for result in spec:
            yield env.tie(str(result))
    elif kind == "bust_outcome":
        for side, result, rounds in spec:
            yield env.bust_outcome(str(side), str(result), int(rounds))
    elif kind == "profit_cap":
        for cap, rounds in spec:
            yield env.profit_cap(int(cap), int(rounds))
    elif kind == "item_ban":
        for rounds in spec:
            yield env.item_ban(int(rounds))
    elif kind == "markup":
        for pct, rounds in spec:
            yield env.markup(int(pct), int(rounds))
    elif kind == "hidden":
        for rounds in spec:
            yield env.hidden(int(rounds))
    else:
        raise ValueError(f"Unknown pool type {kind!r}")


def pool_summary(kind: str, spec) -> str:
    """What a stage's pool entry can create, in a few English words (the codex lists it)."""
    def signed(values):
        return "/".join(f"{int(v):+d}" for v in values)
    if kind == "fixed":
        groups = "/".join(str(v) for v in spec.get("group", []))
        return (f"one number card moves by up to {spec['single']}"
                + (f"; J, Q, K or 10, J, Q, K become {groups}" if groups else ""))
    if kind == "shift":
        parts = []
        if spec.get("rank"):
            parts.append(f"one rank {signed(spec['rank'])}")
        if spec.get("group"):
            parts.append(f"one group {signed(spec['group'])}")
        if spec.get("compound"):
            parts.append("even/odd or red/black opposite ±" + "/".join(str(abs(int(v))) for v in spec["compound"]))
        if spec.get("all"):
            parts.append(f"every card {signed(spec['all'])}")
        return "; ".join(parts)
    if kind == "bust":
        return ", ".join(f"{'your' if a == 'player' else 'dealer'} limit {lim} for {r} rounds" for a, lim, r in spec)
    if kind == "tie":
        return ", ".join({"dealer": "ties to the dealer", "player": "ties to you", "push": "ties stand"}[x] for x in spec)
    if kind == "bust_outcome":
        return ", ".join(f"a {side} bust becomes a {result} for {r} rounds" for side, result, r in spec)
    if kind == "profit_cap":
        return ", ".join(f"at most {cap} profit for {r} rounds" for cap, r in spec)
    if kind == "item_ban":
        return ", ".join(f"{r} rounds" for r in spec)
    if kind == "markup":
        return ", ".join(f"+{pct}% for {r} rounds" for pct, r in spec)
    if kind == "hidden":
        return ", ".join(f"{r} rounds" for r in spec)
    return ""


# --- legacy Chaos rules in saves from the first build prototype (§5 mapping) ---------------------------


def from_legacy(snapshot: dict[str, Any]) -> EnvRule | None:
    """The environment rule an old registry Chaos rule maps to, or None when it has no counterpart."""
    rule_id, p = str(snapshot.get("id", "")), dict(snapshot.get("params", {}) or {})
    try:
        if rule_id == "modify_card_value":
            return env.shift((CardGroup("all"), int(p.get("delta", -2))))
        if rule_id == "great_crash":
            return env.fixed(ranks(*HIGH), int(p.get("ten_value", 1)))
        if rule_id == "odd_even_chaos":
            return env.shift((CardGroup("even"), int(p.get("even_delta", 2))), (CardGroup("odd"), int(p.get("odd_delta", -1))))
        if rule_id == "suit_power":
            return env.shift((CardGroup("red"), int(p.get("red_delta", 1))), (CardGroup("black"), int(p.get("black_delta", -1))))
        if rule_id == "fragile_bust":
            return env.bust("player", int(p.get("bust_limit", 18)), 2)
        if rule_id == "reverse_bust":
            return env.bust_outcome("player", "push", 2)
        if rule_id == "tiebreaker_shift":
            return env.tie("dealer" if str(p.get("ties_to", "player")) == "dealer" else "player")
    except (ValueError, KeyError):
        return None
    return None
