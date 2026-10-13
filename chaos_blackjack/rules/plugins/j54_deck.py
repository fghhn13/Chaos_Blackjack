"""Chaos rules of J-54's table: they change the cards in the deck, not the
rules of blackjack (docs/design/J54_TABLE.md).

The modifier only carries the order; the table applies it once when the rule
is announced (chaos_blackjack/j54/table.py), so card values never change.
Params: `count` (cards), optional `rank` (drawn by the table when missing).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.registry import register_rule

BURN_FLAG = "j54_burn"


@dataclass(frozen=True)
class DeckRuleModifier:
    id: str
    count: int = 0
    rank: str | None = None
    chaos_flags: frozenset[str] = field(default_factory=frozenset)
    deck_rule: bool = True  # handled by the table, not the rule engine

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value


def _count(params: dict[str, Any], default: int) -> int:
    return max(1, min(8, int(params.get("count", default))))


def _rank(params: dict[str, Any]) -> str | None:
    rank = params.get("rank")
    return str(rank).upper() if rank else None


class BurnPlugin:
    id = "j54_burn"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> DeckRuleModifier:
        return DeckRuleModifier(cls.id, chaos_flags=frozenset({BURN_FLAG}))


class SampleInjectionPlugin:
    id = "j54_sample_injection"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> DeckRuleModifier:
        return DeckRuleModifier(cls.id, count=_count(params, 3), rank=_rank(params))


class RedundancyPurgePlugin:
    id = "j54_redundancy_purge"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> DeckRuleModifier:
        return DeckRuleModifier(cls.id, count=_count(params, 3), rank=_rank(params))


class AceInjectionPlugin:
    id = "j54_ace_injection"

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> DeckRuleModifier:
        return DeckRuleModifier(cls.id, count=_count(params, 1), rank="A")


for _plugin in (BurnPlugin, SampleInjectionPlugin, RedundancyPurgePlugin, AceInjectionPlugin):
    register_rule(_plugin.id, _plugin)
