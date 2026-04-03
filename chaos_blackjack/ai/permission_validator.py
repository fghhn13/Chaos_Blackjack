"""Validate structured AI actions against a permission profile."""

from __future__ import annotations

from typing import Any

from chaos_blackjack.contracts.ai_action import StructuredAIAction


def validate_chaos_action(
    action: StructuredAIAction,
    profile: dict[str, Any],
    *,
    budget_remaining: int,
    actions_this_turn: int,
) -> tuple[bool, str]:
    """Return (ok, reason)."""
    max_turn = int(profile.get("max_actions_per_turn", 1))
    verb = action.get("action", "noop")

    if verb == "noop":
        return True, ""

    if actions_this_turn >= max_turn:
        return False, "max_actions_per_turn"

    if budget_remaining <= 0:
        return False, "chaos_budget"

    if verb == "apply_rule":
        rid = action.get("rule_id")
        if not rid:
            return False, "missing_rule_id"
        allowed = profile.get("allowed_rules", [])
        if rid not in allowed:
            return False, "rule_not_allowed"
        return True, ""

    if verb == "use_item":
        iid = action.get("item_id")
        if not iid:
            return False, "missing_item_id"
        allowed_items = profile.get("allowed_items")
        if allowed_items is not None and iid not in allowed_items:
            return False, "item_not_allowed"
        return True, ""

    return False, "unknown_action"
