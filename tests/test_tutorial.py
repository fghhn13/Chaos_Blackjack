"""Onboarding: the practice table, the strategy chart, milestones and table unlocks (docs/design/TUTORIAL.md)."""

from __future__ import annotations

import pytest

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.view import Action, TablePhase
from chaos_blackjack.content import basic_strategy as bs
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.meta import onboarding
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.modes import get_mode, modes
from chaos_blackjack.tutorial.lessons import LESSONS


def practice() -> GameController:
    config = get_mode("tutorial").apply(RunConfig.from_balance(default_balance(), seed=3))
    return GameController(config)


# --------------------------------------------------------------- strategy chart

@pytest.mark.parametrize("total, soft, up, expected", [
    (16, False, "10", "surrender"), (16, False, "9", "surrender"), (16, False, "A", "surrender"),
    (15, False, "10", "surrender"), (15, False, "9", "hit"), (16, False, "6", "stand"),
    (12, False, "3", "hit"), (12, False, "4", "stand"), (11, False, "10", "double"), (11, False, "A", "hit"),
    (10, False, "9", "double"), (10, False, "10", "hit"), (9, False, "3", "double"), (9, False, "2", "hit"),
    (17, False, "A", "stand"), (8, False, "6", "hit"),
    (18, True, "4", "double"), (18, True, "2", "stand"), (18, True, "9", "hit"), (19, True, "6", "stand"),
    (17, True, "3", "double"), (17, True, "2", "hit"), (13, True, "5", "double"), (13, True, "4", "hit"),
    (15, True, "4", "double"), (14, True, "K", "hit"),
])
def test_the_chart_matches_basic_strategy(total, soft, up, expected):
    assert bs.advice(total, soft, up) == expected


def test_the_chart_falls_back_when_a_move_is_not_allowed():
    assert bs.advice(16, False, "10", can_surrender=False) == "hit"
    assert bs.advice(11, False, "6", can_double=False) == "hit"
    assert bs.advice(18, True, "4", can_double=False) == "stand"


# --------------------------------------------------------------- practice table

def test_tutorial_mode_is_never_listed():
    assert "tutorial" not in {m.id for m in modes()}
    assert get_mode("tutorial").hidden


def test_each_lesson_allows_only_its_button_and_the_practice_ends():
    c = practice()
    table = c.table
    for n, lesson in enumerate(LESSONS[:-1]):
        assert c.phase == TablePhase.BETTING and table.lesson is lesson
        c.place_bet(10)
        if c.phase == TablePhase.CHAOS:
            c.resolve_chaos()
        if lesson.action is None:   # the natural: settled at once, paid 3 to 2
            assert c.phase == TablePhase.ROUND_OVER and c.last_result.outcome == "blackjack", n
            assert c.last_result.delta == 15
            c.next_round()
            continue
        assert c.phase == TablePhase.PLAYER_TURN, n
        playable = c.view().available_actions & {Action.HIT, Action.STAND, Action.DOUBLE, Action.SURRENDER}
        assert playable == {lesson.action}, (n, playable)
        others = {Action.HIT: "hit", Action.STAND: "stand", Action.DOUBLE: "double_down",
                  Action.SURRENDER: "surrender"}
        wrong = next(a for a in others if a != lesson.action)
        with pytest.raises(ActionError):
            getattr(c, others[wrong])()
        getattr(c, others[lesson.action])()
        if lesson.then is not None:
            assert c.view().available_actions & set(others) == {lesson.then}
            getattr(c, others[lesson.then])()
        while c.phase == TablePhase.DEALER_TURN:
            c.dealer_step()
        assert c.last_result is not None
        assert c.last_result.outcome == ("surrender" if lesson.action == "surrender" else "player"), n
        c.next_round()
    # The free hand: every button the rules allow, with the chart's advice.
    c.place_bet(10)
    if c.phase == TablePhase.CHAOS:
        c.resolve_chaos()
    if c.phase == TablePhase.PLAYER_TURN:
        assert table.advice().startswith("The chart says")
        assert {Action.HIT, Action.STAND} <= c.view().available_actions
        c.stand()
    while c.phase == TablePhase.DEALER_TURN:
        c.dealer_step()
    assert c.phase == TablePhase.RUN_OVER and c.run_end.kind == "victory"


def test_practice_bets_are_capped_at_a_quarter():
    c = practice()
    lo, hi = c.bet_limits(c.run.money)
    assert hi == c.run.money // 4


# --------------------------------------------------------------- milestones and unlocks

@pytest.fixture
def guided(monkeypatch):
    monkeypatch.setenv("CHAOS_TUTORIAL", "1")
    service = install_fake(demo=False)
    yield service
    meta.use_service(None)


def test_a_player_from_before_onboarding_has_every_milestone():
    install_fake(demo=False)
    try:
        player = meta.create_player(1, "Old")
        assert not player.guided
        assert meta.milestones(player.id) == frozenset(onboarding.ALL)
        assert all(o.unlocked for o in meta.modes(player.id))
    finally:
        meta.use_service(None)


def test_a_new_player_sees_poker_head_as_a_silhouette_and_no_j54(guided):
    player = meta.create_player(1, "New")
    assert player.guided and meta.milestones(player.id) == frozenset()
    options = {o.mode.id: o for o in meta.modes(player.id)}
    assert options["normal"].unlocked
    assert not options["chaos"].unlocked and "top stake" in options["chaos"].hint
    assert "j54" not in options
    with pytest.raises(meta.MetaError):
        meta.start_run(player.id, "chaos", stake=400)
    with pytest.raises(meta.MetaError):
        meta.start_run(player.id, "tutorial")


def test_a_top_stake_classic_win_opens_poker_head_and_shows_j54(guided):
    player = meta.create_player(1, "New")
    started = meta.start_run(player.id, "normal", stake=100)
    assert started.config.max_bet_fraction == onboarding.CAP_FRACTION and started.notes
    c = started.controller
    c.run.money = c.config.target_money - 1
    _win_a_hand(c)
    reward = meta.finish_run(started.run_id, c)
    assert onboarding.CLASSIC_MAX_WIN in reward.milestones
    options = {o.mode.id: o for o in meta.modes(player.id)}
    assert options["chaos"].unlocked
    assert not options["j54"].unlocked and "Poker Head" in options["j54"].hint


def test_a_low_stake_win_does_not_open_poker_head(guided):
    player = meta.create_player(1, "New")
    started = meta.start_run(player.id, "normal", stake=40)
    c = started.controller
    c.run.money = c.config.target_money - 1
    _win_a_hand(c)
    assert onboarding.CLASSIC_MAX_WIN not in meta.finish_run(started.run_id, c).milestones


def test_the_bet_cap_lifts_after_three_classic_runs(guided):
    player = meta.create_player(1, "New")
    for n in range(onboarding.CAPPED_RUNS):
        started = meta.start_run(player.id, "normal", stake=40)
        assert started.config.max_bet_fraction == onboarding.CAP_FRACTION
        c = started.controller
        reward = _lose(started)
        assert (onboarding.BET_CAP_LIFTED in reward.milestones) == (n == onboarding.CAPPED_RUNS - 1)
        meta.claim_relief(player.id)
    started = meta.start_run(player.id, "normal", stake=40)
    assert started.config.max_bet_fraction > onboarding.CAP_FRACTION and not started.notes


def test_reach_records_once_and_rejects_unknown_milestones(guided):
    player = meta.create_player(1, "New")
    assert meta.reach(player.id, onboarding.TUTORIAL)
    assert not meta.reach(player.id, onboarding.TUTORIAL)
    with pytest.raises(meta.MetaError):
        meta.reach(player.id, "nonsense")


def _win_a_hand(c: GameController) -> None:
    """Play hands with the chart until the run ends (the money is set one hand from the goal)."""
    for _ in range(200):
        if c.phase == TablePhase.RUN_OVER:
            return
        if c.phase == TablePhase.ROUND_OVER:
            c.next_round()
            continue
        if c.phase == TablePhase.BETTING:
            c.run.money = max(c.run.money, c.config.target_money - c.bet_limits(c.run.money)[1])
            c.place_bet(c.bet_limits(c.run.money)[1])
        elif c.phase == TablePhase.CHAOS:
            c.resolve_chaos()
        elif c.phase == TablePhase.PLAYER_TURN:
            c.stand()
        elif c.phase == TablePhase.DEALER_TURN:
            c.dealer_step()
    raise AssertionError("no win in 200 steps")


def _lose(started):
    """Go broke between hands: the run ends in defeat."""
    c = started.controller
    c.run.money = 0
    c.check_terminal()
    assert c.run_end is not None and c.run_end.kind == "defeat"
    return meta.finish_run(started.run_id, c)


def test_the_first_relief_is_a_milestone_and_later_ones_are_not(guided):
    player = meta.create_player(1, "New")
    for n in range(2):
        started = meta.start_run(player.id, "normal", stake=40)
        with meta.service()._db() as db, db:
            db.execute("UPDATE player SET tokens = 0 WHERE id = ?", (player.id,))
        reward = _lose(started)
        assert any(label == "Relief from Poker Head" for label, _ in reward.breakdown)
        assert (onboarding.FIRST_RELIEF in reward.milestones) == (n == 0)
