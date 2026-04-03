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

    # Newly added numeric + logic-twisting rules.
    m2 = reg.build_chaos_rule("great_crash", {})
    assert m2 is not None
    assert m2.adjust_rank_value(Card(Rank("K"), ""), 10) == 1

    m3 = reg.build_chaos_rule("fragile_bust", {})
    assert m3 is not None
    assert "fragile_bust" in getattr(m3, "chaos_flags", frozenset())


def test_peek_item_registered() -> None:
    reg = get_registry()
    cls = reg.resolve_item("peek")
    assert cls is not None
    assert getattr(cls, "name", None) == "peek"
