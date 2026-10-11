"""Regression coverage for opening settlements and the shorter run economy."""

import json
from pathlib import Path

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.ai.pipeline import OfflineChaosStub, StubLLM
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.content.builtin_persona import default_persona
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.rules.modifiers import ActiveModifiers


def deal(controller, player, dealer, bet=10):
    def new_round(**kwargs):
        controller.loop.modifiers = ActiveModifiers()
        return GameState(tuple(Card(Rank(r), s) for r, s in player),
                         tuple(Card(Rank(r), s) for r, s in dealer), (), GamePhase.PLAYER_TURN)
    controller.loop.new_round = new_round
    controller.place_bet(bet)


@pytest.mark.parametrize("player,dealer,outcome,delta", [
    ([("A", "♣"), ("K", "♣")], [("10", "♥"), ("8", "♥")], "blackjack", 15),
    ([("10", "♥"), ("8", "♥")], [("A", "♣"), ("K", "♣")], "dealer", -10),
    ([("A", "♣"), ("K", "♣")], [("A", "♥"), ("Q", "♥")], "push", 0),
])
def test_original_naturals_settle_before_any_chaos_call(player, dealer, outcome, delta):
    c = GameController(RunConfig(enable_chaos=True, use_llm=False))
    c.loop.pipeline.llm.complete = lambda *args: pytest.fail("A natural must not call Chaos")
    deal(c, player, dealer)
    assert c.phase == TablePhase.ROUND_OVER
    assert (c.last_result.outcome, c.last_result.delta) == (outcome, delta)
    assert not c.loop.modifiers.items


@pytest.mark.parametrize("rule,params,outcome", [
    ("suit_power", {}, "dealer"),
    ("fragile_bust", {}, "dealer"),
])
def test_chaos_opening_bust_settles_without_player_actions(rule, params, outcome):
    c = GameController(RunConfig(enable_chaos=True, use_llm=False))
    c.loop.pipeline.llm = StubLLM(json.dumps({"action": "apply_rule", "rule_id": rule, "params": params}))
    deal(c, [("10", "♥"), ("K", "♥")], [("Q", "♦"), ("K", "♦")])
    c.resolve_chaos()
    assert c.phase == TablePhase.ROUND_OVER
    assert c.last_result.player_bust
    assert c.last_result.outcome == outcome and c.last_result.delta == -10


def test_rule_modified_21_is_an_ordinary_hand():
    c = GameController(RunConfig(enable_chaos=True, use_llm=False))
    c.loop.pipeline.llm = StubLLM(json.dumps({"action": "apply_rule", "rule_id": "suit_power"}))
    deal(c, [("10", "♥"), ("9", "♦")], [("10", "♣"), ("7", "♠")])
    c.resolve_chaos()
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 21
    c.stand()
    c.finish_dealer()
    assert c.last_result.outcome == "player" and c.last_result.delta == 10


def test_low_bankroll_prices_and_purchase_reserve():
    c = GameController(RunConfig(start_money=20, shop_slots=6))
    prices = {o.item: o.price for o in c.view().shop_offers}
    assert prices == {"peek": 1, "danger_radar": 1, "swap": 1, "hole_card_hacker": 1, "fate_oracle": 2}
    assert GameController(RunConfig(start_money=9)).phase == TablePhase.RUN_OVER
    c = GameController(RunConfig(start_money=10, shop_slots=6))
    assert all(not o.affordable for o in c.view().shop_offers)
    with pytest.raises(ActionError):
        c.buy("peek")


def test_reroll_errors_explain_stock_and_required_funds():
    c = GameController(RunConfig(start_money=12))
    with pytest.raises(ActionError, match="at least 13"):
        c.reroll_shop()
    c = GameController(RunConfig(start_money=20))
    c.reroll_shop()
    assert c.run.money == 17 and c.view().shop_restock_in == 2
    with pytest.raises(ActionError, match="already rerolled"):
        c.reroll_shop()
    session = AgentSession(c, seed=1)
    assert not session.observe()["shop"]["reroll_affordable"]


def test_run_ends_before_a_restock_when_no_valid_bet_remains():
    c = GameController(RunConfig(start_money=12, shop_refresh_rounds=1))
    c.drain_notices()
    deal(c, [("10", "♣"), ("8", "♣")], [("A", "♥"), ("K", "♥")], bet=5)
    assert c.phase == TablePhase.RUN_OVER and c.run.money == 7
    assert NoticeKind.SHOP_RESTOCKED not in [n.kind for n in c.drain_notices()]


def test_bundled_persona_and_browser_resources_keep_default_rule_choices():
    persona = default_persona()
    assert persona.name == "Poker Head" and len(persona.portraits) == 8
    assert all(path.is_file() for path in persona.portraits.values())
    root = Path(__file__).resolve().parents[1]
    allowed = set((root / "browser/package-files.txt").read_text().splitlines())
    assert all(path.relative_to(root).as_posix() in allowed for path in persona.portraits.values())
    c = GameController(RunConfig(enable_chaos=True, use_llm=False))
    assert isinstance(c.loop.pipeline.llm, OfflineChaosStub)
    assert c.loop.pipeline.llm.choices == c.config.chaos_stub
