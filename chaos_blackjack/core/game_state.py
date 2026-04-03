"""Pure game state — facts only; mutations go through events / reducers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import NewType


Rank = NewType("Rank", str)


@dataclass(frozen=True)
class Card:
    rank: Rank
    # Suit optional for blackjack logic; kept for display / future extensions
    suit: str = ""

    @staticmethod
    def from_rank(rank: str) -> Card:
        return Card(Rank(rank), "")


class GamePhase(Enum):
    PLAYER_TURN = auto()
    DEALER_TURN = auto()
    RESOLVED = auto()


@dataclass(frozen=True)
class GameState:
    """Immutable snapshot; use `with_*` helpers or `replace()` for transitions."""

    player_hand: tuple[Card, ...]
    dealer_hand: tuple[Card, ...]
    deck: tuple[Card, ...]
    phase: GamePhase

    def with_player_hand(self, hand: tuple[Card, ...]) -> GameState:
        return replace(self, player_hand=hand)

    def with_dealer_hand(self, hand: tuple[Card, ...]) -> GameState:
        return replace(self, dealer_hand=hand)

    def with_deck(self, deck: tuple[Card, ...]) -> GameState:
        return replace(self, deck=deck)

    def with_phase(self, phase: GamePhase) -> GameState:
        return replace(self, phase=phase)
