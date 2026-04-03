"""Chaos rule: Great Crash — all 10/J/Q/K become value 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass(frozen=True)
class GreatCrashModifier:
    id: str = "great_crash"

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        r = card.rank.upper()
        if r in ("10", "J", "Q", "K"):
            return 1
        return base_value


class GreatCrashPlugin:
    id = "great_crash"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        # Params intentionally ignored: this rule is fully deterministic.
        return GreatCrashModifier(id=cls.id)


register_rule("great_crash", GreatCrashPlugin)

