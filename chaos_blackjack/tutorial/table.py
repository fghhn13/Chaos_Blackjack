"""The practice table (mode "tutorial"): scripted hands that each teach one button (tutorial/lessons.py).

* `before_bet` deals the lesson's cards in order (the rest of the deck follows, shuffled).
* `augment_actions` leaves only the taught button on the first decision (and `Lesson.then` after it).
* After the last lesson the run is won ("Practice over"); the GUI then shows the strategy chart.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.table_mechanics import Notify, TableMechanics, register_table
from chaos_blackjack.app.view import Action
from chaos_blackjack.content.basic_strategy import CELL_NAMES, advice, cell
from chaos_blackjack.core.game_state import Card, GameState, Rank
from chaos_blackjack.tutorial.lessons import LESSONS, Lesson

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.economy import RunState

PLAY = frozenset({Action.HIT, Action.STAND, Action.DOUBLE, Action.SURRENDER, Action.USE_ITEM})
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("♠", "♥", "♦", "♣")


def card(code: str) -> Card:
    return Card(Rank(code[:-1]), code[-1])


class TutorialTable(TableMechanics):
    id = "tutorial"

    @classmethod
    def goal(cls, config: "RunConfig") -> str:
        return f"Play {len(LESSONS)} practice hands"

    def __init__(self, config: "RunConfig", seed: int | str, notify: Notify) -> None:
        super().__init__(config, seed, notify)
        self.played = 0          # hands settled

    def bind(self, controller: "GameController") -> None:
        self.c = controller

    # --- lessons ----------------------------------------------------------

    @property
    def lesson(self) -> Lesson | None:
        """The hand being played (or bet on next); None once the practice is over."""
        return LESSONS[self.played] if self.played < len(LESSONS) else None

    @property
    def finished(self) -> bool:
        return self.played >= len(LESSONS)

    def summary(self) -> list[str]:
        return []

    def before_bet(self) -> tuple[Card, ...]:
        lesson = self.lesson
        scripted = [card(c) for c in lesson.deal] if lesson is not None else []
        rest = [Card(Rank(r), s) for s in SUITS for r in RANKS]
        rest = [c for c in rest if c not in scripted]
        random.Random(f"{self.seed}:tutorial:{self.played}").shuffle(rest)
        return tuple(scripted + rest)

    def augment_actions(self, actions: frozenset[str]) -> frozenset[str]:
        lesson = self.lesson
        if lesson is None or lesson.action is None or self.c.state is None:
            return actions
        first = len(self.c.state.player_hand) == 2
        allowed = lesson.action if first else lesson.then
        return (actions - PLAY) | (actions & {allowed} if allowed else frozenset())

    def advice(self) -> str:
        """What the strategy chart says for the hand on the table now ("" outside your turn)."""
        st = self.c.state
        if st is None or len(st.dealer_hand) < 1:
            return ""
        total = self.c.hand_value(st.player_hand)
        hard = sum(1 if c.rank == "A" else 10 if c.rank in ("J", "Q", "K") else int(c.rank) for c in st.player_hand)
        soft = hard != total and total <= 21
        up = str(st.dealer_hand[0].rank)
        actions = self.c.base_actions()
        move = advice(total, soft, up, can_double=Action.DOUBLE in actions, can_surrender=Action.SURRENDER in actions)
        hand = f"soft {total}" if soft else f"{total}"
        shown = "an ace" if up == "A" else f"a {up}"
        name = CELL_NAMES[cell(total, soft, up)]
        if name.lower() != move:
            name = f"{name}; you can't, so {move.capitalize()}"
        return f"The chart says, for {hand} against {shown}: {name}."

    # --- hooks ------------------------------------------------------------

    def after_settle(self, state: GameState, outcome: str, modifiers, run: "RunState") -> None:
        self.played += 1

    def victory(self, run: "RunState") -> str | None:
        return "Practice over." if self.finished else None

    def to_dict(self) -> dict[str, Any]:
        return {"played": self.played}

    def restore(self, data: dict[str, Any]) -> None:
        self.played = int(data.get("played", 0))


register_table("tutorial", TutorialTable)
