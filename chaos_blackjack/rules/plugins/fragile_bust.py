"""Chaos rule: Fragile Table — bust threshold reduced to 18."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass(frozen=True)
class FragileBustModifier:
    id: str = "fragile_bust"
    chaos_flags: frozenset[str] = field(
        default_factory=lambda: frozenset({"fragile_bust"}),
    )

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value


class FragileBustPlugin:
    id = "fragile_bust"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        return FragileBustModifier(id=cls.id)


register_rule("fragile_bust", FragileBustPlugin)

