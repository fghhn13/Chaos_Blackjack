"""Shop: stock, buying, restocking, saves; and the item effects it sells."""

from __future__ import annotations

import pytest

from chaos_blackjack.agent.session import AgentSession
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.persistence import build_save_data
from chaos_blackjack.app.shop import ShopOffer, ShopState, roll_stock
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.registry import get_registry

PRICES = {"peek": 10, "swap": 20, "shield": 30}


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _ctrl(**cfg) -> GameController:
    return GameController(RunConfig(seed=1, shop_prices=dict(PRICES), **cfg), save_fn=lambda d, n: n)


def _play_round(c: GameController) -> None:
    c.place_bet(2)
    c.surrender()
    c.next_round()


def _rig(c: GameController, player, dealer, deck=()) -> None:
    c.state = GameState(tuple(player), tuple(dealer), tuple(deck), GamePhase.PLAYER_TURN,
                        inventory=c.state.inventory if c.state else ())


def test_stock_is_seeded_and_sorted_by_price() -> None:
    a = roll_stock(5, 1, PRICES, 2)
    assert a == roll_stock(5, 1, PRICES, 2)
    assert len(a.offers) == 2 and len({o.item for o in a.offers}) == 2
    assert [o.price for o in a.offers] == sorted(o.price for o in a.offers)
    assert len(roll_stock(5, 1, PRICES, 9).offers) == 3  # never more than the pool


def test_buy_spends_bankroll_and_sells_out() -> None:
    c = _ctrl()
    assert len(c.view().shop_offers) == 3
    c.buy("swap")
    v = c.view()
    assert v.money == 80 and [i.id for i in v.items] == ["swap"]
    assert next(o for o in v.shop_offers if o.item == "swap").sold
    assert NoticeKind.ITEM_BOUGHT in [n.kind for n in c.drain_notices()]
    with pytest.raises(ActionError):
        c.buy("swap")  # single purchase per restock
    with pytest.raises(ActionError):
        c.buy("fate_oracle")  # not on the shelves


def test_buy_must_leave_enough_to_bet() -> None:
    c = _ctrl(start_money=31)
    assert not next(o for o in c.view().shop_offers if o.item == "shield").affordable
    with pytest.raises(ActionError):
        c.buy("shield")
    c.buy("swap")
    assert c.view().money == 11


def test_shop_is_closed_during_a_round() -> None:
    c = _ctrl()
    c.place_bet(10)
    with pytest.raises(ActionError):
        c.buy("peek")


def test_bought_items_are_usable_next_hand() -> None:
    c = _ctrl()
    c.buy("peek")
    c.place_bet(10)
    assert c.use_item("peek").ok


def test_restocks_every_two_rounds() -> None:
    c = _ctrl()
    c.buy("peek")
    assert c.view().shop_restock_in == 2
    _play_round(c)
    assert c.view().shop_restock_in == 1
    assert next(o for o in c.view().shop_offers if o.item == "peek").sold  # same stock
    _play_round(c)
    v = c.view()
    assert v.round == 3 and v.shop_restock_in == 2
    assert c.shop.stock_round == 3 and not any(o.sold for o in v.shop_offers)
    assert NoticeKind.SHOP_RESTOCKED in [n.kind for n in c.drain_notices()]


def test_shop_survives_save_and_load() -> None:
    c = _ctrl()
    c.buy("peek")
    data = RunSaveData.from_dict(build_save_data(
        run=c.run, state=None, loop=c.loop, enable_chaos=False, shop=c.shop, shop_seed=c.shop_seed,
    ).to_dict())
    loaded = GameController.from_save(data, RunConfig(shop_prices=dict(PRICES)))
    assert loaded.shop == c.shop and loaded.shop_seed == c.shop_seed
    assert [i.id for i in loaded.view().items] == ["peek"]


def test_old_saves_without_a_shop_get_fresh_stock() -> None:
    c = _ctrl()
    data = build_save_data(run=c.run, state=None, loop=c.loop, enable_chaos=False)
    loaded = GameController.from_save(data, RunConfig(seed=1, shop_prices=dict(PRICES)))
    assert loaded.shop == c.shop


def test_shop_state_round_trips() -> None:
    s = ShopState(3, (ShopOffer("peek", 10, True), ShopOffer("swap", 20)))
    assert ShopState.from_dict(s.to_dict()) == s


# ------------------------------------------------------------ item effects


def test_hole_card_hacker_flips_the_hole_card() -> None:
    c = _ctrl()
    c.run.items = ("hole_card_hacker",)
    c.place_bet(10)
    _rig(c, [_c("9"), _c("7")], [_c("K"), _c("8", "♦")], deck=[_c("2")])
    assert c.view().dealer_cards[1].face_up is False
    assert c.use_item("hole_card_hacker").ok
    v = c.view()
    assert v.hole_revealed and v.dealer_cards[1].face_up and v.dealer_total == 18
    c.stand()
    c.finish_dealer()
    c.next_round()
    c.place_bet(10)
    assert c.view().dealer_cards[1].face_up is False  # only for that round


def test_shield_dispels_active_rules() -> None:
    c = _ctrl()
    c.run.items = ("shield",)
    c.place_bet(10)
    _rig(c, [_c("9"), _c("7")], [_c("K"), _c("8")])
    c.loop.modifiers = c.loop.modifiers.with_added(
        get_registry().build_chaos_rule("modify_card_value", {"delta": -1})
    )
    assert c.view().player_total == 14 and c.view().active_rules
    assert c.use_item("shield").ok
    v = c.view()
    assert v.active_rules == () and v.player_total == 16 and v.items == ()
    assert NoticeKind.CHAOS_DISPELLED in [n.kind for n in c.drain_notices()]


def test_shield_without_rules_is_kept() -> None:
    c = _ctrl()
    c.run.items = ("shield",)
    c.place_bet(10)
    assert not c.use_item("shield").ok
    assert [i.id for i in c.view().items] == ["shield"]


def test_item_that_busts_the_hand_settles_the_round() -> None:
    c = _ctrl()
    c.run.items = ("shield",)
    c.place_bet(10)
    _rig(c, [_c("K"), _c("6"), _c("6")], [_c("10"), _c("8")])
    c.loop.modifiers = c.loop.modifiers.with_added(
        get_registry().build_chaos_rule("modify_card_value", {"delta": -1})
    )
    assert c.view().player_total == 19
    c.use_item("shield")
    v = c.view()
    assert v.phase == TablePhase.ROUND_OVER and v.last_result.player_bust


# ------------------------------------------------------------------ agent


def test_agent_buy_persists_across_run_files() -> None:
    s = AgentSession.new(seed=7)
    offer = s.observe()["shop"]["offers"][0]
    r = s.execute({"cmd": "buy", "item": offer["item"]})
    assert r["ok"] and r["obs"]["bankroll"] == 100 - offer["price"]
    assert r["obs"]["items"][0]["id"] == offer["item"]
    again = AgentSession.from_state(s.to_state())
    sold = {o["item"]: o["sold"] for o in again.observe()["shop"]["offers"]}
    assert sold[offer["item"]] is True
    assert again.execute({"cmd": "buy"})["error"]["code"] == "invalid_argument"


def test_agent_hole_card_reveal_survives_reload() -> None:
    s = AgentSession.new(seed=7)
    s.controller.run.items = ("hole_card_hacker",)
    s.execute({"cmd": "bet", "amount": 10})
    if s.controller.phase != TablePhase.PLAYER_TURN:
        pytest.skip("seed dealt a natural")
    s.execute({"cmd": "act", "action": "use_item", "item": "hole_card_hacker"})
    again = AgentSession.from_state(s.to_state())
    assert "??" not in again.observe()["dealer"]["cards"]
