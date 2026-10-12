"""Balance v1 mechanics: bankroll-scaled prices, shop rerolls, calm offline
Chaos rounds, Reverse Bust as a push and the consumable kinds a player brings."""

from __future__ import annotations

from dataclasses import replace

import pytest

from chaos_blackjack import meta
from chaos_blackjack.ai.pipeline import OfflineChaosStub
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.shop import ShopState, shop_prices
from chaos_blackjack.app.view import Action
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.plugins.reverse_bust import ReverseBustModifier
from chaos_blackjack.rules.rule_engine import DefaultBlackjackRules, RuleContext


@pytest.fixture
def svc():
    s = install_fake(demo=False)
    yield s
    s._conn.close()
    meta.use_service(None)


def test_percentage_prices_follow_the_bankroll_with_a_floor() -> None:
    listed = {"peek": 6, "fate_oracle": 18, "example_trim": 20}
    pct = frozenset({"peek", "fate_oracle"})
    assert shop_prices(listed, pct, 100, 100) == {"peek": 6, "fate_oracle": 18, "example_trim": 20}
    assert shop_prices(listed, pct, 250, 100) == {"peek": 15, "fate_oracle": 45, "example_trim": 20}
    assert shop_prices(listed, pct, 30, 100) == {"peek": 6, "fate_oracle": 18, "example_trim": 20}  # floor
    assert shop_prices({"peek": 1}, pct, 10, 10)["peek"] == 1  # never free


def test_restock_prices_use_the_bankroll_at_restock() -> None:
    c = GameController(RunConfig(seed=2))
    c.run.money = 200
    c.shop = c._roll_shop()
    expected = shop_prices(c.config.shop_prices, frozenset(c.config.shop_bankroll_pct), 200, 100)
    assert all(o.price == expected[o.item] for o in c.shop.offers)


def test_reroll_once_per_stock_costs_chips_and_survives_saves() -> None:
    c = GameController(RunConfig(seed=4))
    assert c.view().shop_reroll_price == 3 and c.view().can(Action.REROLL)
    c.reroll_shop()
    assert c.run.money == 97 and c.shop.rerolled and c.view().shop_reroll_price is None
    assert not c.view().can(Action.REROLL) and c.shop.stock_round == 1
    with pytest.raises(ActionError):
        c.reroll_shop()
    again = ShopState.from_dict(c.shop.to_dict())
    assert again == c.shop


def test_reroll_needs_enough_chips_to_keep_betting() -> None:
    c = GameController(RunConfig(seed=4, start_money=11))
    assert not c.view().can(Action.REROLL)
    with pytest.raises(ActionError):
        c.reroll_shop()


def test_free_rerolls_are_counted_per_run_across_restocks() -> None:
    c = GameController(RunConfig(seed=4, free_rerolls=1, shop_refresh_rounds=1))
    assert c.reroll_price() == 0
    c.reroll_shop()
    assert c.run.money == 100 and c.shop.free_rerolls_used == 1
    c.shop = ShopState(c.shop.stock_round, c.shop.offers, free_rerolls_used=1)  # new stock keeps the count
    assert c.reroll_price() == 3


def test_calm_rounds_and_rule_weights_in_the_offline_ai() -> None:
    stub = OfflineChaosStub(choices=(("", {}, 1.0),))
    assert stub.complete("", "") == '{"action":"noop"}'
    stub = OfflineChaosStub(choices=(("great_crash", {}, 1.0), ("", {}, 0.0)))
    assert "great_crash" in stub.complete("", "")
    assert RunConfig().chaos_stub[-1] == ("", {}, 15.0)


def test_reverse_bust_turns_a_player_bust_into_a_push() -> None:
    rules = DefaultBlackjackRules()
    ctx = RuleContext(modifiers=ActiveModifiers().with_added(ReverseBustModifier()))
    st = GameState((Card(Rank("K")), Card(Rank("Q")), Card(Rank("5"))), (Card(Rank("10")), Card(Rank("7"))), (),
                   GamePhase.RESOLVED)
    assert rules.compare_player_dealer(st, ctx) == "push"
    assert rules.compare_player_dealer(st, RuleContext(modifiers=ActiveModifiers())) == "dealer"


def test_bring_limit_and_bag_space(svc) -> None:
    p = meta.create_player(1, "Bag")
    svc.grant_tokens(p.id, 200)
    for u in ("start_peek", "start_shield", "start_swap"):
        meta.buy_upgrade(p.id, u)
    with pytest.raises(meta.MetaError, match="up to 2 kinds"):
        meta.start_run(p.id, "normal", consumables=["start_peek", "start_shield", "start_swap"])
    assert meta.get_player(p.id).upgrades["start_peek"] == 1  # nothing spent
    meta.buy_upgrade(p.id, "bag_space")
    run = meta.start_run(p.id, "normal", consumables=["start_peek", "start_shield", "start_swap"])
    assert sorted(run.config.starting_items) == ["peek", "shield", "swap"]


def test_chaos_victory_pays_the_bonus(svc) -> None:
    from chaos_blackjack.logic.run_end_policy import RunEndResult
    from chaos_blackjack.app.view import TablePhase

    p = meta.create_player(1, "Bonus")
    run = meta.start_run(p.id, "chaos")
    c = run.controller
    c.run = replace(c.run, money=300, round=12)
    c.run_end = RunEndResult("victory", "Won")
    c.phase = TablePhase.RUN_OVER
    reward = meta.finish_run(run.run_id, c)
    run_lines = {k: v for k, v in reward.breakdown if not k.startswith("Achievement: ")}
    assert run_lines == {"Victory": 10, "Chaos bonus": 4}
    assert reward.tokens == 14 + sum(u.tokens for u in reward.unlocked)
    assert any(u.cosmetic_id == "table_chaos" for u in reward.unlocked)
