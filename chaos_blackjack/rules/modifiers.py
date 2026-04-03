"""Rule modifiers — AI injects here; state stays untouched."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from chaos_blackjack.core.game_state import Card


@runtime_checkable
class RuleModifier(Protocol):
    """A transient rule perturbation (e.g. 'all 10s count as 8')."""

    id: str

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        """Return the effective value for this card under the modifier."""
        ...


def merge_chaos_flags(modifiers: tuple[RuleModifier, ...]) -> frozenset[str]:
    out: set[str] = set()
    for m in modifiers:
        cf = getattr(m, "chaos_flags", None)
        if cf:
            out |= cf
    return frozenset(out)


@dataclass
class ActiveModifiers:
    """Stack of modifiers; extend with TTL / priority as needed."""

    items: tuple[RuleModifier, ...] = field(default_factory=tuple)

    def with_added(self, modifier: RuleModifier) -> ActiveModifiers:
        return ActiveModifiers(items=self.items + (modifier,))

    def with_cleared(self) -> ActiveModifiers:
        return ActiveModifiers(items=())

    def chaos_flags(self) -> frozenset[str]:
        return merge_chaos_flags(self.items)
