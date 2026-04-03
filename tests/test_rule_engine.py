"""Baseline blackjack + chaos flags."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.plugins.fragile_bust import FragileBustModifier
from chaos_blackjack.rules.plugins.great_crash import GreatCrashModifier
from chaos_blackjack.rules.plugins.odd_even_chaos import OddEvenChaosModifier
from chaos_blackjack.rules.plugins.suit_power import SuitPowerModifier
from chaos_blackjack.rules.plugins.reverse_bust import ReverseBustModifier
from chaos_blackjack.rules.plugins.tiebreaker_shift import TiebreakerShiftModifier
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


def test_great_crash_turns_10_into_1() -> None:
    rules = DefaultBlackjackRules()
    ctx = RuleContext(modifiers=ActiveModifiers(items=(GreatCrashModifier(),)))
    assert rules.hand_value((Card(Rank("10"), "♠"),), ctx) == 1


def test_odd_even_chaos_even_plus_2_odd_minus_1() -> None:
    rules = DefaultBlackjackRules()
    ctx = RuleContext(modifiers=ActiveModifiers(items=(OddEvenChaosModifier(),)))
    assert rules.hand_value((Card(Rank("2"), "♠"),), ctx) == 4
    assert rules.hand_value((Card(Rank("3"), "♠"),), ctx) == 2


def test_suit_power_red_plus_1_black_minus_1() -> None:
    rules = DefaultBlackjackRules()
    ctx = RuleContext(modifiers=ActiveModifiers(items=(SuitPowerModifier(),)))
    assert rules.hand_value((Card(Rank("7"), "♥"),), ctx) == 8
    assert rules.hand_value((Card(Rank("7"), "♠"),), ctx) == 6


def test_fragile_bust_threshold_18() -> None:
    rules = DefaultBlackjackRules()
    ctx = RuleContext(modifiers=ActiveModifiers(items=(FragileBustModifier(),)))
    assert rules.is_bust(19, ctx) is True
    assert rules.is_bust(18, ctx) is False


def test_tiebreaker_shift_player_wins_ties() -> None:
    rules = DefaultBlackjackRules()
    # Player total == Dealer total (both 19) and neither side is bust.
    st_player_vs_dealer = RuleContext(
        modifiers=ActiveModifiers(
            items=(TiebreakerShiftModifier(id="tiebreaker_shift", chaos_flags=frozenset({"player_wins_ties"})),),
        )
    )
    # Construct a minimal GameState with equal totals.
    from chaos_blackjack.core.game_state import GameState, GamePhase

    state = GameState(
        player_hand=(Card(Rank("10"), "♠"), Card(Rank("9"), "♠")),
        dealer_hand=(Card(Rank("10"), "♠"), Card(Rank("9"), "♠")),
        deck=(),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=(),
    )
    assert rules.compare_player_dealer(state, st_player_vs_dealer) == "player"
