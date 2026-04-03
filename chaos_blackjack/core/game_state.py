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
    chaos_budget_remaining: int = 3
    inventory: tuple[str, ...] = ()

    def with_player_hand(self, hand: tuple[Card, ...]) -> GameState:
        return replace(self, player_hand=hand)

    def with_dealer_hand(self, hand: tuple[Card, ...]) -> GameState:
        return replace(self, dealer_hand=hand)

    def with_deck(self, deck: tuple[Card, ...]) -> GameState:
        return replace(self, deck=deck)

    def with_phase(self, phase: GamePhase) -> GameState:
        return replace(self, phase=phase)

    def with_chaos_budget(self, n: int) -> GameState:
        return replace(self, chaos_budget_remaining=n)

    def with_inventory(self, inv: tuple[str, ...]) -> GameState:
        return replace(self, inventory=inv)
