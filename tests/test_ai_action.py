"""Structured AI action parsing."""

from __future__ import annotations

from chaos_blackjack.contracts.ai_action import parse_structured_action


def test_parse_minimal() -> None:
    p = parse_structured_action({"action": "noop"})
    assert p is not None
    assert p["action"] == "noop"


def test_parse_apply_rule() -> None:
    p = parse_structured_action(
        {
            "action": "apply_rule",
            "rule_id": "modify_card_value",
            "params": {"delta": -2},
        },
    )
    assert p is not None
    assert p.get("rule_id") == "modify_card_value"
    assert p.get("params") == {"delta": -2}


def test_parse_invalid_missing_action() -> None:
    assert parse_structured_action({}) is None
    assert parse_structured_action({"action": ""}) is None
