"""Chaos rule: Tiebreaker Shift — ties go to Player (or Dealer)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule
from chaos_blackjack.rules.modifiers import RuleModifier


@dataclass(frozen=True)
class TiebreakerShiftModifier:
    id: str = "tiebreaker_shift"
    chaos_flags: frozenset[str] = field(
        default_factory=lambda: frozenset({"player_wins_ties"}),
    )

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value


class TiebreakerShiftPlugin:
    id = "tiebreaker_shift"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        ties_to = str(params.get("ties_to", "player")).lower().strip()
        if ties_to == "dealer":
            mod = TiebreakerShiftModifier(
                id=cls.id,
                chaos_flags=frozenset({"dealer_wins_ties"}),
            )
        else:
            mod = TiebreakerShiftModifier(
                id=cls.id,
                chaos_flags=frozenset({"player_wins_ties"}),
            )
        return mod


register_rule("tiebreaker_shift", TiebreakerShiftPlugin)

