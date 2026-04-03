"""ChaosPipeline with StubLLM — no network."""

from __future__ import annotations

from chaos_blackjack.ai.pipeline import ChaosPipeline, StubLLM
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.core.game_state import GamePhase, GameState
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry.registry import get_registry
from chaos_blackjack.rules.modifiers import ActiveModifiers


def _minimal_state() -> GameState:
    from chaos_blackjack.core.game_state import Card, Rank

    return GameState(
        player_hand=(Card(Rank("8"), ""), Card(Rank("9"), "")),
        dealer_hand=(Card(Rank("6"), ""), Card(Rank("K"), "")),
        deck=(Card(Rank("2"), ""),),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=5,
        inventory=("peek",),
    )


def test_pipeline_apply_rule_stub() -> None:
    reg = get_registry()
    pipe = ChaosPipeline.from_profile_name(
        "easy",
        "chaotic",
        StubLLM(
            response_json='{"action":"apply_rule","rule_id":"modify_card_value","params":{"delta":-1}}',
        ),
        registry=reg,
    )
    obs = ChaosObservation(
        state=_minimal_state(),
        modifiers=ActiveModifiers(),
        chaos_budget_remaining=5,
        chaos_actions_this_turn=0,
    )
    events: list[Event] = []

    def emit(e: Event) -> None:
        events.append(e)

    eff = pipe.run(
        obs,
        emit=emit,
        peek_next_card_rank=lambda: "A",
    )
    assert eff.modifier is not None
    assert any(e.type == EventType.RULE_MODIFIER_APPLIED for e in events)


def test_pipeline_invalid_json_emits_reject() -> None:
    reg = get_registry()
    pipe = ChaosPipeline.from_profile_name(
        "easy",
        "chaotic",
        StubLLM(response_json="not json"),
        registry=reg,
    )
    obs = ChaosObservation(
        state=_minimal_state(),
        modifiers=ActiveModifiers(),
        chaos_budget_remaining=5,
        chaos_actions_this_turn=0,
    )
    events: list[Event] = []

    def emit(e: Event) -> None:
        events.append(e)

    eff = pipe.run(obs, emit=emit, peek_next_card_rank=lambda: None)
    assert eff.modifier is None
    assert any(
        e.type == EventType.CHAOS_ACTION_REJECTED and e.payload.get("reason") == "invalid_json"
        for e in events
    )
