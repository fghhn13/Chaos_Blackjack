"""Run end (global win/lose) policies.

This module decouples the global victory/defeat rules from the UI loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


class RunEconomyView(Protocol):
    """Minimal view required for run-end decisions (structural typing)."""

    money: int
    target_money: int


@dataclass(frozen=True)
class RunEndResult:
    kind: str  # "victory" | "defeat"
    message: str


class RunEndPolicy(Protocol):
    def check(self, run: RunEconomyView) -> Optional[RunEndResult]:
        ...


@dataclass(frozen=True)
class MoneyBankruptDefeatPolicy:
    """Failure when bankroll is depleted."""

    message: str = "Game Over. You are out of money."

    def check(self, run: RunEconomyView) -> Optional[RunEndResult]:
        if run.money <= 0:
            return RunEndResult(kind="defeat", message=self.message)
        return None


@dataclass(frozen=True)
class MoneyTargetVictoryPolicy:
    """Victory when bankroll reaches target."""

    message: str = "Victory! You reached the target bankroll."

    def check(self, run: RunEconomyView) -> Optional[RunEndResult]:
        if run.money >= run.target_money:
            return RunEndResult(kind="victory", message=self.message)
        return None


@dataclass(frozen=True)
class CompositeRunEndPolicy:
    """Evaluate policies in order and return the first match."""

    policies: Sequence[RunEndPolicy]

    def check(self, run: RunEconomyView) -> Optional[RunEndResult]:
        for p in self.policies:
            res = p.check(run)
            if res is not None:
                return res
        return None

