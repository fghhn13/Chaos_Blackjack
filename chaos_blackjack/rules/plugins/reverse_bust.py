"""Registered chaos rule: player bust no longer auto-loses (flag on modifiers)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass
class ReverseBustModifier:
    id: str = "reverse_bust"
    chaos_flags: frozenset[str] = field(
        default_factory=lambda: frozenset({"reverse_bust"}),
    )

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value


class ReverseBustPlugin:
    id = "reverse_bust"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        return ReverseBustModifier(id=cls.id)


register_rule("reverse_bust", ReverseBustPlugin)
