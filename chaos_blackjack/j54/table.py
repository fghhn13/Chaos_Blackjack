"""J-54's table (demo): a deck that lasts the whole run (docs/design/J54_TABLE.md).

* The deck's cards persist between rounds; every round shuffles all of them.
  Its make-up is public (`deck_counts`); its order never is.
* A protocol drawn per run is the goal: Single Capture (draw the Joker
  yourself) or Capital (reach a chip target).
* The Joker starts sealed; the Start Experiment contract puts it in the deck.
  If the dealer would get it, J-54 takes it back into the deck and adds low
  cards as a penalty.
* A compute fee is charged before every bet and grows with the round; J-54
  adds low cards after every round (entropy), so idle rounds only hurt.
* Rules (rules/plugins/j54_deck.py), contracts (j54/contracts.py), entropy
  and the penalty are all deck operations (j54/deck_ops.py).

Random choices use a counter-seeded RNG, so a run replays identically however
it is saved and resumed.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.table_mechanics import Notify, TableMechanics, register_table
from chaos_blackjack.core.game_state import Card, GameState, Rank
from chaos_blackjack.j54.contracts import CONTRACTS, contract_spec, describe
from chaos_blackjack.j54.deck_ops import JOKER, RANKS, SUITS, DeckContext, DeckOp, apply, is_joker
from chaos_blackjack.rules.modifiers import ActiveModifiers

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.economy import RunState

TABLE_EVENT = NoticeKind.TABLE_EVENT  # notice kind of everything the table announces
START_EXPERIMENT = "j54_start_experiment"

PROTOCOLS: dict[str, str] = {"capture": "Single Capture", "capital": "Capital"}

# Used when a balance profile has no mode.j54.* settings (e.g. cloned before them).
DEFAULTS: dict[str, Any] = {
    "protocols": "capture,capital",
    "capital_target": 250,
    "experiment_jokers": 1,
    "fee_steps": "0,1,2,4,8",
    "fee_step_rounds": 4,
    "entropy": 1,
    "entropy_experiment": 2,
    "dealer_joker_penalty": 1,
    "min_deck": 12,
}


def joker() -> Card:
    return Card(Rank(JOKER), "")


def standard_cards() -> list[Card]:
    return [Card(Rank(r), s) for s in SUITS for r in RANKS]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _settings(config: "RunConfig") -> dict[str, Any]:
    return {**DEFAULTS, **{k[4:]: v for k, v in config.mode_settings.items() if k.startswith("j54.")}}


class J54Table(TableMechanics):
    id = "j54"

    @classmethod
    def goal(cls, config: "RunConfig") -> str:
        return f"A random protocol: draw the Joker, or reach {_settings(config)['capital_target']} chips"

    def __init__(self, config: "RunConfig", seed: int | str, notify: Notify) -> None:
        super().__init__(config, seed, notify)
        self.settings = _settings(config)
        protocols = [p.strip() for p in str(self.settings["protocols"]).split(",") if p.strip() in PROTOCOLS]
        self.protocol = random.Random(f"{seed}:j54:protocol").choice(protocols or ["capture"])
        self.cards: list[Card] = standard_cards()
        self.removed: list[Card] = []     # cards deleted during the run (Data Backflow returns them)
        jokers = int(self.settings["experiment_jokers"]) if self.protocol == "capture" else 0
        self.jokers_sealed = jokers
        self.jokers_needed = jokers
        self.jokers_in_deck = 0
        self.captured = 0
        self.experiment = False
        self.pending: list[str] = []
        self.freeze = 0
        self.won = False
        self._ops = 0             # RNG counter (saved), see _rng
        self._applied_rules = 0   # deck rules of this round already applied

    # --- helpers ----------------------------------------------------------

    def _rng(self) -> random.Random:
        self._ops += 1
        return random.Random(f"{self.seed}:j54:{self._ops}")

    def _say(self, text: str, **data: Any) -> None:
        self.notify(TABLE_EVENT, text, {"table": self.id, **data})

    @property
    def deck_size(self) -> int:
        return len(self.cards) + self.jokers_in_deck

    @property
    def capital_target(self) -> int:
        return int(self.settings["capital_target"])

    def _run(self, op: DeckOp, state: GameState | None = None, deck: list[Card] | None = None):
        """Apply a deck operation to the run's deck (and this round's, when `deck` is given)."""
        ctx = DeckContext(self.cards, self.removed, self._rng, int(self.settings["min_deck"]), deck,
                          state.player_hand if state else (), state.dealer_hand if state else ())
        return apply(op, ctx)

    def deck_counts(self) -> tuple[tuple[str, int], ...]:
        """How many cards of each rank the deck holds (all of them, whatever is in play)."""
        return tuple((r, sum(1 for c in self.cards if str(c.rank) == r)) for r in RANKS)

    # --- run --------------------------------------------------------------

    def start(self, run: "RunState") -> None:
        run.objective = f"j54_{self.protocol}"
        run.target_money = self.capital_target if self.protocol == "capital" else 0

    def summary(self) -> list[str]:
        fee = "Every round costs a compute fee, and after each hand I add low cards to the deck. Waiting only makes it worse."
        if self.protocol == "capital":
            return [f"Protocol: Capital. Reach {self.capital_target} chips. Reshape my deck in your favour with contracts.",
                    fee]
        return [f"Protocol: Single Capture. One Joker is sealed in my archive. Sign Start Experiment to release it "
                "into the deck, then draw it yourself. If I draw it, I keep it a little longer.",
                fee]

    def joker_state(self) -> str:
        if self.protocol != "capture":
            return "none"
        if self.captured >= self.jokers_needed:
            return "captured"
        return "in the deck" if self.jokers_in_deck else "sealed"

    def info(self, run: "RunState") -> tuple[tuple[str, str], ...]:
        rows: list[tuple[str, str]] = [("Protocol", PROTOCOLS[self.protocol])]
        if self.protocol == "capital":
            rows.append(("Goal", f"Reach {self.capital_target} chips"))
        else:
            rows.append(("Joker", self.joker_state()))
        rows.append(("Deck", _plural(self.deck_size, "card")))
        if self.removed:
            rows.append(("Removed", _plural(len(self.removed), "card")))
        rows.append(("Fee", f"{self.fee(run.round)} per round"))
        if self.pending:
            rows.append(("Contracts", ", ".join(CONTRACTS[c].name for c in self.pending)))
        if self.freeze:
            rows.append(("Freeze", _plural(self.freeze, "round")))
        return tuple(rows)

    def victory(self, run: "RunState") -> str | None:
        if self.protocol == "capture" and self.won:
            return "Sample captured. The experiment is complete."
        if self.protocol == "capital" and run.money >= self.capital_target:
            return f"Capital protocol complete: {run.money} chips."
        return None

    # --- economy ----------------------------------------------------------

    def fee(self, round_no: int) -> int:
        steps = [int(x) for x in str(self.settings["fee_steps"]).split(",") if x.strip()] or [0]
        step = (max(1, round_no) - 1) // max(1, int(self.settings["fee_step_rounds"]))
        if step < len(steps):
            return steps[step]
        return steps[-1] * 2 ** (step - len(steps) + 1)

    def min_bet(self, round_no: int) -> int:
        return self.fee(round_no)

    # --- shop -------------------------------------------------------------

    def sells(self, item_id: str) -> bool:
        return item_id in CONTRACTS

    def stockable(self, item_id: str) -> bool:
        if item_id == START_EXPERIMENT:
            return self.protocol == "capture" and not self.experiment
        return self.sells(item_id)

    def pinned(self) -> tuple[str, ...]:
        return (START_EXPERIMENT,) if self.stockable(START_EXPERIMENT) else ()

    def describe(self, item_id: str) -> str:
        return describe(item_id, self.config.item_params)

    def buy(self, item_id: str, run: "RunState") -> str:
        spec = contract_spec(item_id, self.config.item_params)
        name = CONTRACTS[item_id].name
        if spec.trigger == "now":
            self._fire(item_id)
            return f"Signed {name}."
        self.pending.append(item_id)
        return f"Signed {name}: it takes effect on your next {spec.trigger}."

    def _fire(self, item_id: str) -> None:
        spec = contract_spec(item_id, self.config.item_params)
        name = CONTRACTS[item_id].name
        if spec.effect == "freeze":
            self.freeze += spec.rounds
            self._say(f"{name}: J-54 adds no cards for {_plural(self.freeze, 'round')}.", effect="freeze")
        elif spec.effect == "release_jokers":
            self.jokers_in_deck += self.jokers_sealed
            self.jokers_sealed = 0
            self.experiment = True
            self._say("Experiment started: the Joker is in the deck.", effect="release_jokers")
        else:
            assert spec.op is not None
            result = self._run(spec.op)
            self._say(f"{name}: {result.summary(spec.op)}.", effect=spec.op.op, cards=len(result.cards))

    # --- round ------------------------------------------------------------

    def round_cards(self) -> tuple[Card, ...]:
        self._applied_rules = 0
        return tuple(self.cards) + (joker(),) * self.jokers_in_deck

    @property
    def ends_hand(self) -> bool:
        return self.won

    def after_cards(self, state: GameState) -> GameState:
        deck = list(state.deck)
        player = [c for c in state.player_hand if not is_joker(c)]
        caught = len(state.player_hand) - len(player)
        if caught:
            self.captured += caught
            self.jokers_in_deck -= caught
            self.won = self.protocol == "capture" and self.captured >= self.jokers_needed
            self._say("You drew the Joker. Sample captured.", effect="capture")
            while not self.won and len(player) < len(state.player_hand) and deck:
                player.append(self._take(deck))
        dealer = list(state.dealer_hand)
        for i, card in enumerate(dealer):
            if is_joker(card) and deck:
                dealer[i] = self._take(deck)
                deck.insert(self._rng().randint(min(1, len(deck)), len(deck)), card)  # not back on top
                penalty = int(self.settings["dealer_joker_penalty"])
                added = self._run(DeckOp("add", "low", penalty)).cards if penalty else []
                extra = f" and adds {', '.join(str(c.rank) for c in added)}" if added else ""
                self._say(f"The dealer drew the Joker. J-54 shuffles it back{extra}.", effect="dealer_joker")
        return replace(state, player_hand=tuple(player), dealer_hand=tuple(dealer), deck=tuple(deck))

    @staticmethod
    def _take(deck: list[Card]) -> Card:
        """The first card of `deck` that is not a Joker (removed from it)."""
        for i, card in enumerate(deck):
            if not is_joker(card):
                return deck.pop(i)
        return deck.pop(0)

    def after_chaos(self, state: GameState, modifiers: ActiveModifiers) -> tuple[GameState, ActiveModifiers]:
        items = list(modifiers.items)
        deck = list(state.deck)
        for i in range(self._applied_rules, len(items)):
            m = items[i]
            if not getattr(m, "deck_rule", False):
                continue
            if m.op.when != "now":
                self._say(f"{m.name}: {m.op.describe()}.", effect=m.id)
                continue
            result = self._run(m.op, state, deck)
            items[i] = m.with_rank(result.rank or m.rank)
            self._say(f"{m.name}: {result.summary(m.op)}.", effect=m.id, cards=len(result.cards))
        self._applied_rules = len(items)
        return replace(state, deck=tuple(deck)), ActiveModifiers(items=tuple(items))

    def after_settle(self, state: GameState, outcome: str, modifiers: ActiveModifiers, run: "RunState") -> None:
        if self.won:
            return
        for m in modifiers.items:  # rules that act after the hand (e.g. Burn Protocol)
            if getattr(m, "deck_rule", False) and m.op.when == "round_end":
                result = self._run(m.op, state)
                self._say(f"{m.name}: {result.summary(m.op)}.", effect=m.id, cards=len(result.cards))
        happened = {"win"} if outcome in ("player", "blackjack") else {"loss"} if outcome == "dealer" else set()
        if outcome == "blackjack":
            happened.add("natural")
        for item_id in list(self.pending):
            if contract_spec(item_id, self.config.item_params).trigger in happened:
                self.pending.remove(item_id)
                self._fire(item_id)
        if self.freeze:
            self.freeze -= 1
            self._say("Freeze contract: J-54 adds no cards this round.", effect="freeze")
            return
        n = int(self.settings["entropy_experiment" if self.experiment else "entropy"])
        if n:
            op = DeckOp("add", "low", n)
            self._say(f"Entropy: J-54 {self._run(op).summary(op)}.", effect="entropy")

    # --- save -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "cards": [[str(c.rank), c.suit] for c in self.cards],
            "removed": [[str(c.rank), c.suit] for c in self.removed],
            "jokers_sealed": self.jokers_sealed,
            "jokers_in_deck": self.jokers_in_deck,
            "jokers_needed": self.jokers_needed,
            "captured": self.captured,
            "experiment": self.experiment,
            "pending": list(self.pending),
            "freeze": self.freeze,
            "won": self.won,
            "ops": self._ops,
            "applied_rules": self._applied_rules,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.protocol = str(data.get("protocol", self.protocol))
        self.cards = [Card(Rank(r), s) for r, s in data.get("cards", [])]
        self.removed = [Card(Rank(r), s) for r, s in data.get("removed", [])]
        self.jokers_sealed = int(data.get("jokers_sealed", 0))
        self.jokers_in_deck = int(data.get("jokers_in_deck", 0))
        self.jokers_needed = int(data.get("jokers_needed", 0))
        self.captured = int(data.get("captured", 0))
        self.experiment = bool(data.get("experiment", False))
        self.pending = [str(c) for c in data.get("pending", []) if c in CONTRACTS]
        self.freeze = int(data.get("freeze", 0))
        self.won = bool(data.get("won", False))
        self._ops = int(data.get("ops", 0))
        self._applied_rules = int(data.get("applied_rules", 0))


register_table("j54", J54Table)
