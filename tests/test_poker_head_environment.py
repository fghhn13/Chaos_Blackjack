"""Poker Head's environment rules, stage A: the rule model and hand values.

docs/design/POKER_HEAD_CHAOS_RULES_AND_AGENT.zh-CN.md §2–§4.
"""

from dataclasses import replace

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.modes import get_mode
from chaos_blackjack.poker_head import environment as env
from chaos_blackjack.poker_head.environment import CardGroup, EnvRule, ranks
from chaos_blackjack.poker_head.ownership import Holdings


def card(rank, suit="♠"):
    return Card(Rank(rank), suit)


def controller(core="ph_margin", rules=(), equipped=()):
    cfg = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=7, use_llm=False))
    cfg = replace(cfg, enable_chaos=False, mode_settings={**cfg.mode_settings, "chaos.unlock_all": 0,
                                                          "chaos.director.stages": "[[1, 0, 3, 99]]"})
    c = GameController(cfg, save_fn=lambda d, n: n)
    c.choice = None
    c.table.loadout.core = core
    c.table.loadout.equipped = list(equipped)
    c.table.holdings = Holdings()
    c.table._sync_items()
    c.table.environment = list(rules)
    c.shop = c.table.roll_shop()
    return c


def deal(c, player, dealer=("10", "7"), deck=("2", "3", "4"), bet=10, suits=None):
    s = suits or {}
    c.table.prepared = tuple(card(x, s.get(i, "♠")) for i, x in enumerate((*player, *dealer, *deck)))
    c.table.prepared_round = c.run.round
    c.place_bet(bet)


def finish(c):
    c.stand()
    c.finish_dealer()


# --- the rule model ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule, words", [
    (env.fixed(ranks("7"), 10), ["7s", "10"]),
    (env.fixed(ranks("J", "Q", "K"), 8), ["J, Q and K", "8"]),
    (env.shift((CardGroup("even"), 2), (CardGroup("odd"), -1)), ["even number cards", "+2", "odd number cards", "−1"]),
    (env.shift((CardGroup("red"), 1), (CardGroup("black"), -1), actor="dealer"), ["dealer", "red cards", "black cards"]),
    (env.bust("player", 20), ["Your", "20"]),
    (env.bust("dealer", 23), ["dealer", "23"]),
    (env.tie("dealer"), ["dealer wins"]),
    (env.bust_outcome("dealer", "push"), ["dealer busts", "push"]),
    (env.profit_cap(40), ["40"]),
    (env.item_ban(3), ["consumable"]),
    (env.markup(20), ["20%"]),
    (env.hidden(2), ["face down"]),
])
def test_every_rule_reads_with_its_actual_numbers_and_targets(rule, words):
    text = rule.text()
    assert all(w in text for w in words), text
    assert "{" not in text and "actor" not in text and "params" not in text
    assert rule.title and rule.removal_text() in text and rule.duration_text() in text


def test_duration_age_and_signature():
    rule = env.bust("player", 20, rounds=2)
    assert rule.remaining == 2 and "2 rounds left" in rule.text()
    older = rule.aged()
    assert older.remaining == 1 and not older.expired and older.aged().expired
    assert older.signature == rule.signature                       # age is not part of the effect
    assert env.bust("player", 19).signature != rule.signature
    persistent = env.fixed(ranks("7"), 10)
    assert persistent.remaining is None and not persistent.aged().expired
    assert "until removed or replaced" in persistent.text()


@pytest.mark.parametrize("make", [
    lambda: env.fixed(ranks("7"), 7),                     # must change the value
    lambda: env.fixed(ranks("7"), 11),                    # 1–10
    lambda: env.shift((CardGroup("red"), 1), (CardGroup("suit", suit="♥"), -1)),  # overlapping groups
    lambda: env.shift((CardGroup("all"), 0)),
    lambda: env.bust("both", 20),                         # one actor
    lambda: EnvRule("markup", {"pct": 10}),               # timed rules need a duration
    lambda: EnvRule("chaos", {}),
])
def test_invalid_rules_are_refused(make):
    with pytest.raises((ValueError, KeyError)):
        make()


def test_one_rule_per_type_and_fixed_and_shift_coexist():
    rules = [env.fixed(ranks("7"), 10)]
    assert env.conflict(rules, env.fixed(ranks("8"), 5))
    assert not env.conflict(rules, env.shift((CardGroup("all"), 1)))
    assert not env.conflict(rules, env.tie())


def test_rules_round_trip_through_dicts():
    for rule in (env.fixed(ranks("10", "J", "Q", "K"), 6, actor="dealer"),
                 env.shift((CardGroup("suit", suit="♦"), -1)).aged(), env.markup(30), env.hidden(3)):
        assert EnvRule.from_dict(rule.to_dict()) == rule


# --- card values ----------------------------------------------------------------------------------


def test_odd_and_even_use_the_printed_rank_and_ten_is_even():
    rules = [env.fixed(ranks("7"), 8), env.shift((CardGroup("even"), 2), (CardGroup("odd"), -1))]
    assert env.card_values(card("7"), "player", rules) == (7, 7)     # fixed 8 first, then odd −1 (printed 7 is odd)
    assert env.card_values(card("10"), "player", rules) == (12, 12)
    assert env.card_values(card("3"), "player", rules) == (2, 2)


def test_fixed_rewrite_comes_before_shifts_and_cards_never_drop_below_one():
    rules = [env.fixed(ranks("7"), 2), env.shift((CardGroup("all"), -2))]
    assert env.card_values(card("7"), "both", rules) == (1, 1)
    assert env.card_values(card("2"), "player", rules) == (1, 1)


def test_aces_shift_both_values_unless_pinned():
    assert env.card_values(card("A"), "player", [env.shift((CardGroup("all"), 1))]) == (12, 2)
    assert env.card_values(card("A"), "player", [env.shift((CardGroup("all"), -1))]) == (10, 1)
    assert env.card_values(card("A"), "player", [env.fixed(ranks("A"), 5)]) == (5, 5)


def test_actor_scope():
    rule = env.fixed(ranks("K"), 6, actor="dealer")
    assert env.card_values(card("K"), "dealer", [rule]) == (6, 6)
    assert env.card_values(card("K"), "player", [rule]) == (10, 10)


# --- hands at the table ------------------------------------------------------------------------------


def test_a_rewrite_changes_both_hands():
    c = controller(rules=[env.fixed(ranks("7"), 10)])
    deal(c, player=("7", "7"), dealer=("7", "9"))
    assert c.view().player_total == 20
    finish(c)
    assert c.last_result.dealer_total == 19 and c.last_result.outcome == "player"


def test_the_player_build_applies_after_the_environment():
    c = controller(rules=[env.fixed(ranks("J", "Q", "K"), 8)], equipped=["ph_court"])
    deal(c, player=("K", "Q"), dealer=("K", "Q"))
    assert c.hand_value(c.state.player_hand) == 10 and c.hand_value(c.state.dealer_hand, "dealer") == 16


def test_ace_switch_with_a_shift():
    c = controller("ph_retreat", rules=[env.shift((CardGroup("all"), 1))])
    deal(c, player=("A", "9"), dealer=("10", "7"))
    assert c.view().player_total == 12            # 12 + 10 = 22 busts, so the ace drops to 2


def test_core_and_items_add_to_a_lower_base_limit():
    c = controller("ph_margin", rules=[env.bust("player", 19)])
    deal(c, player=("10", "10"), deck=("2",))
    assert c.phase == TablePhase.PLAYER_TURN      # 20: the limit is 19 + 1 (Room to Breathe)
    c.hit()
    assert c.last_result.player_bust and c.last_result.player_total == 22


def test_buffer_and_margin_stack_on_a_base_of_19():
    c = controller("ph_margin", rules=[env.bust("player", 19)])
    c.table.round.preparations.append("ph_buffer")
    deal(c, player=("10", "10"), deck=("2",))
    c.hit()
    assert c.phase == TablePhase.PLAYER_TURN and c.view().player_total == 22   # limit 19 + 1 + 2 = 22


def test_almost_perfect_recognises_first_then_checks_the_limit():
    c = controller("ph_approx", rules=[env.bust("player", 20)])
    deal(c, player=("10", "10"))
    assert c.last_result.player_bust and c.last_result.player_total == 21     # 20 counts as 21, above 20


def test_a_dealer_limit_above_21_lets_22_compare():
    c = controller(rules=[env.bust("dealer", 23)])
    deal(c, player=("10", "10"), dealer=("10", "6"), deck=("6",))
    finish(c)
    assert c.last_result.dealer_total == 22 and c.last_result.outcome == "dealer"


def test_ties_to_the_house_are_ordinary_losses():
    c = controller("ph_stakes", rules=[env.tie("dealer")], equipped=["ph_risk"])
    deal(c, player=("10", "8"), dealer=("10", "8"), deck=("K",), bet=20)
    finish(c)
    assert c.last_result.outcome == "dealer" and c.last_result.delta == -20
    d = controller("ph_stakes", rules=[env.tie("dealer")], equipped=["ph_risk"])
    deal(d, player=("5", "4"), dealer=("10", "9"), deck=("10",), bet=20)
    d.double_down()
    d.finish_dealer()
    assert d.last_result.outcome == "dealer" and d.last_result.delta == -30   # Shared Risk still applies


def test_dealer_bust_pardon_only_pardons_the_dealer():
    c = controller(rules=[env.bust_outcome("dealer", "push")])
    deal(c, player=("10", "8"), dealer=("10", "6"), deck=("K",))
    finish(c)
    assert c.last_result.outcome == "push" and c.last_result.delta == 0
    p = controller(rules=[env.bust_outcome("dealer", "push")])
    deal(p, player=("10", "8"), deck=("K",))
    p.hit()
    assert p.last_result.outcome == "dealer" and p.last_result.player_bust


def test_naturals_ignore_value_rules():
    c = controller(rules=[env.fixed(ranks("K"), 6), env.shift((CardGroup("all"), -1))])
    deal(c, player=("A", "K"), dealer=("10", "7"))
    assert c.last_result.outcome == "blackjack" and c.last_result.delta == 15


def test_silence_seal_suppresses_the_environment_for_the_round():
    c = controller(rules=[env.fixed(ranks("7"), 10)])
    c.table.round.preparations.append("ph_silence")
    deal(c, player=("7", "7"))
    assert c.view().player_total == 14
    finish(c)
    assert c.table.environment and c.table.env_rules()                # back next round


def test_the_environment_is_saved_with_the_run():
    c = controller(rules=[env.fixed(ranks("7"), 10), env.markup(20).aged()])
    loaded = GameController.from_save(RunSaveData.from_dict(c.save("x").to_dict()), save_fn=lambda d, n: n)
    assert loaded.table.environment == c.table.environment


# === stage B: money, items, shop and display rules ==============================================

from chaos_blackjack.agent import AgentSession  # noqa: E402
from chaos_blackjack.app.chaos_context import build_chaos_context  # noqa: E402
from chaos_blackjack.app.shop import ShopOffer, ShopState  # noqa: E402


def item(c, name, paid=0):
    h = c.table.holdings.add(name, paid)
    c.table._sync_items()
    return h


def offer(c, *items):
    c.shop = ShopState(c.run.round, tuple(ShopOffer(i, c.config.shop_prices[i]) for i in items))


# --- Withdrawal Limit (§3.6) -------------------------------------------------------------------------


def test_profit_above_the_cap_is_lost():
    c = controller("ph_retreat", rules=[env.profit_cap(40)])
    c.run.money = 200
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=60)
    finish(c)
    assert c.last_result.delta == 40 and c.run.money == 240


def test_the_cap_counts_hand_and_investment_profit_once_and_cuts_the_hand_first():
    c = controller("ph_account", rules=[env.profit_cap(40)])
    c.table.ledger.open("ph_deposit", 30, 0, 1)          # pays 40 now: 30 back + 10 profit
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=40)
    finish(c)
    assert c.last_result.delta == 30                      # 40 + 10 = 50 profit, 10 over the cap
    assert c.run.money == 100 + 30 + 40                   # the principal comes back in full


def test_losses_are_not_capped_and_do_not_raise_the_cap():
    c = controller("ph_account", rules=[env.profit_cap(5)])
    c.table.ledger.open("ph_deposit", 30, 0, 1)
    deal(c, player=("10", "6"), dealer=("10", "8"), bet=20)
    finish(c)
    assert c.last_result.delta == -20 and c.run.money == 100 - 20 + 30 + 5


def test_refunds_and_loan_repayments_are_not_profit():
    c = controller("ph_retreat", rules=[env.profit_cap(0)], equipped=["ph_claim"])
    c.table.claim = {"round": 1, "refund": 20}
    c.table.ledger.open("ph_loan", 0, 50, 1)
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=10)
    finish(c)
    assert c.last_result.delta == 20                      # the win's 10 is capped away, the refund stays
    assert c.run.money == 100 + 20 - 50


def test_silence_lifts_the_cap_for_the_round():
    c = controller("ph_retreat", rules=[env.profit_cap(0)])
    c.table.round.preparations.append("ph_silence")
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=10)
    finish(c)
    assert c.last_result.delta == 10


def test_victory_is_checked_after_the_cap():
    c = controller("ph_retreat", rules=[env.profit_cap(10)])
    c.run.money = 480
    deal(c, player=("10", "9"), dealer=("10", "7"), bet=40)
    finish(c)
    assert c.run.money == 490 and c.run_end is None


# --- Item Ban (§3.7) ---------------------------------------------------------------------------------


def test_a_banned_item_is_usable_in_its_phase_and_only_lifts_the_ban():
    c = controller(rules=[env.item_ban(2)])
    item(c, "ph_remove")                                   # nothing to remove: normally unusable
    item(c, "ph_peek")
    items = {i.id: i for i in c.view().items}
    assert items["ph_remove"].usable and "lifts the ban" in items["ph_remove"].note
    assert not items["ph_peek"].usable                     # the phase still applies
    result = c.use_item("ph_remove")
    assert result.ok and c.choice is None and "ph_remove" not in c.run.items
    assert not c.table.environment and c.table.env_history[-1]["cause"] == "sacrificed"
    assert not c.view().items[0].note


def test_a_sacrificed_item_has_no_effect():
    c = controller(rules=[env.item_ban(2), env.fixed(ranks("7"), 10)])
    item(c, "ph_silence")
    c.use_item("ph_silence")
    assert "ph_silence" not in c.table.round.preparations and c.table.env_rules()  # nothing silenced
    w = controller("ph_retreat", rules=[env.item_ban(2)])
    item(w, "ph_waiver")
    deal(w, player=("10", "6"))
    assert w.use_item("ph_waiver").ok and w.phase == TablePhase.PLAYER_TURN          # no surrender


def test_permanents_still_act_under_a_ban():
    c = controller(rules=[env.item_ban(2)], equipped=["ph_sleeve"])
    deal(c, player=("10", "6"), deck=("2", "3"))
    c.perform("ph_sleeve")
    assert c.state.player_hand[0].rank == "2" and c.table.environment


def test_the_agent_sees_the_ban_note():
    c = controller(rules=[env.item_ban(2)])
    item(c, "ph_oracle")
    obs = AgentSession(c, seed=7).observe()
    assert obs["items"][0]["usable"] and "lifts the ban" in obs["items"][0]["note"]


# --- Price Hike (§3.8) -----------------------------------------------------------------------------------


def test_markup_and_discount_round_up_once():
    c = controller(rules=[env.markup(20)], equipped=["ph_discount"])
    offer(c, "ph_swap", "ph_deposit")
    swap, deposit = c.view().shop_offers
    assert swap.price == 7 and swap.base_price == 6                 # 6 x 1.2 x 0.9 = 6.48 -> 7 (not 8)
    assert "+20% Price Hike" in swap.price_note and "−10% Purchasing Privilege" in swap.price_note
    assert deposit.price == 30 and deposit.base_price is None       # money products keep their price
    assert c.reroll_price() == 3


def test_the_actual_price_paid_is_remembered_and_silence_restores_prices():
    c = controller(rules=[env.markup(40)])
    offer(c, "ph_aces", "ph_swap")
    c.buy("ph_aces")
    assert c.run.money == 100 - 26 and c.table.holdings.first("ph_aces").paid == 26   # 18 x 1.4 = 25.2 -> 26
    c.table.round.preparations.append("ph_silence")
    assert c.view().shop_offers[1].price == 6 and c.view().shop_offers[1].base_price is None
    obs = AgentSession(c, seed=7).observe()
    assert "base_price" not in obs["shop"]["offers"][1]


# --- Face-Down Card (§3.9) ----------------------------------------------------------------------------------


def _hidden_controller(**kw):
    c = controller(rules=[env.hidden(2)], **kw)
    deal(c, player=("10", "9"), dealer=("8", "7"), deck=("2", "3", "4"), suits={1: "♦"})
    return c


def test_the_second_opening_card_and_the_total_stay_hidden_on_your_turn():
    c = _hidden_controller()
    v = c.view()
    assert [x.face_up for x in v.player_cards] == [True, False] and v.player_total is None
    obs = AgentSession(c, seed=7).observe()
    assert obs["you"] == {"cards": ["10♠", "??"], "total": None} and "= ?." in obs["summary"]
    assert "9♦" not in str(obs) and "9♦" not in build_chaos_context(c)
    assert "9♦" not in str(c.run_log.to_dict())
    c.hit()                                                # extra cards are face up, the second stays down
    v = c.view()
    assert [x.face_up for x in v.player_cards] == [True, False, True] and v.player_total is None


def test_standing_reveals_the_hand():
    c = _hidden_controller()
    c.stand()
    assert all(x.face_up for x in c.view().player_cards) and c.view().player_total == 19


def test_a_natural_is_judged_on_the_real_cards_and_shown_at_once():
    c = controller(rules=[env.hidden(2)])
    deal(c, player=("A", "K"))
    assert c.last_result.outcome == "blackjack" and all(x.face_up for x in c.view().player_cards)


def test_silence_or_removal_shows_the_card_at_once():
    c = _hidden_controller()
    c.table.lift_rule(c.table.environment[0], "removed")
    assert c.view().player_total == 19
    s = controller(rules=[env.hidden(2)])
    s.table.round.preparations.append("ph_silence")
    deal(s, player=("10", "9"))
    assert s.view().player_total == 19


def test_a_swap_keeps_the_second_card_down_and_risk_pointer_still_answers():
    c = controller(rules=[env.hidden(2)])
    item(c, "ph_swap")
    item(c, "ph_radar")
    deal(c, player=("10", "9"), deck=("5", "K"))
    c.use_item("ph_swap")
    assert [x.face_up for x in c.view().player_cards] == [True, False] and c.view().player_total is None
    assert "BUST" in c.use_item("ph_radar").message                     # 5 + 9 + K = 24
