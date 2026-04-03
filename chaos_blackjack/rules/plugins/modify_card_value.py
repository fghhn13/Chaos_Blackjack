"""Registered chaos rule: shift effective rank values by delta."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass
class ModifyCardValueModifier:
    id: str
    delta: int

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value + self.delta


class ModifyCardValuePlugin:
    id = "modify_card_value"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        delta = int(params.get("delta", -2))
        return ModifyCardValueModifier(id=cls.id, delta=delta)


register_rule("modify_card_value", ModifyCardValuePlugin)
