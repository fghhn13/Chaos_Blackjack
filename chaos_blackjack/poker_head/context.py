"""The narrow view of a round that build effects and item handlers act through.

Effects and handlers never reach into the controller's private members: they
read and change the round only through these methods, so the controller can
change its internals without touching 41 products (docs/design/ITEM_ARCHITECTURE.md §5).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chaos_blackjack.app.choice import Choice
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GameState

if TYPE_CHECKING:
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.poker_head.table import PokerHeadTable, RoundState


class BuildContext:
    def __init__(self, table: "PokerHeadTable") -> None:
        self.table = table

    @property
    def _c(self) -> "GameController":
        return self.table.c

    # --- the table's own state -----------------------------------------------

    def setting(self, key: str):
        return self.table.setting(key)

    def param(self, item_id: str, key: str):
        return self.table.param(item_id, key)

    def has(self, item_id: str) -> bool:
        """The core or an equipped permanent."""
        return item_id in self.table.loadout.active()

    @property
    def round(self) -> "RoundState":
        return self.table.round

    def prepared(self, item_id: str) -> bool:
        return item_id in self.table.round.preparations

    def prepare(self, item_id: str) -> None:
        """A consumable's effect lasts until this round settles."""
        self.table.round.preparations.append(item_id)

    def message(self, text: str) -> None:
        self.table.message(text)

    # --- the round ------------------------------------------------------------

    @property
    def phase(self) -> TablePhase:
        return self._c.phase

    @property
    def betting(self) -> bool:
        return self._c.phase == TablePhase.BETTING

    @property
    def state(self) -> GameState | None:
        return self._c.state

    def set_state(self, state: GameState) -> None:
        self._c.state = state

    @property
    def deck(self) -> tuple[Card, ...]:
        return self._c.state.deck if self._c.state is not None else ()

    @property
    def player_hand(self) -> tuple[Card, ...]:
        return self._c.state.player_hand if self._c.state is not None else ()

    @property
    def dealer_hand(self) -> tuple[Card, ...]:
        return self._c.state.dealer_hand if self._c.state is not None else ()

    @property
    def bet(self) -> int:
        return self._c.run.current_bet

    @property
    def round_no(self) -> int:
        return self._c.run.round

    @property
    def cash(self) -> int:
        return self._c.run.money

    def add_cash(self, chips: int) -> None:
        self._c.run.money += chips

    def can_bet_with(self, cash: int) -> bool:
        return self._c.can_bet(cash)

    def value(self, hand: tuple[Card, ...], actor: str = "player") -> int:
        return self._c.hand_value(hand, actor)

    def is_bust(self, value: int, actor: str = "player") -> bool:
        return self._c.loop.rules.is_bust(value, self._c.loop.context(actor))

    def dealer_hole_value(self) -> int:
        """The hole card's effective value in the dealer's hand: Chaos value rules
        apply, and an ace drops to low when the dealer's hand would bust."""
        hand = self.dealer_hand
        ranges = [self._c.loop.rules.card_range(card, self._c.loop.context("dealer")) for card in hand]
        values = [high for high, _ in ranges]
        total = sum(values)
        for i, (high, low) in enumerate(ranges):
            if high > low and self.is_bust(total, "dealer"):
                values[i] = low
                total -= high - low
        return values[1]

    def can(self, action: str) -> bool:
        """Whether a hand action (double, surrender, ...) is allowed now."""
        return action in self._c.base_actions()

    @property
    def hole_revealed(self) -> bool:
        return self._c.hole_revealed

    def reveal_hole(self) -> None:
        self._c.hole_revealed = True

    def ask(self, choice: Choice) -> None:
        self._c.ask(choice)

    def surrender(self) -> None:
        self._c.surrender()
