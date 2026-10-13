"""J-54's table (demo): a deck that lasts the whole run (docs/design/J54_TABLE.md).

* The deck's cards persist between rounds; every round shuffles all of them.
* A protocol drawn per run is the goal: Single Capture (draw the Joker
  yourself) or Capital (reach a large bankroll).
* The Joker starts sealed; the Start Experiment contract puts it in the deck.
  If the dealer would get it, J-54 takes it back into the deck and adds low
  cards as a penalty.
* A compute fee is charged before every bet and grows with the round; J-54
  adds low cards after every round (entropy), so idle rounds only hurt.
* The shop sells contracts (j54/contracts.py) and the Chaos AI's rules change
  the deck (rules/plugins/j54_deck.py).

Random choices use a counter-seeded RNG, so a run replays identically however
it is saved and resumed.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.table_mechanics import Notify, TableMechanics
from chaos_blackjack.core.game_state import Card, GameState, Rank
from chaos_blackjack.j54.contracts import CONTRACTS, contract_params, describe, effect_text
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.plugins.j54_deck import BURN_FLAG

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.economy import RunState

TABLE_EVENT = NoticeKind.TABLE_EVENT  # notice kind of everything the table announces
JOKER = "JK"
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("♠", "♥", "♦", "♣")
LOW_RANKS = ("2", "3", "4", "5", "6")
HIGH_RANKS = ("10", "J", "Q", "K", "A")
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


def is_joker(card: Card) -> bool:
    return str(card.rank).upper() == JOKER


def joker() -> Card:
    return Card(Rank(JOKER), "")


def standard_cards() -> list[Card]:
    return [Card(Rank(r), s) for s in SUITS for r in RANKS]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


class J54Table(TableMechanics):
    id = "j54"

    @classmethod
    def goal(cls, config: "RunConfig") -> str:
        settings = {**DEFAULTS, **{k[4:]: v for k, v in config.mode_settings.items() if k.startswith("j54.")}}
        return f"A random protocol: draw the Joker, or reach {settings['capital_target']} chips"

    def __init__(self, config: "RunConfig", seed: int | str, notify: Notify) -> None:
        super().__init__(config, seed, notify)
        self.settings = {**DEFAULTS, **{k[4:]: v for k, v in config.mode_settings.items() if k.startswith("j54.")}}
        protocols = [p.strip() for p in str(self.settings["protocols"]).split(",") if p.strip() in PROTOCOLS]
        self.protocol = random.Random(f"{seed}:j54:protocol").choice(protocols or ["capture"])
        self.cards: list[Card] = standard_cards()
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

    def _room(self) -> int:
        """Cards that may still be deleted before the deck hits its minimum."""
        return max(0, len(self.cards) - int(self.settings["min_deck"]))

    def _add(self, ranks: tuple[str, ...], count: int, rank: str | None = None) -> list[Card]:
        rng = self._rng()
        added = [Card(Rank(rank or rng.choice(ranks)), rng.choice(SUITS)) for _ in range(count)]
        self.cards.extend(added)
        return added

    def _delete(self, cards: list[Card]) -> list[Card]:
        """Remove these cards from the deck (one copy each), never below the minimum."""
        removed = []
        for card in cards:
            if self._room() <= 0:
                break
            if card in self.cards:
                self.cards.remove(card)
                removed.append(card)
        return removed

    def _delete_random(self, count: int, ranks: tuple[str, ...] | None = None) -> list[Card]:
        pool = [c for c in self.cards if ranks is None or str(c.rank) in ranks]
        picked = self._rng().sample(pool, min(count, len(pool)))
        return self._delete(picked)

    @staticmethod
    def _names(cards: list[Card]) -> str:
        # Ranks only, like the other table log lines (the UI font has no suit glyphs).
        return ", ".join(str(c.rank) for c in cards) if cards else "nothing"

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

    def info(self, run: "RunState") -> tuple[tuple[str, str], ...]:
        rows: list[tuple[str, str]] = [("Protocol", PROTOCOLS[self.protocol])]
        if self.protocol == "capital":
            rows.append(("Goal", f"Reach {self.capital_target} chips"))
        else:
            if self.captured >= self.jokers_needed:
                state = "captured"
            elif self.jokers_in_deck:
                state = "in the deck"
            else:
                state = "sealed"
            rows.append(("Joker", state))
        rows.append(("Deck", _plural(self.deck_size, "card")))
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
        params = contract_params(item_id, self.config.item_params)
        name = CONTRACTS[item_id].name
        if params["trigger"] == "now":
            self._fire(item_id, params)
            return f"Signed {name}."
        self.pending.append(item_id)
        return f"Signed {name}: it takes effect on your next {params['trigger']}."

    def _fire(self, item_id: str, params: dict[str, Any]) -> None:
        effect, count = params["effect"], int(params.get("count", 1))
        name = CONTRACTS[item_id].name
        if effect == "delete_random":
            gone = self._delete_random(count)
            self._say(f"{name}: deleted {self._names(gone)}.", effect=effect, cards=len(gone))
        elif effect == "delete_low":
            gone = self._delete_random(count, LOW_RANKS)
            self._say(f"{name}: deleted {self._names(gone)}.", effect=effect, cards=len(gone))
        elif effect == "add_high":
            added = self._add(HIGH_RANKS, count)
            self._say(f"{name}: added {self._names(added)}.", effect=effect, cards=len(added))
        elif effect == "freeze":
            self.freeze += int(params.get("rounds", 1))
            self._say(f"{name}: J-54 adds no cards for {_plural(self.freeze, 'round')}.", effect=effect)
        elif effect == "release_jokers":
            self.jokers_in_deck += self.jokers_sealed
            self.jokers_sealed = 0
            self.experiment = True
            self._say("Experiment started: the Joker is in the deck.", effect=effect)
        else:
            raise ValueError(f"{name}: cannot {effect_text(params)}")

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
                added = self._add(LOW_RANKS, penalty)
                self._say(f"The dealer drew the Joker. J-54 shuffles it back and adds {self._names(added)}.",
                          effect="dealer_joker")
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
            rid, count = str(m.id), int(getattr(m, "count", 1))
            if rid in ("j54_sample_injection", "j54_ace_injection"):
                rank = getattr(m, "rank", None) or self._rng().choice(RANKS)
                added = self._add(RANKS, count, rank)
                rng = self._rng()
                for card in added:
                    deck.insert(rng.randint(0, len(deck)), card)
                items[i] = replace(m, rank=rank)
                label = "Ace injection" if rid == "j54_ace_injection" else "Sample injection"
                self._say(f"{label}: {self._names(added)} added to the deck.", effect=rid)
            elif rid == "j54_redundancy_purge":
                present = sorted({str(c.rank) for c in deck if not is_joker(c)}, key=RANKS.index)
                rank = getattr(m, "rank", None) or (self._rng().choice(present) if present else "2")
                victims = [c for c in deck if str(c.rank) == rank][:count]
                gone = self._delete(victims)
                for card in gone:
                    deck.remove(card)
                items[i] = replace(m, rank=rank)
                self._say(f"Redundancy purge: {self._names(gone)} removed from the deck.", effect=rid)
        self._applied_rules = len(items)
        return replace(state, deck=tuple(deck)), ActiveModifiers(items=tuple(items))

    def after_settle(self, state: GameState, outcome: str, modifiers: ActiveModifiers, run: "RunState") -> None:
        if self.won:
            return
        if BURN_FLAG in modifiers.chaos_flags():
            gone = self._delete([c for c in (*state.player_hand, *state.dealer_hand) if not is_joker(c)])
            self._say(f"Burn protocol: {self._names(gone)} leave the deck.", effect="burn")
        happened = {"win"} if outcome in ("player", "blackjack") else {"loss"} if outcome == "dealer" else set()
        if outcome == "blackjack":
            happened.add("natural")
        for item_id in list(self.pending):
            params = contract_params(item_id, self.config.item_params)
            if params["trigger"] in happened:
                self.pending.remove(item_id)
                self._fire(item_id, params)
        if self.freeze:
            self.freeze -= 1
            self._say("Freeze contract: J-54 adds no cards this round.", effect="freeze")
            return
        n = int(self.settings["entropy_experiment" if self.experiment else "entropy"])
        if n:
            added = self._add(LOW_RANKS, n)
            self._say(f"Entropy: J-54 adds {self._names(added)} to the deck.", effect="entropy")

    # --- save -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "cards": [[str(c.rank), c.suit] for c in self.cards],
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
