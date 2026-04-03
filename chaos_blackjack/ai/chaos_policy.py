"""AI chaos policy — rules about when/what actions are allowed and how they are charged.

This module is intentionally "pure": it does not parse LLM JSON, does not emit events,
and does not mutate game state. It only decides:
- whether we should even attempt chaos this step
- whether a parsed action is allowed under the profile
- how much to charge (budget + action count) when an effect is successfully produced
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from chaos_blackjack.contracts.ai_action import StructuredAIAction
from chaos_blackjack.contracts.observation import ChaosObservation


class ChaosEffectLike(Protocol):
    """A small protocol so we don't import ChaosEffect (avoid circular deps)."""

    modifier: Any | None
    consume_item_id: str | None


@dataclass(frozen=True)
class ChaosAccountingDelta:
    budget_charge: int
    actions_charge: int


@dataclass(frozen=True)
class ChaosPolicy:
    allowed_rules: tuple[str, ...]
    allowed_items: tuple[str, ...] | None
    max_actions_per_turn: int
    max_active_effects: int
    chaos_budget_cap: int
    charge_per_effect: int

    @classmethod
    def from_profile(cls, profile: dict[str, Any]) -> "ChaosPolicy":
        # New schema (preferred)
        attempt_limits = profile.get("attempt_limits") if isinstance(profile.get("attempt_limits"), dict) else {}
        budget = profile.get("budget") if isinstance(profile.get("budget"), dict) else {}

        # Backward compatible fallbacks
        max_actions_per_turn = int(
            attempt_limits.get(
                "max_actions_per_turn",
                profile.get("max_actions_per_turn", 1),
            )
        )
        max_active_effects = int(
            attempt_limits.get(
                "max_active_effects",
                1,
            )
        )

        chaos_budget_cap = int(
            budget.get(
                "chaos_budget",
                profile.get("chaos_budget", 0),
            )
        )
        charge_per_effect = int(budget.get("charge_per_effect", 1))

        allowed_rules = profile.get("allowed_rules") or []
        allowed_items_raw = profile.get("allowed_items", None)
        allowed_items: tuple[str, ...] | None
        if allowed_items_raw is None:
            allowed_items = None
        else:
            allowed_items = tuple(str(x) for x in allowed_items_raw)

        return cls(
            allowed_rules=tuple(str(x) for x in allowed_rules),
            allowed_items=allowed_items,
            max_actions_per_turn=max_actions_per_turn,
            max_active_effects=max_active_effects,
            chaos_budget_cap=chaos_budget_cap,
            charge_per_effect=charge_per_effect,
        )

    def should_attempt(self, obs: ChaosObservation) -> bool:
        """Whether the system is allowed to attempt a non-noop chaos action now."""
        if obs.chaos_budget_remaining <= 0:
            return False
        if obs.chaos_actions_this_turn >= self.max_actions_per_turn:
            return False
        # Active effects are modeled by active modifiers on the GameLoop.
        active_effects = len(obs.modifiers.items)
        if active_effects >= self.max_active_effects:
            return False
        return True

    def validate_action(
        self,
        action: StructuredAIAction,
        obs: ChaosObservation,
    ) -> tuple[bool, str]:
        """Return (ok, reason)."""
        verb = action.get("action", "noop")
        if verb == "noop":
            return True, ""

        # Hard constraints.
        if not self.should_attempt(obs):
            return False, "policy_denied"

        if verb == "apply_rule":
            rid = action.get("rule_id")
            if not rid:
                return False, "missing_rule_id"
            if rid not in self.allowed_rules:
                return False, "rule_not_allowed"
            return True, ""

        if verb == "use_item":
            iid = action.get("item_id")
            if not iid:
                return False, "missing_item_id"
            if self.allowed_items is not None and iid not in self.allowed_items:
                return False, "item_not_allowed"
            return True, ""

        return False, "unknown_action"

    def charge_for_effect(self, effect: ChaosEffectLike) -> ChaosAccountingDelta:
        if effect.modifier is None and effect.consume_item_id is None:
            return ChaosAccountingDelta(budget_charge=0, actions_charge=0)
        return ChaosAccountingDelta(
            budget_charge=self.charge_per_effect,
            actions_charge=1,
        )

