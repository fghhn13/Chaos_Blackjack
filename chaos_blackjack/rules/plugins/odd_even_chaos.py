"""Chaos rule: Odd-Even Chaos — even ranks get +2, odd ranks get -1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass(frozen=True)
class OddEvenChaosModifier:
    id: str = "odd_even_chaos"

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        r = card.rank.upper()
        # Only apply to the numeric ranks mentioned in the spec.
        if r == "2":
            return base_value + 2
        if r == "4":
            return base_value + 2
        if r == "6":
            return base_value + 2
        if r == "8":
            return base_value + 2
        if r == "3":
            return base_value - 1
        if r == "5":
            return base_value - 1
        if r == "7":
            return base_value - 1
        if r == "9":
            return base_value - 1
        return base_value


class OddEvenChaosPlugin:
    id = "odd_even_chaos"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        # Params intentionally ignored: this rule is fully deterministic.
        return OddEvenChaosModifier(id=cls.id)


register_rule("odd_even_chaos", OddEvenChaosPlugin)

