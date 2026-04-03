"""Run end policy unit tests (fail-first)."""

from __future__ import annotations

from dataclasses import dataclass

from chaos_blackjack.logic.run_end_policy import (
    CompositeRunEndPolicy,
    MoneyBankruptDefeatPolicy,
    MoneyTargetVictoryPolicy,
)


@dataclass(frozen=True)
class DummyRun:
    money: int
    target_money: int


def _policy() -> CompositeRunEndPolicy:
    return CompositeRunEndPolicy(
        policies=(MoneyBankruptDefeatPolicy(), MoneyTargetVictoryPolicy()),
    )


def test_defeat_when_money_le_zero() -> None:
    policy = _policy()
    res = policy.check(DummyRun(money=0, target_money=400))
    assert res is not None
    assert res.kind == "defeat"
    assert res.message == "Game Over. You are out of money."


def test_victory_when_money_ge_target() -> None:
    policy = _policy()
    res = policy.check(DummyRun(money=400, target_money=400))
    assert res is not None
    assert res.kind == "victory"
    assert res.message == "Victory! You reached the target bankroll."


def test_fail_first_when_both_match() -> None:
    policy = _policy()
    # money <= 0 and money >= target both true.
    res = policy.check(DummyRun(money=0, target_money=0))
    assert res is not None
    assert res.kind == "defeat"
    assert res.message == "Game Over. You are out of money."

