"""Chaos rule: Great Crash — all 10/J/Q/K become value 1.

Params: `ten_value` (balance profile), the value 10/J/Q/K count as.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass(frozen=True)
class GreatCrashModifier:
    id: str = "great_crash"
    ten_value: int = 1

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        r = card.rank.upper()
        if r in ("10", "J", "Q", "K"):
            return self.ten_value
        return base_value


class GreatCrashPlugin:
    id = "great_crash"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        return GreatCrashModifier(id=cls.id, ten_value=int(params.get("ten_value", 1)))


register_rule("great_crash", GreatCrashPlugin)

