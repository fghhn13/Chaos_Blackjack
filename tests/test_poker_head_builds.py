"""Poker Head builds: effects, choices, moves, money and public boundaries.

docs/design/ITEM_ARCHITECTURE.md is the contract; docs/design/POKER_HEAD_EFFECTS.zh-CN.md the effects.
"""

from dataclasses import FrozenInstanceError, replace

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.parts import PartContext, build_part
from chaos_blackjack.app.shop import ShopOffer, ShopState
from chaos_blackjack.app.view import Action, TablePhase
from chaos_blackjack.app.widgets import ListWidget, Slots
from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.modes import get_mode
from chaos_blackjack.poker_head.catalog import CORES, PRODUCTS, SHOP_IDS
from chaos_blackjack.poker_head.ownership import Holdings
from chaos_blackjack.poker_head import environment as env


# The director (poker_head/director.py) never acts in these scenarios; tests set rules themselves.
DIRECTOR_OFF = {"chaos.director.stages": "[[1, 0, 3, 99]]"}


def card(rank, suit="♠"):
    return Card(Rank(rank), suit)


def config(unlock_all=0, **overrides):
    cfg = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=7, use_llm=False))
    # Scenarios use the real random shelf; the "every product" testing switch is tested on its own.
    settings = {**cfg.mode_settings, "chaos.unlock_all": unlock_all, **DIRECTOR_OFF}
    return replace(cfg, enable_chaos=False, mode_settings=settings, **overrides)


def controller(core="ph_margin", **overrides):
    c = GameController(config(**overrides), save_fn=lambda d, n: n)
    # Scenario fixtures pick a build directly; the opening invitation is tested on its own.
    c.choice = None
    c.table.loadout.core = core
    c.table.holdings = Holdings()
    c.table._sync_items()
    c.shop = c.table.roll_shop()
    c.drain_notices()
    return c


def equip(c, *ids):
    c.table.loadout.equipped = list(ids)


def deal(c, player=("10", "6"), dealer=("10", "7"), deck=("2", "3", "4"), bet=10):
    c.table.prepared = tuple(card(x) for x in (*player, *dealer, *deck))
    c.table.prepared_round = c.run.round
    c.place_bet(bet)


def offer(c, item):
    c.shop = ShopState(c.run.round, (ShopOffer(item, c.config.shop_prices[item]),))


def item(c, name, paid=0):
    holding = c.table.holdings.add(name, paid)
    c.table._sync_items()
    return holding


def finish(c):
    c.stand()
    c.finish_dealer()


# --- opening, catalog and choices -----------------------------------------------------


def test_catalog_has_41_products_and_the_opening_choice_is_reproducible():
    assert len(PRODUCTS) == 41 and len(CORES) == 5
    a, b = AgentSession.new(mode="chaos", seed=7), AgentSession.new(mode="chaos", seed=7)
    obs = a.observe()
    assert obs == b.observe() and obs["target"] == 500
    assert obs["legal_actions"] == ["choose"]          # the invitation cannot be cancelled
    choice = obs["choice"]
    assert not choice["cancellable"] and [o["id"] for o in choice["options"]][-1] == "cash"
    assert obs["shop"]["offers"] == []                 # nothing is sold before the answer
    core = choice["options"][0]["id"]
    assert a.execute({"cmd": "choose", "option": core})["ok"]
    assert a.controller.table.loadout.core == core
    assert len(a.controller.shop.offers) == (4 if core == "ph_account" else 3)
    assert a.observe()["table"]["public"]["core"]["id"] == core


def test_declining_the_core_pays_30_and_blocks_amendments_for_the_run():
    s = AgentSession.new(mode="chaos", seed=7)
    assert s.execute({"cmd": "choose", "option": "cash"})["ok"]
    c = s.controller
    assert c.run.money == 130 and c.table.loadout.no_core and c.table.loadout.core is None
    assert not c.table.stockable("ph_change")
    offer(c, "ph_change")
    assert c.view().shop_offers[0].reason.startswith("You took the opening chips")


def test_a_pending_choice_allows_only_choose_cancel_and_save():
    c = controller()
    equip(c, "ph_long_reward", "ph_mark")
    offer(c, "ph_sleeve")
    c.buy("ph_sleeve")
    assert c.view().available_actions == {Action.CHOOSE, Action.CANCEL, Action.SAVE}
    with pytest.raises(ActionError):
        c.place_bet(10)
    assert all(m.action in (Action.CHOOSE, Action.CANCEL) for m in c.moves())


def test_replacement_charges_nothing_until_confirmed_and_cancel_is_free():
    c = controller()
    equip(c, "ph_long_reward", "ph_mark")
    offer(c, "ph_sleeve")
    c.buy("ph_sleeve")
    assert c.choice.kind == "replace" and c.run.money == 100
    with pytest.raises(ActionError):
        c.choose("not_equipped")
    assert c.choice is not None and c.run.money == 100
    c.cancel_choice()
    assert c.choice is None and c.run.money == 100 and not c.shop.offers[0].sold
    c.buy("ph_sleeve")
    c.choose("ph_mark")
    assert c.run.money == 45 and c.table.loadout.equipped == ["ph_long_reward", "ph_sleeve"]
    assert not c.table.stockable("ph_sleeve") and not c.table.stockable("ph_long_reward")
    assert c.table.stockable("ph_mark")                         # a replaced permanent can be offered again


def test_a_choice_survives_save_and_load():
    c = controller()
    equip(c, "ph_long_reward", "ph_mark")
    offer(c, "ph_sleeve")
    c.buy("ph_sleeve")
    loaded = GameController.from_save(RunSaveData.from_dict(c.save("x").to_dict()), save_fn=lambda d, n: n)
    assert loaded.choice == c.choice
    loaded.choose("ph_mark")
    assert loaded.table.loadout.equipped == ["ph_long_reward", "ph_sleeve"]


def test_amendment_keeps_the_build_and_cancel_keeps_the_letter():
    c = controller("ph_margin")
    equip(c, "ph_court")
    letter = c.table.holdings.add("ph_change", 20, ("ph_margin", "ph_account"))
    c.table._sync_items()
    c.use_item("ph_change")
    assert [o.id for o in c.choice.options] == ["ph_account"]   # the current core is never offered
    c.cancel_choice()
    assert c.table.holdings.get(letter.uid) is not None
    c.use_item("ph_change")
    c.choose("ph_account")
    assert c.table.loadout.core == "ph_account" and c.table.loadout.equipped == ["ph_court"]
    assert "ph_change" not in c.run.items
    assert len(c.shop.offers) == 4                              # Private Account's extra slot appears at once


# --- hand values ---------------------------------------------------------------------------


def test_approx_maps_before_bust_but_does_not_create_starting_natural():
    c = controller("ph_approx")
    deal(c, player=("10", "10"), dealer=("10", "8"), deck=("2",))
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 21
    c.hit()
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 21
    finish(c)
    assert c.last_result.outcome == "player" and c.run.money == 110


def test_approx_does_not_ignore_a_lower_chaos_bust_limit():
    c = controller("ph_approx")
    c.table.environment = [env.bust("player", 19)]
    deal(c, player=("10", "10"))
    assert c.phase == TablePhase.ROUND_OVER and c.last_result.player_bust


def test_player_effects_do_not_change_dealer_values():
    c = controller()
    equip(c, "ph_court")
    deal(c, player=("K", "Q"), dealer=("K", "Q"), deck=("J", "7"))
    assert c.hand_value(c.state.player_hand) == 10
    assert c.hand_value(c.state.dealer_hand, "dealer") == 20
    c.hit()
    c.hit()
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 22   # margin: bust above 22
    finish(c)
    assert c.last_result.outcome == "player"


def test_risk_pointer_uses_the_same_player_values():
    c = controller()
    item(c, "ph_radar")
    deal(c, player=("10", "6"), deck=("6",))
    assert "safe" in c.use_item("ph_radar").message   # 22 is not a bust with Room to Breathe


def test_multi_card_rewards_combine_once():
    c = controller()
    equip(c, "ph_long_reward", "ph_five_reward")
    deal(c, player=("2", "3"), deck=("4", "5", "6"), dealer=("10", "8"))
    for _ in range(3):
        c.hit()
    finish(c)
    assert c.last_result.delta == 22


@pytest.mark.parametrize("both", [False, True])
def test_borrowed_glory_overrides_dealer_natural_and_natural_push(both):
    c = controller("ph_approx")
    equip(c, "ph_borrow", "ph_jackpot")
    deal(c, player=("A", "K") if both else ("2", "3"), dealer=("A", "K"))
    assert c.phase == TablePhase.ROUND_OVER and c.last_result.outcome == "blackjack"
    assert c.last_result.delta == 30 and not c.last_result.dealer_blackjack


# --- surrender -------------------------------------------------------------------------------


def test_surrender_claim_refunds_undiscounted_previous_fee():
    c = controller("ph_retreat")
    equip(c, "ph_loss_discount", "ph_claim")
    deal(c, bet=40)
    c.surrender()
    assert c.last_result.delta == -4 and c.table.claim["refund"] == 20
    c.next_round()
    deal(c, player=("10", "10"), dealer=("10", "8"), bet=5)
    finish(c)
    assert c.last_result.delta == 25 and c.table.claim is None


def test_late_surrender_after_hitting():
    c = controller()
    equip(c, "ph_late_retreat")
    deal(c, player=("2", "3"), deck=("4",))
    c.hit()
    assert Action.SURRENDER in c.view().available_actions
    c.surrender()
    assert c.last_result.delta == -5


def test_waiver_has_no_claim_but_arms_a_real_natural_next_round():
    c = controller("ph_retreat")
    equip(c, "ph_claim", "ph_ace")
    item(c, "ph_waiver")
    deal(c)
    assert c.use_item("ph_waiver").ok
    assert c.last_result.delta == 0 and c.table.claim is None and c.table.ace_pending
    assert c.view().table_public.ace_armed
    c.next_round()
    deal(c, player=("2", "K"), dealer=("10", "8"))
    assert c.last_result.outcome == "blackjack"
    assert c.state.player_hand[0].rank == "A" and not c.table.ace_pending


def test_replacing_a_permanent_drops_what_it_held():
    c = controller()
    equip(c, "ph_claim", "ph_ace")
    c.table.claim, c.table.ace_pending = {"round": 2, "refund": 5}, True
    c.run.money = 400
    offer(c, "ph_risk")
    c.buy("ph_risk", "ph_claim")
    assert c.table.claim is None and c.table.ace_pending
    offer(c, "ph_audit")
    c.buy("ph_audit", "ph_ace")
    assert not c.table.ace_pending


# --- double --------------------------------------------------------------------------------------


def test_late_double_fourfold_and_reduced_loss():
    c = controller("ph_stakes")
    equip(c, "ph_late_double", "ph_risk")
    item(c, "ph_quad")
    deal(c, player=("2", "3"), deck=("10", "10"))
    c.hit()
    assert c.use_item("ph_quad").ok
    c.double_down()
    assert c.last_result.bet == 40 and c.last_result.delta == -30


def test_quad_without_sufficient_funds_is_not_consumed():
    c = controller("ph_stakes")
    item(c, "ph_quad")
    deal(c, bet=30)
    result = c.use_item("ph_quad")
    assert not result.ok and "Not enough chips" in result.message
    assert "ph_quad" in c.run.items and c.run.current_bet == 30


def test_audit_reveals_high_dealer_hole_only():
    c = controller()
    equip(c, "ph_audit")
    deal(c, dealer=("5", "K"))
    assert c.hole_revealed
    low = controller()
    equip(low, "ph_audit")
    deal(low, dealer=("10", "7"))
    assert not low.hole_revealed


# --- consumables, phases and the forecast -----------------------------------------------------------


def test_every_item_shows_when_it_can_be_used():
    c = controller()
    item(c, "ph_oracle")
    item(c, "ph_peek")
    items = {i.id: i for i in c.view().items}
    assert items["ph_oracle"].when == "Before betting" and items["ph_oracle"].usable
    assert items["ph_peek"].when == "On your turn" and not items["ph_peek"].usable
    assert items["ph_peek"].reason == "On your turn only."


def test_prebet_forecast_matches_deal_and_survives_save_without_public_leak():
    c = controller()
    item(c, "ph_oracle")
    assert c.use_item("ph_oracle").ok
    expected = c.table.round.forecast[:]
    deal_order = [f"{x.rank}{x.suit}" for x in c.table.prepared]
    session = AgentSession(c, seed=7)
    resumed = AgentSession.from_state(session.to_state())
    obs = resumed.observe()
    assert obs == session.observe() and obs["table"]["public"]["forecast"] == expected
    text = str(obs)
    assert "prepared" not in text
    assert not any(x in text for x in deal_order[6:12])   # nothing beyond the forecast leaks
    assert not resumed.controller.can_use_item("ph_oracle")
    resumed.controller.buy(resumed.controller.shop.offers[0].item)   # shopping does not move the deal
    resumed.controller.reroll_shop()
    resumed.controller.place_bet(5)
    assert [f"{x.rank}{x.suit}" for x in resumed.controller.state.deck[:2]] == expected


def test_card_effects_mark_the_forecast_out_of_date():
    c = controller()
    item(c, "ph_oracle")
    item(c, "ph_aces")
    c.use_item("ph_oracle")
    deal(c, deck=("3", "A", "7"))
    assert c.use_item("ph_aces").ok
    assert c.view().table_public.forecast_changed


def test_aces_reorder_stably_and_cannot_be_used_before_bet():
    c = controller()
    item(c, "ph_aces")
    assert not c.can_use_item("ph_aces")
    deal(c, deck=("3", "A", "7", "A", "2"))
    assert c.use_item("ph_aces").ok
    assert [x.rank for x in c.state.deck] == ["A", "A", "3", "7", "2"]
    item(c, "ph_aces")
    assert c.item_usability("ph_aces").reason == "Every ace is already on top."


def test_per_round_buffer_cannot_stack_and_spare_sleeve_is_once():
    c = controller()
    equip(c, "ph_sleeve")
    item(c, "ph_buffer")
    item(c, "ph_buffer")
    assert c.use_item("ph_buffer").ok and not c.can_use_item("ph_buffer")
    deal(c, deck=("2", "3"))
    assert [m.action for m in c.moves() if m.table] == ["ph_sleeve"]
    c.perform("ph_sleeve")
    assert c.state.player_hand[0].rank == "2"
    with pytest.raises(ActionError):
        c.perform("ph_sleeve")


def test_rule_removal_asks_for_its_target_and_suppression_preserves_rules():
    c = controller()
    c.table.environment = [env.bust("player", 19, rounds=3)]
    item(c, "ph_silence")
    assert c.use_item("ph_silence").ok
    deal(c, player=("10", "10"), dealer=("10", "8"))
    assert c.phase == TablePhase.PLAYER_TURN                # 20 is safe while the rule is silenced
    finish(c)
    c.next_round()
    assert [r.type for r in c.table.env_rules()] == ["bust"]
    item(c, "ph_remove")
    assert c.use_item("ph_remove").ok and c.choice.kind == "target"
    assert "ph_remove" in c.run.items                       # nothing spent before the answer
    c.choose("bust")
    assert not c.table.environment and "ph_remove" not in c.run.items
    assert c.table.env_history[-1]["cause"] == "removed"


def test_starter_alias_plays_as_its_build_counterpart():
    c = controller()
    item(c, "fate_oracle")
    view = c.view().items[0]
    assert view.usable and view.name == "Fate Forecast" and view.when == "Before betting"
    assert c.use_item("fate_oracle").ok and len(c.table.round.forecast) == 2


# --- money ------------------------------------------------------------------------------------------


def test_cash_investment_and_debt_are_distinct_and_cannot_inflate_victory():
    c = controller("ph_account")
    offer(c, "ph_deposit")
    c.buy("ph_deposit")
    assert c.run.money == 70 and c.table.net_assets() == 100
    offer(c, "ph_loan")
    c.buy("ph_loan")
    assert c.run.money == 110 and c.table.net_assets() == 90 and c.table.ledger.debt == 50
    assert not c.table.stockable("ph_loan")
    public = c.view().table_public
    assert (public.cash, public.invested, public.debt, public.net_assets) == (110, 30, 50, 90)


def test_borrowed_cash_never_wins_and_victory_settles_at_cost():
    c = controller("ph_account")
    c.run.money = 480
    offer(c, "ph_loan")
    c.buy("ph_loan")
    assert c.run.money == 520 and c.run_end is None           # net assets 470
    offer(c, "ph_deposit")
    c.buy("ph_deposit")
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=40)
    finish(c)
    assert c.run_end.kind == "victory"
    assert c.run.money == 510 and not c.table.ledger.positions  # 530 cash + 30 principal − 50 owed


def test_yield_applies_to_profit_only_and_discount_excludes_financial_principal():
    c = controller("ph_account")
    equip(c, "ph_discount", "ph_yield")
    offer(c, "ph_deposit")
    c.buy("ph_deposit")
    assert c.run.money == 70
    for _ in range(2):
        deal(c, player=("10", "7"), dealer=("10", "7"))
        finish(c)
        if c.phase == TablePhase.ROUND_OVER:
            c.next_round()
    assert c.run.money == 112 and not c.table.ledger.positions


def test_stock_pays_90_or_nothing_from_a_private_draw():
    outcomes = set()
    for seed in range(12):
        c = controller("ph_account", seed=seed)
        offer(c, "ph_stock")
        c.buy("ph_stock")
        for _ in range(2):
            deal(c, player=("10", "7"), dealer=("10", "7"))
            finish(c)
            c.next_round()
        outcomes.add(c.run.money - 70)
    assert outcomes == {0, 90}


def test_matured_positions_are_never_paid_twice():
    c = controller("ph_account")
    offer(c, "ph_deposit")
    c.buy("ph_deposit")
    deal(c, player=("10", "7"), dealer=("10", "7"))
    finish(c)
    c.run.round -= 1   # the settled round again: a repeated call is ignored
    c.table.after_settle(c.state, "push", c.loop.modifiers, c.run)
    c.run.round += 1
    assert c.table.ledger.positions[0].remaining == 1


def test_buyback_asks_for_a_target_and_can_end_the_run():
    c = controller()
    receipt = item(c, "ph_buyback", paid=6)
    target = item(c, "ph_aces", paid=17)
    c.run.money = 483
    assert c.use_item("ph_buyback").ok and c.choice.kind == "target"
    assert [o.id for o in c.choice.options] == [target.uid]
    c.choose(target.uid)
    assert c.phase == TablePhase.RUN_OVER and c.run_end.kind == "victory"
    assert c.run.money == 500 and not c.table.holdings.items
    assert receipt.uid not in [h.uid for h in c.table.holdings.items]


def test_free_refresh_is_extra_and_replacement_cannot_restore_it():
    c = controller()
    equip(c, "ph_refresh")
    before = c.shop.offers
    c.reroll_shop()
    assert c.run.money == 100 and c.shop.offers != before
    equip(c)
    equip(c, "ph_refresh")
    assert c.reroll_price() == 3
    c.reroll_shop()
    assert c.run.money == 97 and c.reroll_price() is None


def test_permanent_offers_grow_more_likely_with_the_round():
    def permanents(round_no):
        total = 0
        for seed in range(60):
            c = controller(seed=seed)
            c.run.round = round_no
            total += sum(PRODUCTS[o.item].kind == "permanent" for o in c.table.roll_shop().offers)
        return total
    assert permanents(1) < permanents(10)


# --- moves, views and boundaries ----------------------------------------------------------------------


def _acts(c, part, variant="full"):
    widgets = build_part(part, PartContext(c, c.view()), variant)
    for w in widgets:
        for x in (w.entries if isinstance(w, ListWidget) else w.slots if isinstance(w, Slots) else ()):
            if x.act is not None:
                yield x.act


@pytest.mark.parametrize("phase", ["betting", "player_turn"])
def test_gui_acts_and_agent_actions_come_from_the_same_moves(phase):
    c = controller()
    equip(c, "ph_sleeve")
    for name in ("ph_oracle", "ph_peek", "ph_quad"):
        item(c, name)
    if phase == "player_turn":
        deal(c, deck=("2", "3"))
    moves = {(m.action, m.arg): m.enabled for m in c.moves()}
    acts = [*_acts(c, "core.items"), *_acts(c, "core.items", "compact"), *_acts(c, "core.actions")]
    assert acts and all(moves[(a.id, a.arg)] == a.enabled for a in acts)
    obs = AgentSession(c, seed=7).observe()
    assert ("use_item" in obs["legal_actions"]) == any(i["usable"] for i in obs["items"])
    assert ("perform" in obs["legal_actions"]) == any(a["enabled"] for a in obs["table_actions"])
    assert {i["id"]: i["usable"] for i in obs["items"]} == {i: moves[("use_item", i)] for i in c.run.items}


def test_public_snapshot_is_frozen_and_detached():
    c = controller()
    equip(c, "ph_claim")
    c.table.claim = {"round": 2, "refund": 5}
    public, saved = c.view().table_public, c.table.to_dict()
    with pytest.raises(FrozenInstanceError):
        public.claim_refund = 999
    data = public.to_dict()
    data["equipped"].clear()
    saved["loadout"]["equipped"].clear()
    assert c.table.claim["refund"] == 5 and c.table.loadout.equipped == ["ph_claim"]


def test_legacy_chaos_save_does_not_acquire_new_build_or_goal():
    legacy = GameController(RunConfig(mode="chaos", enable_chaos=True,
                                     mode_settings={"chaos.build_version": 0}, use_llm=False))
    old = legacy.save("legacy")
    loaded = GameController.from_save(old)
    assert loaded.table is None and loaded.run.target_money == 300 and loaded.choice is None


def test_modeless_chaos_keeps_the_classic_shop_and_goal():
    s = AgentSession.new(seed=7, chaos=True)
    c = s.controller
    assert c.table is None and c.choice is None and c.run.target_money == 300
    assert not any(o.item.startswith("ph_") for o in c.shop.offers)
    assert s.observe()["legal_actions"] == ["bet", "buy", "reroll"]


def test_classic_items_wait_for_the_players_turn():
    s = AgentSession.new(seed=7)
    c = s.controller
    c.run.items = ("peek",)
    peek = c.view().items[0]
    assert not peek.usable and peek.reason == "Use it on your turn." and peek.when == "On your turn"
    c.place_bet(10)
    if c.phase == TablePhase.PLAYER_TURN:
        assert c.view().items[0].usable


def test_saves_round_trip_the_whole_build():
    c = controller("ph_account")
    equip(c, "ph_court", "ph_claim")
    item(c, "ph_peek", paid=4)
    offer(c, "ph_bond")
    c.buy("ph_bond")
    c.table.claim = {"round": 2, "refund": 10}
    data = c.save("x").to_dict()
    loaded = GameController.from_save(RunSaveData.from_dict(data), save_fn=lambda d, n: n)
    assert loaded.table.to_dict() == c.table.to_dict()
    assert loaded.view().table_public == c.view().table_public
    assert loaded.run.items == ("ph_peek",)


# --- the "every product" testing switch (mode.chaos.unlock_all) ---------------------------


def test_unlock_all_lists_every_product_grouped_and_without_rerolls():
    c = controller("ph_margin", unlock_all=1)
    offers = c.shop.offers
    assert {o.item for o in offers} == set(SHOP_IDS)
    groups = [PRODUCTS[o.item].to_def().group for o in offers]
    assert groups == sorted(groups, key=["consumable", "permanent", "special"].index)
    assert c.reroll_price() is None and Action.REROLL not in c.view().available_actions
    deposit = next(o for o in c.view().shop_offers if o.item == "ph_deposit")
    assert deposit.affordable and deposit.group == "special"   # no Private Account needed


def test_unlock_all_keeps_the_rules_that_are_not_unlocks():
    c = controller("ph_margin", unlock_all=1)
    equip(c, "ph_court")
    court = next(o for o in c.view().shop_offers if o.item == "ph_court")
    assert not court.affordable and court.reason == "Already equipped."
    c.buy("ph_loan")
    loan = next(o for o in c.view().shop_offers if o.item == "ph_loan")
    assert loan.sold and c.table.ledger.debt == 50
    c.table.set_core("ph_account")
    assert len(c.shop.offers) == len(SHOP_IDS)                 # a core change never trims the shelf


def test_icon_groups_follow_the_catalog():
    groups = {p.id: p.to_def().group for p in PRODUCTS.values()}
    assert groups["ph_court"] == "permanent" and groups["ph_peek"] == "consumable"
    assert {groups[x] for x in ("ph_margin", "ph_deposit", "ph_loan", "ph_gift", "ph_change")} == {"special"}


# --- two build slots and discarding ------------------------------------------------------------


def test_the_shipped_build_has_two_slots():
    c = controller()
    assert c.view().table_public.slots == 2


def test_discarding_asks_first_frees_the_slot_and_returns_the_permanent_to_the_shop():
    c = controller()
    equip(c, "ph_claim", "ph_ace")
    c.table.claim, c.table.ace_pending = {"round": 2, "refund": 5}, True
    assert {(m.action, m.arg) for m in c.moves() if m.table} == {("ph_discard", "ph_claim"), ("ph_discard", "ph_ace")}
    assert not any(m.listed for m in c.moves() if m.action == "ph_discard")   # shown in the bag, not as actions
    c.perform("ph_discard", "ph_claim")
    assert c.choice.kind == "discard" and c.table.loadout.equipped == ["ph_claim", "ph_ace"]
    c.cancel_choice()
    assert c.table.loadout.equipped == ["ph_claim", "ph_ace"]
    c.perform("ph_discard", "ph_claim")
    c.choose("ph_claim")
    assert c.table.loadout.equipped == ["ph_ace"] and c.table.claim is None and c.run.money == 100
    assert c.table.stockable("ph_claim")
    c.shop = c.table.roll_shop()
    assert "ph_claim" in {x for s in range(40) for x in _stock(c, s)}


def _stock(c, n):
    c.table.shop_counters.roll_number = n
    return [o.item for o in c.table.roll_shop(reroll=True).offers]


def test_permanents_are_discarded_only_between_hands():
    c = controller()
    equip(c, "ph_court")
    deal(c, player=("10", "6"), deck=("2", "3"))
    assert not any(m.action == "ph_discard" for m in c.moves())
    with pytest.raises(ActionError):
        c.perform("ph_discard", "ph_court")


def test_the_bag_lists_the_build_with_discard_acts():
    c = controller()
    equip(c, "ph_court")
    acts = [a for a in _acts(c, "poker_head.loadout")]
    assert [(a.id, a.arg, a.enabled) for a in acts] == [("ph_discard", "ph_court", True)]


def test_the_goal_is_net_assets_and_shown_apart_from_the_bankroll():
    c = controller("ph_account")
    offer(c, "ph_loan")
    c.buy("ph_loan")
    assert c.view().money == 140 and c.view().goal == ("Net assets", 90, 500)
    plain = AgentSession.new(seed=7).controller
    assert plain.view().goal is None
