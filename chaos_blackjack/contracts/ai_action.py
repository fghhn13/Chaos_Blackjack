"""Structured output shape for chaos AI — JSON-serializable only."""

from __future__ import annotations

from typing import Any, TypedDict


class _RequiredAction(TypedDict):
    action: str
    """High-level verb: apply_rule, noop, use_item."""


class StructuredAIAction(_RequiredAction, total=False):
    """LLM / stub must return JSON matching this shape.

    (Required/optional split via inheritance: typing.NotRequired is 3.11+.)
    """

    narration: str
    """Short human-readable explanation for UI (no markdown)."""

    rule_id: str | None
    params: dict[str, Any]
    item_id: str | None


def parse_structured_action(raw: dict[str, Any]) -> StructuredAIAction | None:
    """Validate minimal keys; returns None if invalid."""
    action = raw.get("action")
    if not isinstance(action, str) or not action:
        return None
    out: StructuredAIAction = {"action": action}
    narration = raw.get("narration")
    if narration is not None:
        if not isinstance(narration, str):
            return None
        out["narration"] = narration
    rid = raw.get("rule_id")
    if rid is not None:
        out["rule_id"] = str(rid) if not isinstance(rid, str) else rid
    params = raw.get("params")
    if isinstance(params, dict):
        out["params"] = params
    iid = raw.get("item_id")
    if iid is not None:
        out["item_id"] = str(iid) if not isinstance(iid, str) else iid
    return out
