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


# --- Aces stay soft under value-changing chaos rules ------------------------

def _hand(*cards: str) -> tuple[Card, ...]:
    return tuple(Card(Rank(c[:-1]), c[-1]) for c in cards)


def _value(mods, *cards: str) -> int:
    return DefaultBlackjackRules().hand_value(_hand(*cards), RuleContext(modifiers=ActiveModifiers(items=tuple(mods))))


def test_baseline_aces_soft_and_hard() -> None:
    assert _value([], "A♠", "6♥") == 17
    assert _value([], "A♠", "6♥", "K♦") == 17
    assert _value([], "A♠", "A♥", "9♦") == 21


def test_value_shift_moves_both_ace_values() -> None:
    from chaos_blackjack.rules.plugins.modify_card_value import ModifyCardValueModifier

    minus1 = [ModifyCardValueModifier(id="modify_card_value", delta=-1)]
    assert _value(minus1, "A♠", "6♥") == 15                 # 10 + 5, soft
    assert _value(minus1, "6♥", "Q♦", "A♠") == 14           # agent test R2: was 24 (bust)
    assert _value(minus1, "4♥", "A♥", "A♦") == 13           # agent test R7: was 23 (bust)
    assert _value(minus1, "3♣", "6♣", "A♥") == 17           # 2 + 5 + 10 stays high


def test_suit_power_aces_soft() -> None:
    sp = [SuitPowerModifier()]
    assert _value(sp, "A♥", "K♠") == 21                     # 12 + 9
    assert _value(sp, "A♥", "K♠", "5♣") == 15               # red Ace drops to 2: 2 + 9 + 4


def test_fragile_bust_softens_against_18() -> None:
    fb = [FragileBustModifier()]
    assert _value(fb, "A♠", "K♥") == 11                     # 21 would bust at 18 -> Ace counts 1
    assert _value(fb, "A♠", "7♥") == 18
    assert _value(fb, "A♠", "8♥") == 9
