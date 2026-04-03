"""Chaos agent — proposes rule modifiers; never mutates game state directly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from chaos_blackjack.core.game_state import GameState
from chaos_blackjack.rules.modifiers import ActiveModifiers, RuleModifier


@dataclass(frozen=True)
class ChaosObservation:
    """Narrow view for the agent — extend with telemetry / player stats later."""

    state: GameState
    modifiers: ActiveModifiers
    last_event_summary: str | None = None


@runtime_checkable
class ChaosAgent(Protocol):
    """Implement LLM, heuristic, or scripted chaos behind this interface."""

    def maybe_propose_modifier(self, obs: ChaosObservation) -> RuleModifier | None:
        ...


@dataclass
class NoOpChaosAgent:
    """Default agent: no perturbations (vanilla blackjack)."""

    def maybe_propose_modifier(self, obs: ChaosObservation) -> RuleModifier | None:
        return None
