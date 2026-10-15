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


# Scenarios play at the reference scale: 100 chips, amounts as written for 100, a fixed goal of 500
# (chip scaling, the Full Haul window and real stakes have their own tests).
SCALE = {"start_money": 100, "target_money": 500, "target_multiple": 0.0, "exit_multiple": 0.0}


def config(unlock_all=0, **overrides):
    cfg = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=7, use_llm=False))
    # Scenarios use the real random shelf; the "every product" testing switch is tested on its own.
    settings = {**cfg.mode_settings, "chaos.unlock_all": unlock_all, "chaos.money_base": 100, "chaos.build_slots": 2,
                **DIRECTOR_OFF}
    return replace(cfg, enable_chaos=False, mode_settings=settings, **{**SCALE, **overrides})


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


def test_catalog_has_43_products_and_the_opening_choice_is_reproducible():
    assert len(PRODUCTS) == 43 and len(CORES) == 5
    a, b = AgentSession.new(mode="chaos", seed=7), AgentSession.new(mode="chaos", seed=7)
    obs = a.observe()
    assert obs == b.observe() and obs["target"] == 2400 and obs["bankroll"] == 400   # 400 brought, ceiling 6x
    assert obs["legal_actions"] == ["choose"]          # the invitation cannot be cancelled
    choice = obs["choice"]
    assert not choice["cancellable"] and [o["id"] for o in choice["options"]][-1] == "cash"
    assert obs["shop"]["offers"] == []                 # nothing is sold before the answer
    core = choice["options"][0]["id"]
    assert a.execute({"cmd": "choose", "option": core})["ok"]
    assert a.controller.table.loadout.core == core
    assert len(a.controller.shop.offers) == (4 if core == "ph_account" else 3)
    assert a.observe()["table"]["public"]["core"]["id"] == core


def test_declining_the_core_pays_its_chips_and_blocks_amendments_for_the_run():
    s = AgentSession.new(mode="chaos", seed=7)
    assert s.execute({"cmd": "choose", "option": "cash"})["ok"]
    c = s.controller
    assert c.run.money == 480 and c.table.loadout.no_core and c.table.loadout.core is None   # 30 written for 150
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
    assert c.run.money == 65 and c.table.loadout.equipped == ["ph_long_reward", "ph_sleeve"]
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
    assert c.hand_value(c.state.player_hand) == 20        # J/Q/K stay 10 while that does not bust
    assert c.hand_value(c.state.dealer_hand, "dealer") == 20
    c.hit()
    assert c.view().player_total == 20                     # K Q J: one drops to 5 ... 30 -> 25 -> 20
    c.hit()
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 22   # margin: bust above 22
    finish(c)
    assert c.last_result.outcome == "player"


def test_risk_pointer_uses_the_same_player_values():
    c = controller()
    item(c, "ph_radar")
    deal(c, player=("10", "6"), deck=("6",))
    assert c.use_item("ph_radar").message.startswith("Safe")  # 22 is not a bust with Room to Breathe


def test_multi_card_rewards_combine_once():
    c = controller()
    equip(c, "ph_long_reward", "ph_five_reward")
    deal(c, player=("2", "3"), deck=("4", "5", "6"), dealer=("10", "8"))
    for _ in range(3):
        c.hit()
    finish(c)
    assert c.last_result.delta == 35   # 10 + 50% (four cards) + 200% (five cards)


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


def test_quad_needs_only_a_plain_double_and_a_bigger_loss_becomes_debt():
    c = controller()
    item(c, "ph_quad")
    deal(c, player=("5", "6"), dealer=("10", "9"), deck=("2", "10"), bet=50)
    assert c.use_item("ph_quad").ok
    assert Action.DOUBLE in c.view().available_actions
    c.double_down()
    c.finish_dealer()
    assert c.last_result.bet == 200 and c.last_result.delta == -200
    assert c.run.money == 0 and c.table.ledger.debt == 100 and c.table.net_assets() == -100
    assert c.run_end.kind == "defeat"


def test_quad_prepared_before_the_bet_keeps_the_double():
    c = controller()
    item(c, "ph_quad")
    assert c.use_item("ph_quad").ok
    deal(c, player=("5", "6"), dealer=("10", "7"), deck=("10", "2"), bet=50)
    assert Action.DOUBLE in c.view().available_actions
    c.double_down()
    c.finish_dealer()
    assert c.last_result.delta == 200 and c.run.money == 300 and c.table.ledger.debt == 0


def test_shortfall_debt_survives_a_save():
    c = controller()
    c.table.ledger.shortfall = 40
    data = c.table.to_dict()
    c.table.restore(data)
    assert c.table.ledger.debt == 40


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
    assert expected == deal_order[:2]                      # your two opening cards
    assert not any(x in text for x in deal_order[4:12])   # nothing beyond the forecast leaks
    assert not resumed.controller.can_use_item("ph_oracle")
    resumed.controller.buy(resumed.controller.shop.offers[0].item)   # shopping does not move the deal
    resumed.controller.reroll_shop()
    resumed.controller.place_bet(5)
    assert [f"{x.rank}{x.suit}" for x in resumed.controller.state.player_hand] == expected


def test_card_effects_mark_the_forecast_out_of_date():
    c = controller()
    item(c, "ph_oracle")
    item(c, "ph_aces")
    c.use_item("ph_oracle")
    deal(c, deck=("3", "A", "7"))
    assert c.use_item("ph_aces").ok
    assert c.view().table_public.forecast_changed


def test_aces_moves_one_ace_and_cannot_be_used_before_bet():
    c = controller()
    item(c, "ph_aces")
    assert not c.can_use_item("ph_aces")
    deal(c, deck=("3", "A", "7", "A", "2"))
    assert c.use_item("ph_aces").ok
    assert [x.rank for x in c.state.deck] == ["A", "3", "7", "A", "2"]
    item(c, "ph_aces")
    assert c.item_usability("ph_aces").reason == "The next card is already an ace."


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
    assert c.run.money == 170 and c.table.net_assets() == 80 and c.table.ledger.debt == 120
    assert not c.table.stockable("ph_loan")
    public = c.view().table_public
    assert (public.cash, public.invested, public.debt, public.net_assets) == (170, 30, 120, 80)


def test_borrowed_cash_never_wins_and_victory_settles_at_cost():
    c = controller("ph_account")
    c.run.money = 480
    offer(c, "ph_loan")
    c.buy("ph_loan")
    assert c.run.money == 580 and c.run_end is None           # net assets 460
    offer(c, "ph_deposit")
    c.buy("ph_deposit")
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=40)
    finish(c)
    assert c.run_end.kind == "victory"
    assert c.run.money == 500 and not c.table.ledger.positions  # 590 cash + 30 principal − 120 owed


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
    assert c.run.money == 130 and not c.table.ledger.positions   # 70 + 30 back + 20 profit x 1.5


def test_stock_pays_100_or_nothing_from_a_private_draw():
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
    assert outcomes == {0, 100}


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


# --- chip amounts scale with the starting cash (money.py) ---------------------------------------


def test_chip_amounts_are_a_share_of_the_starting_cash():
    c = controller(start_money=400)  # the shipped profile writes them for 100
    t = c.table
    assert t.config.shop_prices["ph_jackpot"] == 4 * c.config.shop_prices["ph_jackpot"]
    assert t.config.shop_prices["ph_radar"] == 24
    assert [t.min_bet(r) for r in (1, 4, 16, 19)] == [20, 40, 160, 200]
    assert t.config.item_params["ph_loan"] == {**c.config.item_params["ph_loan"], "advance": 400, "repay": 480}
    assert t.config.item_params["ph_stock"]["probability"] == 0.5  # not a chip amount
    assert t.setting("decline_cash") == 120 and t.reroll_price(0) == 12
    assert c.bet_limits() == (20, 200)


def test_agent_start_money_overrides_the_mode_and_scales_the_shop():
    s = AgentSession.new(seed=101, mode="chaos", start_money=400, target_money=2000)
    obs = s.observe()
    assert obs["bankroll"] == 400 and obs["target"] == 2000 and obs["bet_range"] == [13, 200]   # written for 150


def test_scaled_amounts_round_half_up_and_stay_at_least_one_chip():
    from chaos_blackjack.poker_head.money import chips
    from fractions import Fraction
    assert chips(3, Fraction(3, 2)) == 5 and chips(5, Fraction(1, 2)) == 3 and chips(1, Fraction(1, 10)) == 1
    assert chips(0, Fraction(4)) == 0


def test_the_shipped_profile_is_written_for_its_own_start():
    c = controller()
    assert c.table.config is c.config


def test_withdrawal_limit_caps_scale_and_keep_their_pressure():
    from fractions import Fraction
    from chaos_blackjack.poker_head.director import Director
    d = Director({}, seed=1, money=Fraction(4))
    caps = d.variants(d.stage(13))["profit_cap"]
    assert sorted(r.profit_cap for r in caps) == [120, 160]
    assert sorted(d.pressure(r) for r in caps) == [3, 4]


# --- Full Haul: leave from 4x, the table stops at 6x (docs/design/CARRIED_CHIPS.zh-CN.md §4) ------


def haul_table(**overrides):
    return controller(target_multiple=6, exit_multiple=4, **overrides)


def test_full_haul_is_offered_from_the_exit_multiple_and_ends_the_run_as_a_win():
    c = haul_table()
    assert c.run.target_money == 600 and c.config.exit_money == 400
    c.run.money = 399
    assert "ph_full_haul" not in [m.action for m in c.view().moves]
    c.run.money = 400
    assert "ph_full_haul" in [m.action for m in c.view().moves]
    c.perform("ph_full_haul")
    assert c.choice is not None and c.choice.kind == "full_haul"
    c.choose("ph_full_haul")
    assert c.phase == TablePhase.RUN_OVER and c.run_end.kind == "victory"
    assert c.run.money == 400 and "Full Haul" in c.run_end.message


def test_full_haul_can_be_cancelled_and_counts_open_investments():
    c = haul_table()
    c.run.money = 370
    c.table.ledger.open("ph_deposit", 30, 0, 2)
    assert "ph_full_haul" in [m.action for m in c.view().moves]
    c.perform("ph_full_haul")
    c.cancel_choice()
    assert c.phase == TablePhase.BETTING and not c.table.leaving


def test_the_ceiling_cuts_a_win_and_ends_the_run():
    c = haul_table()
    c.run.money = 550
    deal(c, player=("5", "6"), dealer=("10", "7"), deck=("10", "2"), bet=50)
    c.double_down()
    c.finish_dealer()
    assert c.run.money == 600 and c.last_result.delta == 50
    assert c.run_end.kind == "victory" and "stops playing" in c.run_end.message


def test_the_ceiling_counts_the_net_gain_of_a_round():
    c = haul_table()
    c.run.money = 565
    c.table.ledger.open("ph_deposit", 30, 0, 1)  # net 595; matures this round: 50 back, 20 profit
    deal(c, player=("10", "6"), dealer=("10", "9"), deck=("2",), bet=20)
    c.stand()
    c.finish_dealer()
    # The hand lost 20, so the round's net gain is 0: the deposit's 20 profit fits under the 5 chips of room.
    assert c.run.money == 595 and c.table.net_assets() == 595
    assert not any("ceiling" in n.text for n in c.drain_notices())


def test_agent_target_money_replaces_a_multiple():
    s = AgentSession.new(seed=1, mode="chaos", target_money=1000)
    assert s.observe()["target"] == 1000


def test_yield_privilege_needs_money_products():
    c = controller("ph_margin")
    assert not c.table.stockable("ph_yield")
    offer(c, "ph_yield")
    assert c.offer_usability(c.shop.offer("ph_yield")).reason == "Needs the Private Account core."
    rolled = {o.item for _ in range(40) for o in c.table.roll_shop(reroll=True).offers}
    assert "ph_yield" not in rolled
    c.table.loadout.core = "ph_account"
    assert c.table.stockable("ph_yield")


# --- cores change what you can do (2026-10-14) ------------------------------------------------


def test_fresh_hand_swaps_both_opening_cards_once_per_round_before_acting():
    c = controller("ph_redeal")
    deal(c, player=("10", "6"), dealer=("10", "7"), deck=("A", "K", "5", "4"))
    assert "ph_redeal" in [m.action for m in c.view().moves if m.enabled]
    c.perform("ph_redeal")
    assert [x.rank for x in c.state.player_hand] == ["A", "K"] and [x.rank for x in c.state.deck][:2] == ["5", "4"]
    assert c.phase == TablePhase.PLAYER_TURN  # a new 21 is not a natural: you still play the hand
    move = c.view().move("ph_redeal")
    assert move is not None and not move.enabled and move.reason == "Used this round."


def test_fresh_hand_is_only_before_your_first_action():
    c = controller("ph_redeal")
    deal(c, player=("5", "6"), dealer=("10", "7"), deck=("2", "K", "5"))
    c.hit()
    assert c.view().move("ph_redeal").reason == "Only before your first action."


def test_exit_clause_and_raise_permission_are_cores():
    c = controller("ph_late_retreat")
    deal(c, player=("5", "6"), dealer=("10", "7"), deck=("2", "K"))
    c.hit()
    assert Action.SURRENDER in c.view().available_actions
    c = controller("ph_late_double")
    deal(c, player=("2", "3"), dealer=("10", "7"), deck=("4", "K"))
    c.hit()
    assert Action.DOUBLE in c.view().available_actions


def test_room_to_breathe_raises_the_bust_limit_by_two():
    c = controller("ph_margin")
    deal(c, player=("10", "6"), dealer=("10", "7"), deck=("7",))
    c.hit()
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 23


def test_the_former_cores_are_sold_as_permanents():
    assert {"ph_retreat", "ph_approx", "ph_stakes"} <= set(SHOP_IDS) - set(CORES)
    assert {"ph_late_retreat", "ph_late_double", "ph_redeal"} <= set(CORES)


def test_a_save_from_before_the_core_swap_loads_with_its_style_s_new_core():
    c = controller("ph_margin")
    data = c.table.to_dict()
    data["loadout"] = {"core": "ph_approx", "no_core": False, "equipped": ["ph_late_double", "ph_jackpot"]}
    c.table.restore(data)
    assert c.table.loadout.core == "ph_redeal" and c.table.loadout.equipped == ["ph_jackpot"]


def test_cores_can_cost_or_bring_chips_when_chosen():
    c = GameController(config(), save_fn=lambda d, n: n)  # the real invitation
    c.choice = None
    gift = c.table.holdings.add("ph_gift", 0, ("ph_margin", "ph_late_retreat"))
    c.table._ask_opening(gift)
    labels = {o.id: o.label for o in c.choice.options}
    assert labels["ph_margin"] == "Room to Breathe (costs 60 chips)"
    assert labels["ph_late_retreat"] == "Exit Clause (+60 chips)"
    c.choose("ph_margin")
    assert c.table.loadout.core == "ph_margin" and c.run.money == 40


def test_core_chips_scale_with_the_starting_cash():
    c = controller(start_money=400)
    assert c.table.core_cash("ph_margin") == -240 and c.table.core_cash("ph_late_retreat") == 240
    assert c.table.core_cash("ph_redeal") == 0


def test_a_core_fee_must_leave_a_bet():
    c = controller("ph_redeal")
    c.run.money = 45
    with pytest.raises(ActionError):
        c.table.choose_core("ph_margin")
    assert c.table.loadout.core == "ph_redeal" and c.run.money == 45


def test_bust_insurance_lets_the_dealer_play_and_a_dealer_bust_is_a_push():
    c = controller("ph_redeal")
    item(c, "ph_insurance")
    deal(c, player=("10", "6"), dealer=("10", "6"), deck=("K", "Q"), bet=20)
    assert c.use_item("ph_insurance").ok
    c.hit()                                                 # 26: bust, but the dealer still plays
    assert c.phase == TablePhase.DEALER_TURN
    c.finish_dealer()                                       # dealer 16 + Q = 26: also bust
    assert c.last_result.outcome == "push" and c.run.money == 100


def test_bust_insurance_still_loses_when_the_dealer_stands():
    c = controller("ph_redeal")
    item(c, "ph_insurance")
    deal(c, player=("10", "6"), dealer=("10", "7"), deck=("K", "Q"), bet=20)
    c.use_item("ph_insurance")
    c.hit()
    c.finish_dealer()
    assert c.last_result.outcome == "dealer" and c.run.money == 80


def test_without_insurance_a_bust_settles_at_once():
    c = controller("ph_redeal")
    deal(c, player=("10", "6"), dealer=("10", "6"), deck=("K", "Q"), bet=20)
    c.hit()
    assert c.last_result.outcome == "dealer" and c.phase != TablePhase.DEALER_TURN


def test_court_discount_switches_face_cards_like_aces():
    c = controller("ph_redeal")
    equip(c, "ph_court")
    deal(c, player=("K", "5"), dealer=("10", "7"), deck=("Q", "9"))
    assert c.view().player_total == 15
    c.hit()                                                 # K 5 Q: 25 would bust, a face card drops: 20
    assert c.view().player_total == 20 and c.phase == TablePhase.PLAYER_TURN


def test_fate_forecast_shows_your_opening_cards_with_comeback_ace():
    c = controller()
    c.table.ace_pending = True
    item(c, "ph_oracle")
    assert c.use_item("ph_oracle").ok
    first, second = c.table.prepare_deck()[:2]
    assert c.table.round.forecast == [f"A{first.suit}", f"{second.rank}{second.suit}"]


def test_paid_reroll_grows_with_the_minimum_bet_steps():
    c = controller()
    c.config.mode_settings["chaos.reroll_step_add"] = 2
    assert c.reroll_price() == 3
    c.run.round = 4
    assert c.reroll_price() == 5
    c.run.round = 10
    assert c.reroll_price() == 9


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
    assert loan.sold and c.table.ledger.debt == 120
    c.table.set_core("ph_account")
    assert len(c.shop.offers) == len(SHOP_IDS)                 # a core change never trims the shelf


def test_icon_groups_follow_the_catalog():
    groups = {p.id: p.to_def().group for p in PRODUCTS.values()}
    assert groups["ph_court"] == "permanent" and groups["ph_peek"] == "consumable"
    assert {groups[x] for x in ("ph_margin", "ph_deposit", "ph_loan", "ph_gift", "ph_change")} == {"special"}


# --- two build slots and discarding ------------------------------------------------------------


def test_the_shipped_build_has_three_slots():
    s = AgentSession.new(mode="chaos", seed=7)
    assert s.controller.view().table_public.slots == 3


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
    assert "ph_claim" in {x for s in range(200) for x in _stock(c, s)}


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
    assert c.view().money == 200 and c.view().goal == ("Net assets", 80, 500)
    plain = AgentSession.new(seed=7).controller
    assert plain.view().goal is None
