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
    assert (v.bet_min, v.bet_max) == (1, 50)
    assert v.available_actions == frozenset({Action.BET, Action.SAVE})
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


def test_streak_reward_lands_in_inventory() -> None:
    c = _ctrl(reward_streak=1, reward_pool=("peek",))
    c.place_bet(10)
    _rig(c, [_c("K"), _c("Q")], [_c("10"), _c("7")])
    c.stand()
    c.finish_dealer()
    assert c.view().last_result.reward == "peek"
    c.next_round()
    c.place_bet(10)
    assert [i.id for i in c.view().items] == ["peek"]


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
