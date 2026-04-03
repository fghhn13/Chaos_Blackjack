"""Baseline blackjack + chaos flags."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.plugins.reverse_bust import ReverseBustModifier
from chaos_blackjack.rules.rule_engine import DefaultBlackjackRules, RuleContext


def test_hand_value_simple() -> None:
    rules = DefaultBlackjackRules()
    ctx = RuleContext(modifiers=ActiveModifiers())
    hand = (Card(Rank("7"), ""), Card(Rank("9"), ""))
    assert rules.hand_value(hand, ctx) == 16


def test_reverse_bust_exposes_chaos_flag() -> None:
    mod = ReverseBustModifier()
    ctx = RuleContext(modifiers=ActiveModifiers(items=(mod,)))
    assert "reverse_bust" in ctx.modifiers.chaos_flags()
