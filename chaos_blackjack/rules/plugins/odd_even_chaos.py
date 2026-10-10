"""Chaos rule: Odd-Even Chaos — even ranks get +2, odd ranks get -1.

Only the numeric ranks 2-9 change. Params: `even_delta`, `odd_delta` (balance profile).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


_EVEN = {"2", "4", "6", "8"}
_ODD = {"3", "5", "7", "9"}


@dataclass(frozen=True)
class OddEvenChaosModifier:
    id: str = "odd_even_chaos"
    even_delta: int = 2
    odd_delta: int = -1

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        r = card.rank.upper()
        if r in _EVEN:
            return base_value + self.even_delta
        if r in _ODD:
            return base_value + self.odd_delta
        return base_value


class OddEvenChaosPlugin:
    id = "odd_even_chaos"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        return OddEvenChaosModifier(
            id=cls.id,
            even_delta=int(params.get("even_delta", 2)),
            odd_delta=int(params.get("odd_delta", -1)),
        )


register_rule("odd_even_chaos", OddEvenChaosPlugin)

