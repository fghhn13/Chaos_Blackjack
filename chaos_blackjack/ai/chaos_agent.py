"""Legacy protocol + re-exports — prefer ChaosPipeline for new code."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.rules.modifiers import RuleModifier


@runtime_checkable
class ChaosAgent(Protocol):
    """Optional legacy hook: direct modifier proposal (bypasses JSON sandbox)."""

    def maybe_propose_modifier(self, obs: ChaosObservation) -> RuleModifier | None:
        ...


@dataclass
class NoOpChaosAgent:
    def maybe_propose_modifier(self, obs: ChaosObservation) -> RuleModifier | None:
        return None
