"""PermissionValidator — fast to run, good for debugging action JSON."""

from __future__ import annotations

import pytest

from chaos_blackjack.ai.permission_validator import validate_chaos_action


@pytest.fixture
def easy_like() -> dict:
    return {
        "allowed_rules": ["modify_card_value"],
        "allowed_items": ["peek"],
        "max_actions_per_turn": 1,
        "chaos_budget": 5,
    }


def test_noop_always_ok(easy_like: dict) -> None:
    ok, reason = validate_chaos_action(
        {"action": "noop"},
        easy_like,
        budget_remaining=0,
        actions_this_turn=99,
    )
    assert ok is True
    assert reason == ""


def test_apply_rule_allowed(easy_like: dict) -> None:
    ok, _ = validate_chaos_action(
        {"action": "apply_rule", "rule_id": "modify_card_value", "params": {"delta": -1}},
        easy_like,
        budget_remaining=3,
        actions_this_turn=0,
    )
    assert ok is True


def test_apply_rule_not_in_list(easy_like: dict) -> None:
    ok, reason = validate_chaos_action(
        {"action": "apply_rule", "rule_id": "forbidden_rule"},
        easy_like,
        budget_remaining=3,
        actions_this_turn=0,
    )
    assert ok is False
    assert reason == "rule_not_allowed"


def test_budget_blocks(easy_like: dict) -> None:
    ok, reason = validate_chaos_action(
        {"action": "apply_rule", "rule_id": "modify_card_value"},
        easy_like,
        budget_remaining=0,
        actions_this_turn=0,
    )
    assert ok is False
    assert reason == "chaos_budget"


def test_max_actions_per_turn(easy_like: dict) -> None:
    ok, reason = validate_chaos_action(
        {"action": "apply_rule", "rule_id": "modify_card_value"},
        easy_like,
        budget_remaining=5,
        actions_this_turn=1,
    )
    assert ok is False
    assert reason == "max_actions_per_turn"
