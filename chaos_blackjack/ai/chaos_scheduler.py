"""Chaos scheduler — decides whether we should attempt to execute chaos now.

The scheduler is intentionally thin: the "rules" live in ChaosPolicy.
"""

from __future__ import annotations

from chaos_blackjack.ai.chaos_policy import ChaosPolicy
from chaos_blackjack.contracts.observation import ChaosObservation


class ChaosScheduler:
    def __init__(self, policy: ChaosPolicy) -> None:
        self.policy = policy

    def should_attempt(self, obs: ChaosObservation) -> bool:
        return self.policy.should_attempt(obs)

