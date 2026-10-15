"""Poker Head's offline director (docs/design/POKER_HEAD_CHAOS_RULES_AND_AGENT.zh-CN.md §6–7)."""

import json
from dataclasses import replace

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.meta.tracker import RunTracker
from chaos_blackjack.modes import get_mode
from chaos_blackjack.poker_head import environment as env
from chaos_blackjack.poker_head.director import DEFAULTS, HIGH_PRESSURE, Director, from_legacy
from chaos_blackjack.poker_head.environment import CardGroup, ranks

ALWAYS = json.dumps([[1, 1, 1, 2], [4, 1, 2, 4], [7, 1, 3, 7], [10, 1, 3, 8]])


def director(**settings):
    return Director({**{f"director.{k}": v for k, v in settings.items()}}, seed=7)


def history(type_, cause, round_no, signature=""):
    return {"type": type_, "signature": signature, "cause": cause, "round": round_no}


def controller(seed=7, stages=ALWAYS, chaos=True):
    cfg = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=seed, use_llm=False))
    cfg = replace(cfg, enable_chaos=chaos, mode_settings={**cfg.mode_settings, "chaos.director.stages": stages})
    return GameController(cfg, save_fn=lambda d, n: n)


def play_round(c):
    """Bet the minimum and stand; returns after the round settled and the next one began."""
    c.place_bet(c.bet_limits()[0])
    if c.phase == TablePhase.PLAYER_TURN:
        c.stand()
    c.finish_dealer()
    if c.phase == TablePhase.ROUND_OVER:
        c.next_round()


# --- settings, stages and pressure ------------------------------------------------------------------


def test_the_shipped_profile_holds_the_design_numbers():
    settings = {k[len("chaos."):]: v for k, v in default_balance().mode_settings if k.startswith("chaos.director.")}
    d = Director(settings, seed=1)
    assert d.stages == DEFAULTS["stages"] and d.weights == DEFAULTS["weights"]
    assert d.pools == DEFAULTS["pools"] and d.pressures == DEFAULTS["pressure"]


@pytest.mark.parametrize("round_no, index, act, slots, budget", [
    (1, 0, 0.4, 1, 1), (4, 0, 0.4, 1, 1), (5, 1, 0.6, 2, 3), (9, 2, 0.75, 2, 5), (13, 3, 0.85, 2, 6), (40, 3, 0.85, 2, 6)])
def test_stages_grow_with_the_round(round_no, index, act, slots, budget):
    s = director().stage(round_no)
    assert (s.index, s.act, s.slots, s.budget) == (index, act, slots, budget)


@pytest.mark.parametrize("rule, pressure", [
    (env.fixed(ranks("7"), 9), 1), (env.shift((ranks("7"), 1)), 1), (env.shift((CardGroup("red"), 2)), 2),
    (env.shift((CardGroup("even"), 1), (CardGroup("odd"), -1)), 2), (env.shift((CardGroup("all"), 1)), 2),
    (env.bust("player", 20), 2), (env.bust("player", 19), 3), (env.bust("dealer", 22), 3), (env.bust("dealer", 23), 3),
    (env.tie("dealer"), 2), (env.bust_outcome("dealer", "push"), 3), (env.profit_cap(50), 2), (env.profit_cap(30), 4),
    (env.item_ban(2), 2), (env.item_ban(3), 3), (env.markup(10), 1), (env.markup(30), 2), (env.hidden(2), 2)])
def test_pressure_follows_the_design_table(rule, pressure):
    assert director().pressure(rule) == pressure


def test_the_first_stage_pool_is_mild():
    d = director()
    pool = d.variants(d.stage(1))
    assert set(pool) == {"fixed", "shift", "markup"}
    for rule in pool["fixed"]:
        group = rule.group
        assert not group.has_ace and group.kind == "ranks"          # no fixed ace, no "all cards" rewrite
        if len(group.ranks) == 1:
            assert abs(rule.params["value"] - int(group.ranks[0])) <= 2
        else:
            assert rule.params["value"] in (8, 9)
    assert all(abs(d_) == 1 and g.kind == "ranks" and len(g.ranks) == 1 for r in pool["shift"] for g, d_ in r.shifts)
    assert [r.params["pct"] for r in pool["markup"]] == [10]
    assert {r.params["cap"] for r in d.variants(d.stage(13))["profit_cap"]} == {40, 30}


# --- decisions ------------------------------------------------------------------------------------------


def test_a_decision_depends_only_on_seed_round_rules_and_history():
    a, b = director(), director()
    rules = [env.markup(10)]
    first = a.decide(5, rules, [])
    for _ in range(3):
        a.decide(9, [], [])                                           # other rounds use other streams
    assert a.decide(5, rules, []) == first == b.decide(5, rules, [])


def test_stage_one_fills_one_slot_and_only_replaces_old_persistent_rules():
    d = director(stages=ALWAYS)
    added = d.decide(1, [], [])
    assert added.kind == "added"
    young = d.decide(2, [env.fixed(ranks("7"), 9, age=1)], [])
    assert young.kind == "calm"                                       # in force for less than two rounds
    old = d.decide(3, [env.fixed(ranks("7"), 9, age=2)], [])
    assert old.kind == "replaced" and old.replaced.type == "fixed"
    timed = d.decide(3, [env.markup(10, age=2)], [])
    assert timed.kind == "calm"                                       # a timed rule is never replaced


def test_same_type_replacements_never_weaken_and_never_repeat_the_effect():
    d = director(stages=ALWAYS)
    old = env.shift((CardGroup("all"), 1), age=5)                     # pressure 2
    for round_no in range(10, 30):
        action = d.decide(round_no, [old], [])
        if action.kind == "replaced" and action.rule.type == "shift":
            assert d.pressure(action.rule) >= 2 and action.rule.signature != old.signature


def test_budget_high_pressure_and_hidden_with_ban_limits():
    d = director(stages=ALWAYS)
    for round_no in range(10, 60):
        rules = [env.hidden(3), env.bust("player", 19, age=1)]          # pressure 2 + 3
        action = d.decide(round_no, rules, [])
        if action.kind == "added":
            new = action.rule
            assert new.type not in ("hidden", "bust", "item_ban")
            assert new.tier < 3                                          # one heavy rule at most
            assert 5 + d.pressure(new) <= 8


def test_cooldowns():
    d = director(stages=json.dumps([[1, 1, 3, 99]]), pools=json.dumps([{"markup": [[10, 3]]}]),
                 weights=json.dumps({"markup": [1]}))
    cleared = [history("markup", "sacrificed", 5)]
    assert [d.decide(r, [], cleared).kind for r in (6, 7, 8)] == ["calm", "calm", "added"]
    expired = [history("markup", "expired", 5)]
    assert [d.decide(r, [], expired).kind for r in (6, 7)] == ["calm", "added"]
    sig = env.markup(10).signature
    replaced = [history("markup", "replaced", 5, sig)]
    assert [d.decide(r, [], replaced).kind for r in (6, 7, 8)] == ["calm", "calm", "added"]


def test_legacy_rules_map_to_environment_rules():
    assert from_legacy({"id": "modify_card_value", "params": {"delta": -1}}) == env.shift((CardGroup("all"), -1))
    assert from_legacy({"id": "fragile_bust", "params": {"bust_limit": 19}}) == env.bust("player", 19, 2)
    assert from_legacy({"id": "tiebreaker_shift", "params": {"ties_to": "dealer"}}) == env.tie("dealer")
    assert from_legacy({"id": "j54_burn", "params": {}}) is None


# --- at the table ---------------------------------------------------------------------------------------


def test_the_director_acts_once_per_round_before_betting_and_announces_it():
    c = controller()
    assert not c.table.environment                                     # nothing before the core is chosen
    c.drain_notices()
    c.choose(c.choice.options[0].id)
    events = [n for n in c.drain_notices() if n.data.get("environment")]
    assert len(events) == 1 and events[0].data["environment"] == "added" and len(c.table.environment) == 1
    # A rule change is a Chaos rule notice: the host reacts and the table glitches, as for any Chaos rule.
    assert events[0].kind == NoticeKind.RULE_MODIFIER_APPLIED and events[0].data["rule_name"]
    before = list(c.table.environment)
    c.table.director_turn()                                            # a second call this round does nothing
    assert c.table.environment == before and c.table.acted_round == 1
    c.place_bet(c.bet_limits()[0])
    assert c.phase in (TablePhase.PLAYER_TURN, TablePhase.ROUND_OVER)  # no Chaos phase after the deal


def test_rules_age_and_timed_rules_end():
    c = controller(stages=json.dumps([[1, 0, 3, 99]]))
    c.choose(c.choice.options[0].id)
    c.table.environment = [env.markup(10, rounds=1), env.fixed(ranks("7"), 9)]
    play_round(c)
    assert [r.type for r in c.table.environment] == ["fixed"] and c.table.environment[0].age == 1
    assert c.table.env_history[-1] == {"type": "markup", "signature": env.markup(10, rounds=1).signature,
                                       "cause": "expired", "round": 1}


def test_saving_and_loading_never_redraws():
    c = controller(seed=11)
    c.choose(c.choice.options[0].id)
    play_round(c)
    data = RunSaveData.from_dict(c.save("x").to_dict())
    loaded = GameController.from_save(data, save_fn=lambda d, n: n)
    assert loaded.table.environment == c.table.environment and loaded.table.acted_round == c.run.round
    loaded.table.director_turn()
    assert loaded.table.environment == c.table.environment


def test_shopping_does_not_change_the_environment():
    a, b = controller(seed=3), controller(seed=3)
    for c in (a, b):
        c.choose(c.choice.options[0].id)
    if b.shop.offers and b.offer_usability(b.shop.offers[0]).ok:
        b.buy(b.shop.offers[0].item)
    if b.reroll_price() is not None:
        b.reroll_shop()
    for _ in range(4):
        play_round(a)
        play_round(b)
        assert a.table.environment == b.table.environment


@pytest.mark.parametrize("seed", range(6))
def test_a_long_run_keeps_every_limit(seed):
    c = controller(seed=seed, stages=json.dumps(DEFAULTS["stages"]))
    c.choose(c.choice.options[-1].id)                                  # cash: no core
    c.run.money, c.run.target_money = 10_000, 10**9                   # keep playing all 30 rounds
    d = c.table.director
    acted = 0
    for _ in range(30):
        assert c.phase == TablePhase.BETTING
        rules = c.table.environment
        stage = d.stage(c.run.round)
        assert len(rules) <= stage.slots and len({r.type for r in rules}) == len(rules)
        assert sum(d.pressure(r) for r in rules) <= stage.budget or c.run.round == 1
        assert sum(1 for r in rules if r.tier == 3) <= 1               # one heavy rule at most ...
        assert c.run.round >= 9 or all(r.tier < 3 for r in rules)        # ... and none before round 9
        assert not {"hidden", "item_ban"} <= {r.type for r in rules}
        play_round(c)
    assert c.run.round == 31
    assert len({h["type"] for h in c.table.env_history} | {r.type for r in c.table.environment}) >= 3


def test_environment_rules_count_as_rules_seen():
    c = controller()
    tracker = RunTracker(c)
    c.choose(c.choice.options[0].id)
    assert any(k.startswith("ph_env_") for k in tracker.summary()["rules_seen"])



# --- what players and agents see (stage D) ------------------------------------------------------------------


def test_rules_show_as_cards_with_scope_time_and_removal():
    from chaos_blackjack.agent import AgentSession
    from chaos_blackjack.app.parts import PartContext, build_part

    c = controller(stages=json.dumps([[1, 0, 3, 99]]))
    c.choose(c.choice.options[0].id)
    c.table.environment = [env.fixed(ranks("7"), 9), env.markup(20, rounds=3)]
    rules = c.view().active_rules
    assert [(r.id, r.name, r.scope, r.remaining) for r in rules] == [
        ("fixed", "Seven Rewrite", "Both hands", None), ("markup", "Price Hike", "The shop", 3)]
    assert all(r.effect in r.description and r.removal for r in rules)
    full = build_part("core.rules", PartContext(c, c.view()), "full")
    cards = full[0].entries
    assert [e.badge for e in cards] == ["Light · Until removed", "Light · 3 rounds"] and "Clause Removal" in cards[0].text
    assert len(full) == 1                                              # no Chaos AI rule pool at this table
    obs = AgentSession(c, seed=7).observe()["chaos"]["active_rules"]
    assert obs[1] == {"id": "markup", "help": rules[1].description, "name": "Price Hike", "scope": "The shop",
                      "effect": rules[1].effect, "remaining": 3, "removal": rules[1].removal, "silenced": False,
                      "tier": "Light"}


def test_silenced_rules_stay_listed_and_marked():
    c = controller(stages=json.dumps([[1, 0, 3, 99]]))
    c.choose(c.choice.options[0].id)
    c.table.environment = [env.tie("dealer")]
    c.table.round.preparations.append("ph_silence")
    assert c.view().active_rules[0].silenced


def test_rule_names_read_naturally():
    assert env.fixed(ranks("7"), 9).title == "Seven Rewrite"
    assert env.fixed(ranks("J", "Q", "K"), 8).title == "Court Rewrite"
    assert env.shift((ranks("5"), 1)).title == "Five Up"
    assert env.shift((CardGroup("all"), -1)).title == "Whole Deck Down"
    assert env.shift((CardGroup("red"), 1), (CardGroup("black"), -1)).title == "Red-Black Shift"


def test_the_feed_names_the_change():
    from chaos_blackjack.gui.texts import notice_line

    c = controller()
    c.drain_notices()
    c.choose(c.choice.options[0].id)
    change = next(n for n in c.drain_notices() if n.data.get("environment") == "added")
    assert notice_line(change)[0].startswith("Poker Head changes the table:")



def test_the_chaos_ai_budget_is_not_shown_at_the_build_table():
    from chaos_blackjack.agent import AgentSession

    c = controller()
    assert not c.view().chaos_budget_shown
    assert AgentSession(c, seed=7).observe()["chaos"]["budget"] is None
    legacy = AgentSession.new(seed=7, chaos=True)
    assert legacy.controller.view().chaos_budget_shown and legacy.observe()["chaos"]["budget"] is not None
