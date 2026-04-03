"""Registry + plugins (requires conftest auto_load)."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.registry.registry import get_registry


def test_rules_registered() -> None:
    reg = get_registry()
    m = reg.build_chaos_rule("modify_card_value", {"delta": -1})
    assert m is not None
    assert getattr(m, "id", None) == "modify_card_value"
    v = m.adjust_rank_value(Card(Rank("10"), ""), 10)
    assert v == 9


def test_peek_item_registered() -> None:
    reg = get_registry()
    cls = reg.resolve_item("peek")
    assert cls is not None
    assert getattr(cls, "name", None) == "peek"
