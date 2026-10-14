"""GameController — UI-agnostic run state machine."""

from __future__ import annotations

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import Action, TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _ctrl(**cfg) -> GameController:
    saved: list = []
    c = GameController(RunConfig(seed=1, **cfg), save_fn=lambda d, n: saved.append((n, d)) or n)
    c.saved = saved  # type: ignore[attr-defined]
    return c


def _rig(c: GameController, player, dealer, deck=()) -> None:
    """Replace the dealt table with a known one."""
    c.state = GameState(
        player_hand=tuple(player),
        dealer_hand=tuple(dealer),
        deck=tuple(deck),
        phase=GamePhase.PLAYER_TURN,
        inventory=c.state.inventory if c.state else (),
    )


def test_starts_in_betting_with_limits() -> None:
    c = _ctrl()
    v = c.view()
    assert v.phase == TablePhase.BETTING
    assert (v.bet_min, v.bet_max) == (5, 50)
    assert v.available_actions == frozenset({Action.BET, Action.BUY, Action.REROLL, Action.SAVE})
    assert v.player_cards == ()


def test_invalid_bet_and_wrong_phase_raise() -> None:
    c = _ctrl()
    with pytest.raises(ActionError):
        c.place_bet(51)
    with pytest.raises(ActionError):
        c.hit()


def test_bet_deals_and_hides_hole_card() -> None:
    c = _ctrl()
    c.place_bet(10)
    v = c.view()
    assert v.phase == TablePhase.PLAYER_TURN
    assert len(v.player_cards) == 2 and len(v.dealer_cards) == 2
    assert v.dealer_cards[1].face_up is False
    assert v.dealer_total is None
    kinds = [n.kind for n in c.drain_notices()]
    assert NoticeKind.ROUND_STARTED in kinds


def test_player_bust_settles_immediately() -> None:
    c = _ctrl()
    c.place_bet(10)
    _rig(c, [_c("K"), _c("Q")], [_c("9"), _c("8")], deck=[_c("5")])
    c.hit()
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER
    assert v.last_result is not None and v.last_result.player_bust
    assert v.money == 90 and v.last_result.delta == -10
    assert any(n.kind == NoticeKind.PLAYER_BUST for n in c.drain_notices())


def test_stand_dealer_steps_then_win_and_next_round() -> None:
    c = _ctrl()
    c.place_bet(20)
    _rig(c, [_c("K"), _c("9")], [_c("10"), _c("6")], deck=[_c("K")])
    c.stand()
    assert c.view().dealer_cards[1].face_up  # revealed during dealer turn
    assert c.dealer_step() is True          # draws K -> 26
    assert c.dealer_step() is False         # busts, round settles
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER
    assert v.last_result.outcome == "player" and v.money == 120
    assert v.round == 1 and v.win_streak == 1
    c.next_round()
    assert c.view().phase == TablePhase.BETTING and c.view().round == 2


def test_wins_no_longer_grant_items() -> None:
    c = _ctrl()
    for _ in range(2):
        c.place_bet(10)
        _rig(c, [_c("K"), _c("Q")], [_c("10"), _c("7")])
        c.stand()
        c.finish_dealer()
        c.next_round()
    assert c.view().win_streak == 2 and c.view().items == ()


def test_use_item_consumes_and_reports() -> None:
    c = _ctrl()
    c.run.items = ("peek",)
    c.place_bet(10)
    res = c.use_item("peek")
    assert res.ok
    assert c.view().items == ()
    kinds = [n.kind for n in c.drain_notices()]
    assert NoticeKind.ITEM_USED in kinds and NoticeKind.ITEM_RESULT in kinds


def test_victory_ends_run() -> None:
    c = _ctrl(start_money=100, target_money=110)
    c.place_bet(10)
    _rig(c, [_c("K"), _c("Q")], [_c("10"), _c("7")])
    c.stand()
    c.finish_dealer()
    v = c.view()
    assert v.phase == TablePhase.RUN_OVER and v.run_end.kind == "victory"
    assert v.available_actions == frozenset()


def test_cannot_bet_is_defeat() -> None:
    c = _ctrl(start_money=1)
    v = c.view()
    assert v.phase == TablePhase.RUN_OVER and v.run_end.kind == "defeat"


def test_chaos_phase_requires_resolve() -> None:
    c = _ctrl(enable_chaos=True)
    c.place_bet(10)
    assert c.view().phase == TablePhase.CHAOS
    with pytest.raises(ActionError):
        c.hit()
    c.resolve_chaos()
    v = c.view()
    assert v.phase == TablePhase.PLAYER_TURN
    assert v.active_rules  # stub LLM always applies modify_card_value


def test_save_and_resume_mid_round() -> None:
    c = _ctrl(enable_chaos=True)
    c.place_bet(10)
    c.resolve_chaos()
    data = c.save("slot")
    r = GameController.from_save(data)
    a, b = c.view(), r.view()
    assert b.phase == TablePhase.PLAYER_TURN
    assert (b.money, b.current_bet, b.player_cards) == (a.money, a.current_bet, a.player_cards)
    assert [x.id for x in b.active_rules] == [x.id for x in a.active_rules]


def test_save_between_rounds_resumes_at_betting() -> None:
    c = _ctrl()
    data = c.save("slot")
    assert data.game_state is None
    assert GameController.from_save(data).view().phase == TablePhase.BETTING


# --- double down / surrender / naturals -------------------------------------

def _deal(c: GameController, player, dealer, deck=(), bet: int = 10) -> None:
    """Place a bet with a rigged deal (naturals are checked on this deal)."""
    def fixed_round(seed=None, *, inventory_override=None):
        c.loop.modifiers = c.loop.modifiers.with_cleared()
        return GameState(
            player_hand=tuple(player),
            dealer_hand=tuple(dealer),
            deck=tuple(deck),
            phase=GamePhase.PLAYER_TURN,
            inventory=inventory_override or (),
        )

    c.loop.new_round = fixed_round  # type: ignore[method-assign]
    c.place_bet(bet)


def test_first_decision_offers_double_and_surrender() -> None:
    c = _ctrl()
    _deal(c, [_c("5"), _c("6")], [_c("9"), _c("7")], deck=[_c("2"), _c("3")])
    assert {Action.DOUBLE, Action.SURRENDER} <= c.view().available_actions
    c.hit()
    v = c.view()
    assert Action.DOUBLE not in v.available_actions
    assert Action.SURRENDER not in v.available_actions
    with pytest.raises(ActionError):
        c.double_down()


def test_rules_can_be_switched_off() -> None:
    c = _ctrl(allow_double=False, allow_surrender=False)
    _deal(c, [_c("5"), _c("6")], [_c("9"), _c("7")])
    assert not {Action.DOUBLE, Action.SURRENDER} & c.view().available_actions


def test_double_down_doubles_bet_draws_one_and_stands() -> None:
    c = _ctrl()
    _deal(c, [_c("5"), _c("6")], [_c("10"), _c("7")], deck=[_c("K"), _c("2")], bet=20)
    c.double_down()
    v = c.view()
    assert v.current_bet == 40 and len(v.player_cards) == 3
    assert v.phase == TablePhase.DEALER_TURN
    c.finish_dealer()  # dealer 17 stands; player 21 wins
    r = c.view().last_result
    assert r.outcome == "player" and r.doubled and r.delta == 40
    assert c.view().money == 140


def test_double_down_bust_loses_double() -> None:
    c = _ctrl()
    _deal(c, [_c("10"), _c("6")], [_c("10"), _c("7")], deck=[_c("K")], bet=20)
    c.double_down()
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER and v.last_result.player_bust
    assert v.last_result.delta == -40 and v.money == 60


def test_surrender_returns_half_rounded_for_house() -> None:
    c = _ctrl()
    _deal(c, [_c("10"), _c("6")], [_c("10"), _c("9")], bet=15)
    c.surrender()
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER
    assert v.last_result.outcome == "surrender"
    assert v.last_result.delta == -8  # 7 of 15 back
    assert v.money == 92 and v.win_streak == 0


def test_player_natural_pays_three_to_two() -> None:
    c = _ctrl()
    _deal(c, [_c("A"), _c("K")], [_c("9"), _c("7")], bet=10)
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER
    assert v.last_result.outcome == "blackjack" and v.last_result.delta == 15
    assert v.money == 115 and v.win_streak == 1
    assert v.dealer_cards[1].face_up


def test_natural_payout_rounds_down_and_ratio_configurable() -> None:
    c = _ctrl()
    _deal(c, [_c("A"), _c("Q")], [_c("9"), _c("7")], bet=5)
    assert c.view().last_result.delta == 7  # 7.5 -> 7
    c2 = _ctrl(blackjack_pays=(6, 5))
    _deal(c2, [_c("A"), _c("Q")], [_c("9"), _c("7")], bet=10)
    assert c2.view().last_result.delta == 12


def test_dealer_natural_wins_before_player_acts() -> None:
    c = _ctrl()
    _deal(c, [_c("10"), _c("9")], [_c("A"), _c("J")], bet=10)
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER
    assert v.last_result.outcome == "dealer" and v.last_result.dealer_blackjack
    assert v.money == 90
    kinds = [n.kind for n in c.drain_notices()]
    assert NoticeKind.DEALER_BLACKJACK in kinds


def test_both_naturals_push() -> None:
    c = _ctrl()
    _deal(c, [_c("A"), _c("K")], [_c("A"), _c("Q")], bet=10)
    r = c.view().last_result
    assert r.outcome == "push" and r.delta == 0


def test_three_card_21_is_not_a_natural() -> None:
    c = _ctrl()
    _deal(c, [_c("7"), _c("7")], [_c("10"), _c("8")], deck=[_c("7")], bet=10)
    c.hit()
    c.stand()
    c.finish_dealer()
    r = c.view().last_result
    assert r.outcome == "player" and r.delta == 10


# --- goal as a multiple of the start (docs/design/CARRIED_CHIPS.zh-CN.md §4) -------------------


def test_target_multiple_sets_the_goal_and_is_a_ceiling() -> None:
    c = _ctrl(start_money=100, target_multiple=4)
    assert c.run.target_money == 400
    c.run.money = 380
    _deal(c, [_c("K"), _c("9")], [_c("10"), _c("7")], bet=50)
    c.stand()
    c.finish_dealer()
    assert c.run_end is not None and c.run_end.kind == "victory"
    assert c.run.money == 400 and c.last_result.delta == 20
    assert any("not paid" in n.text for n in c.drain_notices())


def test_without_a_multiple_wins_are_paid_past_the_target() -> None:
    c = _ctrl(start_money=100, target_money=300)
    c.run.money = 290
    _deal(c, [_c("K"), _c("9")], [_c("10"), _c("7")], bet=50)
    c.stand()
    c.finish_dealer()
    assert c.run.money == 340 and c.run_end.kind == "victory"
