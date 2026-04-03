"""Chaos rule plugin contract — maps to RuleModifier at runtime."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.rules.modifiers import RuleModifier


@runtime_checkable
class ChaosRulePlugin(Protocol):
    """Plugin class or factory target registered under a string id."""

    id: str

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> RuleModifier:
        """Build a RuleModifier instance for ActiveModifiers stack."""
        ...
