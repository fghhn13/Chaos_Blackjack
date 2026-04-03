"""ChaosPolicy/ChaosScheduler unit tests (policy-only, no LLM/network)."""

from __future__ import annotations

from dataclasses import dataclass

from chaos_blackjack.ai.chaos_policy import ChaosPolicy
from chaos_blackjack.ai.chaos_scheduler import ChaosScheduler
from chaos_blackjack.contracts.ai_action import StructuredAIAction
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.core.game_state import GamePhase, GameState, Rank, Card
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.plugins.great_crash import GreatCrashModifier


def _minimal_state() -> GameState:
    return GameState(
        player_hand=(),
        dealer_hand=(),
        deck=(),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=0,
        inventory=(),
    )


def _minimal_obs(*, modifiers: ActiveModifiers, budget_remaining: int, actions: int) -> ChaosObservation:
    return ChaosObservation(
        state=_minimal_state(),
        modifiers=modifiers,
        chaos_budget_remaining=budget_remaining,
        chaos_actions_this_turn=actions,
    )


def test_should_attempt_denied_when_active_effects_reached() -> None:
    profile = {
        "allowed_rules": ["great_crash"],
        "allowed_items": [],
        "attempt_limits": {"max_actions_per_turn": 10, "max_active_effects": 1},
        "budget": {"chaos_budget": 5, "charge_per_effect": 1},
    }
    policy = ChaosPolicy.from_profile(profile)

    obs0 = _minimal_obs(
        modifiers=ActiveModifiers(items=()),
        budget_remaining=5,
        actions=0,
    )
    assert policy.should_attempt(obs0) is True

    obs1 = _minimal_obs(
        modifiers=ActiveModifiers(items=(GreatCrashModifier(),)),
        budget_remaining=5,
        actions=0,
    )
    assert policy.should_attempt(obs1) is False


def test_charge_for_effect_charges_once() -> None:
    profile = {
        "allowed_rules": [],
        "allowed_items": [],
        "attempt_limits": {"max_actions_per_turn": 10, "max_active_effects": 1},
        "budget": {"chaos_budget": 5, "charge_per_effect": 7},
    }
    policy = ChaosPolicy.from_profile(profile)

    @dataclass(frozen=True)
    class DummyEffect:
        modifier: object | None = object()
        consume_item_id: str | None = None

    delta = policy.charge_for_effect(DummyEffect())
    assert delta.budget_charge == 7
    assert delta.actions_charge == 1


def test_validate_action_denied_when_policy_denies() -> None:
    profile = {
        "allowed_rules": ["great_crash"],
        "allowed_items": [],
        "attempt_limits": {"max_actions_per_turn": 10, "max_active_effects": 1},
        "budget": {"chaos_budget": 5, "charge_per_effect": 1},
    }
    policy = ChaosPolicy.from_profile(profile)

    obs = _minimal_obs(
        modifiers=ActiveModifiers(items=(GreatCrashModifier(),)),
        budget_remaining=5,
        actions=0,
    )
    action: StructuredAIAction = {
        "action": "apply_rule",
        "rule_id": "great_crash",
        "params": {},
    }
    ok, reason = policy.validate_action(action, obs)
    assert ok is False
    assert reason == "policy_denied"


def test_scheduler_delegates_to_policy() -> None:
    profile = {
        "allowed_rules": ["great_crash"],
        "allowed_items": [],
        "attempt_limits": {"max_actions_per_turn": 1, "max_active_effects": 1},
        "budget": {"chaos_budget": 5, "charge_per_effect": 1},
    }
    policy = ChaosPolicy.from_profile(profile)
    scheduler = ChaosScheduler(policy)

    obs = _minimal_obs(
        modifiers=ActiveModifiers(items=()),
        budget_remaining=5,
        actions=0,
    )
    assert scheduler.should_attempt(obs) is True

