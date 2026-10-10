"""Chaos rule: Suit Power — red suits +1, black suits -1.

Params: `red_delta`, `black_delta` (balance profile).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


_RED_SUITS = {"♥", "♦"}
_BLACK_SUITS = {"♠", "♣"}
_RED_SUITS_ALT = {"h", "d"}  # Accept ASCII suits too.
_BLACK_SUITS_ALT = {"s", "c"}


@dataclass(frozen=True)
class SuitPowerModifier:
    id: str = "suit_power"
    red_delta: int = 1
    black_delta: int = -1

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        suit = (card.suit or "").strip()
        suit_lower = suit.lower()
        if suit in _RED_SUITS or suit_lower in _RED_SUITS_ALT:
            return base_value + self.red_delta
        if suit in _BLACK_SUITS or suit_lower in _BLACK_SUITS_ALT:
            return base_value + self.black_delta
        return base_value


class SuitPowerPlugin:
    id = "suit_power"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        return SuitPowerModifier(
            id=cls.id,
            red_delta=int(params.get("red_delta", 1)),
            black_delta=int(params.get("black_delta", -1)),
        )


register_rule("suit_power", SuitPowerPlugin)

