"""J-54's table (v2, docs/design/J54_V2_SPEC.md): program of conditions, compute, deck shaping,
the Joker, firmware, bounty, goal, snapshot and saves. The evaluator has its own tests."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.j54.program import Program, Segment, generate, switches
from chaos_blackjack.j54.table import (CUT, CUT_CHOICE, FIRMWARE_CHOICE, GROUPS, HOT_PURGE, IN_DECK, RELEASE,
                                       SEALED, J54Table, joker)
from chaos_blackjack.modes import J54_RULES, get_mode
from chaos_blackjack.rules.plugins.j54_conditions import CONDITIONS
from chaos_blackjack.rules.plugins.j54_deck import DECK_RULES


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _config(seed: int = 1, **settings) -> RunConfig:
    cfg = get_mode("j54").apply(RunConfig.from_balance(default_balance(), seed=seed))
    return replace(cfg, mode_settings={**cfg.mode_settings, **{f"j54.{k}": v for k, v in settings.items()}})


def _controller(seed: int = 1, firmware: str | None = "none", **settings) -> GameController:
    """A J-54 run; `firmware` answers the opening choice (None leaves it open)."""
    if firmware not in (None, "none"):
        settings.setdefault("firmwares_offered", 4)
    c = GameController(_config(seed, **settings), save_fn=lambda d, n: n)
    if firmware is not None:
        c.choose(firmware)
    c.drain_notices()
    return c


def _force(c: GameController, rule: str = "j54_faces_set") -> None:
    """Put one condition in force for the whole run (and no bounty)."""
    t = c.table
    t.program = Program((Segment(rule, 1, t.rounds),))
    t.segment = 0
    t.bounty_rank = None


def _rig(c: GameController, player, dealer, deck=()) -> None:
    """Make the next deal fixed (the table's deck is still used for everything else)."""

    def fixed_round(seed=None, *, inventory_override=None, cards=None, ordered_cards=None):
        return GameState(tuple(player), tuple(dealer), tuple(deck), GamePhase.PLAYER_TURN,
                         inventory=inventory_override or ())

    c.loop.new_round = fixed_round  # type: ignore[method-assign]


def _hand(c: GameController, player, dealer, deck=(), bet: int = 10, stand: bool = True) -> None:
    _rig(c, player, dealer, deck)
    c.place_bet(bet)
    if stand and c.phase == TablePhase.PLAYER_TURN:
        c.stand()
    c.finish_dealer()


def _events(c: GameController) -> list[str]:
    return [n.text for n in c.drain_notices() if n.kind == NoticeKind.TABLE_EVENT]


# ------------------------------------------------------------------ mode


def test_mode_schedules_the_seven_conditions_and_sells_nothing() -> None:
    base = RunConfig.from_balance(default_balance())
    j54 = get_mode("j54").apply(base)
    mode = get_mode("j54")
    assert mode.name == "J-54's Table" and j54.host == "j54" and j54.enable_chaos
    assert j54.rule_pool == J54_RULES and set(J54_RULES) == set(CONDITIONS) and j54.shop_prices == {}
    assert not set(DECK_RULES) & set(J54_RULES)  # v1's deck rules stay registered, in no pool
    assert j54.start_money == 100
    for other in ("normal", "chaos"):
        cfg = get_mode(other).apply(base)
        assert not {r for r, _, _ in cfg.chaos_stub} & set(J54_RULES)
    assert set(J54_RULES) <= set(get_mode("chaos").apply(base).disabled_rules)  # Poker Head: "all" but these


def test_plain_tables_have_no_mechanics() -> None:
    c = GameController(get_mode("normal").apply(RunConfig.from_balance(default_balance(), seed=1)))
    assert c.table is None and c.view().table_info == () and c.view().fee == 0


def test_the_goal_is_the_target_from_round_nine_or_a_capture() -> None:
    c = _controller()
    assert isinstance(c.table, J54Table) and c.run.target_money == 175 and c.view().fee == 0
    assert J54Table.goal(c.config) == "Reach 175 chips from round 9, or capture the Joker"
    assert c.bet_limits() == (5, 50) and c.table.should_chaos() is False


# ------------------------------------------------------------------ program


@pytest.mark.parametrize("seed", range(10))
def test_program_covers_the_run_with_the_configured_switches(seed: int) -> None:
    t = _controller(seed).table
    segs = t.program.segments
    assert segs[0].start == 1 and segs[-1].end == 16
    assert all(a.end + 1 == b.start for a, b in zip(segs, segs[1:]))
    assert all(2 <= s.length <= 4 for s in segs)
    assert all(a.rule != b.rule for a, b in zip(segs, segs[1:]))
    assert t.conditions[segs[0].rule].camp == "classic"
    assert 1 <= switches([t.conditions[s.rule].camp for s in segs]) <= 2
    assert t.program == _controller(seed).table.program  # drawn from the seed


def test_switch_count_and_options_follow_the_profile() -> None:
    assert switches(["classic", "anti", "classic"]) == 2
    assert switches(["classic", "loner", "anti"]) == 1   # two halves
    assert switches(["classic", "loner", "classic"]) == 1
    assert switches(["anti", "loner"]) == 0              # a half, rounded down
    camps = {r: m for r, (_, _, d) in CONDITIONS.items() for m in [d["camp"]]}
    p = generate(3, 16, camps, (4, 4), (0, 0), False)
    assert [s.length for s in p.segments] == [4, 4, 4, 4]
    assert switches([camps[s.rule] for s in p.segments]) == 0


def test_condition_changes_at_the_segment_start_and_is_announced_a_round_ahead() -> None:
    c = _controller(4)
    t = c.table
    seen = {}
    while c.run.round <= 12 and c.phase != TablePhase.RUN_OVER:
        r = c.run.round
        seg = t.program.at(r)
        assert t.condition().id == seg.rule and t.rounds_left() == seg.end - r + 1
        nxt = t.program.next_after(r)
        if r == seg.end and nxt is not None:
            assert t.announcement == f"Next condition: {t.conditions[nxt.rule].camp} camp."
            assert t.public().announcement == t.announcement
        else:
            assert t.announcement is None
        seen[r] = t.condition().id
        c.run.money = 100  # keep playing
        _hand(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("8", "♦")])
        c.next_round()
        events = _events(c)
        if c.run.round == t.program.at(c.run.round).start:
            assert any(e.startswith(f"Condition {t.segment + 1} begins") for e in events)
    assert len(set(seen.values())) >= 2


def test_announcement_modes() -> None:
    def last_round_of_first(c):
        return c.table.program.segments[0].end

    c = _controller(4, announce="rule")
    end = last_round_of_first(c)
    c.table._enter_round(end)
    nxt = c.table.conditions[c.table.program.segments[1].rule]
    assert c.table.announcement == f"Next condition: {nxt.text}."
    c = _controller(4, announce="none")
    c.table._enter_round(last_round_of_first(c))
    assert c.table.announcement is None and c.table.public().program is None
    c = _controller(4, announce="schedule")
    program = c.table.public().program
    assert [p["id"] for p in program] == [s.rule for s in c.table.program.segments]
    assert program[0]["start"] == 1 and program[-1]["end"] == 16


def test_program_and_condition_survive_a_save() -> None:
    c = _controller(6)
    _hand(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("8", "♦")])
    c.next_round()
    data = c.save("x")
    loaded = GameController.from_save(RunSaveData.from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.table.to_dict() == c.table.to_dict()
    assert loaded.table.program == c.table.program and loaded.table.condition() == c.table.condition()
    assert loaded.view().active_rules == c.view().active_rules


# ------------------------------------------------------------------ values


def test_conditions_change_only_j54s_cards() -> None:
    c = _controller()
    _force(c, "j54_black_plus")
    hand = (_c("10", "♣"), _c("7", "♠"))
    assert c.hand_value(hand, "dealer") == 19 and c.hand_value(hand, "player") == 17
    _force(c, "j54_hearts_scale")
    assert c.hand_value((_c("A", "♥"), _c("9", "♣")), "dealer") == 11  # A♥ is 22 or 2
    _force(c, "j54_faces_set")
    assert c.hand_value((_c("K"), _c("Q", "♦")), "dealer") == 10 and c.hand_value((_c("K"), _c("Q")), "player") == 20
    rule = c.table.conditions["j54_black_plus"]
    assert rule.adjust_rank_value(_c("5"), 5) == 5 and rule.adjust_rank_value_for(_c("5"), 5, "dealer") == 6


def test_a_stand_threshold_changes_when_j54_stops_drawing() -> None:
    c = _controller()
    _force(c, "j54_stand_15")
    _hand(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("5", "♦")], deck=[_c("K")])
    assert c.last_result.dealer_total == 15 and c.last_result.outcome == "player"
    c.next_round()
    _force(c, "j54_stand_19")
    _hand(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("7", "♦")], deck=[_c("2"), _c("5")])
    assert c.last_result.dealer_total == 19 and c.last_result.outcome == "push"


def test_firmware_changes_the_players_values_only_and_costs_chips() -> None:
    c = _controller(firmware="fw_fives")
    assert c.run.money == 80 and c.table.firmware.id == "fw_fives"
    _force(c)  # a condition that leaves these cards alone
    hand = (_c("5"), _c("6", "♥"))
    assert c.hand_value(hand, "player") == 20 and c.hand_value(hand, "dealer") == 11
    m = _controller(firmware="fw_margin")
    assert m.run.money == 70
    hand = (_c("10"), _c("8"), _c("4"))
    pc, dc = m.loop.context("player"), m.loop.context("dealer")
    assert not m.loop.rules.is_bust(22, pc) and m.loop.rules.is_bust(22, dc)
    _force(m)
    _rig(m, [_c("10"), _c("8")], [_c("10", "♥"), _c("9", "♦")], deck=[_c("4")])
    m.place_bet(10)
    m.hit()
    assert m.phase == TablePhase.PLAYER_TURN and m.view().player_total == 22


def test_firmware_choice_offers_three_and_none() -> None:
    c = _controller(firmware=None)
    choice = c.view().choice
    assert choice.kind == FIRMWARE_CHOICE and not choice.cancellable
    ids = [o.id for o in choice.options]
    assert len(ids) == 4 and ids[-1] == "none" and all("chips" in o.label for o in choice.options[:3])
    assert c.moves() and all(m.action == "choose" for m in c.moves())
    with pytest.raises(ActionError):
        c.place_bet(10)
    c.choose(ids[0])
    assert c.run.money == 100 - c.table.firmware_price(ids[0]) and c.table.firmware.id == ids[0]


def test_the_joker_is_a_soft_ace_for_the_player_and_zero_for_j54() -> None:
    c = _controller()
    _force(c)
    assert c.hand_value((joker(), _c("9")), "player") == 20
    assert c.hand_value((joker(), _c("9"), _c("5")), "player") == 15
    assert c.hand_value((joker(), _c("9")), "dealer") == 9


# ------------------------------------------------------------------ compute and moves


def test_compute_income_cap_and_costs() -> None:
    c = _controller()
    t = c.table
    assert t.compute == 2 and dict(c.view().table_info)["Compute"] == "2/8"
    _hand(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("8", "♦")])
    c.next_round()
    assert t.compute == 4
    t.compute = 7
    _hand(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("8", "♦")])
    c.next_round()
    assert t.compute == 8  # the cap
    c.perform(CUT, "5r")
    c.perform(HOT_PURGE)
    assert t.compute == 6
    c.perform(RELEASE)
    assert t.compute == 0 and t.joker == IN_DECK


def test_cut_removes_two_cards_of_the_group() -> None:
    c = _controller()
    t = c.table
    c.perform(CUT, "5r")
    assert t.group_counts()["5r"] == 0 and t.group_counts()["5b"] == 2 and len(t.cards) == 50
    assert {(str(x.rank), x.suit) for x in t.removed} == {("5", "♥"), ("5", "♦")}
    moves = {(m.action, m.arg): m for m in c.moves()}
    assert not moves[(CUT, "5r")].enabled and "No 5 red" in moves[(CUT, "5r")].reason
    with pytest.raises(ActionError):
        c.perform(CUT, "5r")
    assert dict(c.view().table_info)["Removed"] == "2 cards"


def test_cut_without_a_group_asks_which() -> None:
    c = _controller()
    c.perform(CUT)
    choice = c.view().choice
    assert choice.kind == CUT_CHOICE and choice.cancellable and len(choice.options) == len(GROUPS)
    c.cancel_choice()
    assert c.table.compute == 2
    c.perform(CUT)
    c.choose("Kb")
    assert c.table.group_counts()["Kb"] == 0 and c.table.compute == 1


def test_hot_purge_takes_one_of_the_three_hottest_ranks() -> None:
    c = _controller()
    hottest = c.table._hottest_ranks(3)  # noqa: SLF001
    c.perform(HOT_PURGE)
    counts = dict(c.table.deck_counts())
    purged = [r for r, n in counts.items() if n == 1]
    assert len(purged) == 1 and purged[0] in hottest and len(c.table.cards) == 49
    assert any(e.startswith(f"Hot Purge drew rank {purged[0]}") for e in _events(c))


def test_hottest_ranks_follow_the_heat() -> None:
    c = _controller()
    _force(c, "j54_stand_19")
    heat = c.table.public().heat
    per_rank = {r: heat.get(f"{r}r", 0.0) + heat.get(f"{r}b", 0.0) for r, n in c.table.deck_counts() if n}
    expected = sorted(per_rank, key=lambda r: (-per_rank[r], list(per_rank).index(r)))[:3]
    assert c.table._hottest_ranks(3) == expected  # noqa: SLF001
    assert all(per_rank[r] >= max(v for k, v in per_rank.items() if k not in expected) for r in expected)


def test_moves_stop_at_the_deck_floor_and_without_compute() -> None:
    c = _controller()
    c.table.settings["min_deck"] = 52
    moves = {(m.action, m.arg): m for m in c.moves() if m.table}
    for key in ((CUT, ""), (CUT, "5r"), (HOT_PURGE, "")):
        assert not moves[key].enabled and "minimum of 52" in moves[key].reason
    assert "Not enough compute" in moves[(RELEASE, "")].reason
    with pytest.raises(ActionError):
        c.perform(HOT_PURGE)
    c.table.settings["min_deck"] = 51
    c.table.compute = 8
    c.perform(CUT, "Ab")  # stops at the floor: one card goes
    assert len(c.table.cards) == 51 and c.table.group_counts()["Ab"] == 1


def test_moves_are_offered_while_betting_only() -> None:
    c = _controller()
    _rig(c, [_c("10"), _c("6")], [_c("10", "♥"), _c("8", "♦")], deck=[_c("2")])
    c.place_bet(10)
    assert not [m for m in c.moves() if m.table]
    with pytest.raises(ActionError):
        c.perform(HOT_PURGE)


# ------------------------------------------------------------------ the Joker


def test_release_puts_the_joker_in_the_deck_once() -> None:
    c = _controller()
    c.table.compute = 8
    c.perform(RELEASE)
    t = c.table
    assert t.joker == IN_DECK and t.deck_size == 53 and joker() in t.round_cards()
    move = next(m for m in c.moves() if m.action == RELEASE)
    assert not move.enabled and move.reason == "The Joker is already released."
    with pytest.raises(ActionError):
        c.perform(RELEASE)


def _released(c: GameController) -> None:
    c.table.compute = 8
    c.perform(RELEASE)
    _force(c)


def test_a_capture_wins_only_from_round_nine_on_a_hand_not_lost() -> None:
    c = _controller()
    _released(c)
    _hand(c, [joker(), _c("9")], [_c("10", "♥"), _c("7", "♦")])  # round 1: a win, but too early
    assert c.last_result.outcome == "player" and c.table.joker == IN_DECK and c.run_end is None
    assert any("not recorded yet" in e for e in _events(c))
    c.next_round()
    c.run.round = 9
    _hand(c, [joker(), _c("6")], [_c("10", "♥"), _c("9", "♦")])  # a loss: the Joker returns
    assert c.last_result.outcome == "dealer" and c.table.joker == IN_DECK and c.run_end is None
    c.next_round()
    _hand(c, [joker(), _c("7")], [_c("10", "♥"), _c("8", "♦")])  # a push from round 9: captured
    assert c.last_result.outcome == "push"
    assert c.phase == TablePhase.RUN_OVER and c.run_end.kind == "victory" and "captured" in c.run_end.message
    assert c.table.joker == "captured" and c.table.public().joker == "captured"
    assert c.table.host_variant("victory") == "capture" and c.table.host_variant("defeat") == ""


def test_a_surrender_never_captures() -> None:
    c = _controller()
    _released(c)
    c.run.round = 10
    _rig(c, [joker(), _c("5")], [_c("10", "♥"), _c("9", "♦")])
    c.place_bet(10)
    c.surrender()
    assert c.table.joker == IN_DECK and c.run_end is None


def test_j54_never_keeps_the_joker() -> None:
    c = _controller()
    _released(c)
    _rig(c, [_c("10"), _c("7")], [joker(), _c("8", "♦")], deck=[_c("9", "♣"), _c("4"), _c("3")])
    c.place_bet(10)
    dealer = c.state.dealer_hand
    assert joker() not in dealer and dealer[0] == _c("9", "♣")
    assert joker() in c.state.deck and c.state.deck[0] != joker()  # shuffled back, never on top
    assert len(c.table.cards) == 53 and any("J-54 drew the Joker" in e for e in _events(c))


# ------------------------------------------------------------------ round end


def test_entropy_adds_a_low_card_after_every_settlement() -> None:
    c = _controller()

    def lows() -> int:
        return sum(1 for x in c.table.cards if str(x.rank) in ("2", "3", "4", "5", "6"))

    assert lows() == 20
    _hand(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("8", "♦")])
    assert len(c.table.cards) == 53 and lows() == 21
    assert any(e.startswith("Entropy: J-54 added") for e in _events(c))


def test_the_bounty_pays_for_every_named_rank_in_your_hand() -> None:
    c = _controller()
    _force(c)
    c.table.bounty_rank = "7"
    _hand(c, [_c("7"), _c("7", "♥")], [_c("10", "♥"), _c("8", "♦")])
    assert c.last_result.outcome == "dealer" and c.last_result.delta == -10 + 4 and c.run.money == 94
    assert any(e.startswith("Bounty: 4 chips") for e in _events(c))


def test_each_condition_names_a_bounty_rank(monkeypatch) -> None:
    """The rank whose removal helps the player most on the heat map, ties by rank order; the rank the
    condition raises most for J-54 when no removal helps."""
    import chaos_blackjack.j54.table as j54_table

    c = _controller()
    t = c.table
    named = {}
    for rule in ("j54_black_plus", "j54_hearts_scale", "j54_low_plus", "j54_stand_15"):
        _force(c, rule)
        named[rule] = t._bounty_rank()
    assert named == {"j54_black_plus": "7", "j54_hearts_scale": "A", "j54_low_plus": "2", "j54_stand_15": "10"}
    assert len(set(named.values())) == 4  # no longer "2" for nearly every condition
    monkeypatch.setattr(j54_table, "measure", lambda table: (None, {"5r": -0.1, "5b": -0.2}))
    _force(c, "j54_hearts_scale")
    assert t._bounty_rank() == "A"  # the fallback: hearts double, so aces gain most
    _force(c, "j54_stand_15")
    assert t._bounty_rank() == "2"  # a threshold raises nothing: the first rank
    assert t.public().bounty is None or t.public().bounty["chips"] == 2


def test_the_target_wins_only_from_round_nine() -> None:
    c = _controller()
    _force(c)
    c.run.money = 170
    c.run.round = 8
    _hand(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("7", "♦")])
    assert c.run.money == 180 and c.run_end is None and c.phase == TablePhase.ROUND_OVER
    c.next_round()
    _hand(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("7", "♦")])
    assert c.run_end.kind == "victory" and "190 chips" in c.run_end.message


def test_the_run_is_lost_when_round_sixteen_settles_without_a_win() -> None:
    c = _controller()
    _force(c)
    c.run.round = 16
    _hand(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("7", "♦")])
    assert c.run_end.kind == "defeat" and "Round 16" in c.run_end.message and c.phase == TablePhase.RUN_OVER


# ------------------------------------------------------------------ public snapshot and agent


def test_public_snapshot_and_agent_observation() -> None:
    c = _controller(firmware="fw_low")
    snap = c.table.public()
    d = snap.to_dict()
    assert d["kind"] == "j54" and d["compute"] == 2 and d["compute_cap"] == 8
    assert set(d["condition"]) == {"id", "name", "text", "camp", "rounds_left"}
    assert d["firmware"]["id"] == "fw_low" and d["firmware"]["name"] == "Low Firmware" and d["joker"] == SEALED
    assert d["deck_size"] == 52 and d["removed"] == 0 and d["bounty"]["chips"] == 2
    assert 0 < d["bar"] < 1 and -1 < d["ev"] < 1 and d["capture"] == 0
    assert 0 < len(d["heat"]) <= 26 and set(d["heat"]) <= set(GROUPS)
    assert set(d["band"]) == {"low", "stake_pct", "suggested"} and d["band"]["suggested"] >= c.view().bet_min
    assert [b["low"] for b in d["bands"]] == [50, 55, 60] and d["seen"][0]["id"] == d["condition"]["id"]
    assert c.view().table_public == snap

    s = AgentSession.new(seed=5, mode="j54")
    obs = s.observe()
    assert obs["choice"]["kind"] == FIRMWARE_CHOICE and [o["id"] for o in obs["choice"]["options"]][-1] == "none"
    obs = s.execute({"cmd": "choose", "option": "none"})["obs"]
    public = obs["table"]["public"]
    assert obs["phase"] == "betting" and public["compute"] == 2
    assert {"bar", "ev", "band", "capture", "heat"} <= set(public) and 0 < public["bar"] < 1
    assert {a["action"] for a in obs["table_actions"]} == {CUT, HOT_PURGE, RELEASE}
    release = next(a for a in obs["table_actions"] if a["action"] == RELEASE)
    assert not release["enabled"] and "compute" in release["reason"]
    assert sum(obs["table"]["deck"].values()) == 52 and obs["shop"] is None
    assert "Shop:" not in obs["summary"] and "Active chaos rules" not in obs["summary"]
    assert obs["summary"].count(public["condition"]["name"]) == 1 and "Condition" not in obs["table"]["info"]
    reply = s.execute({"cmd": "perform", "action": CUT, "arg": "9b"})
    assert reply["ok"] and reply["obs"]["table"]["public"]["removed"] == 2
    assert reply["obs"]["table"]["public"]["heat"] != public["heat"]  # recomputed after the move
    obs = s.execute({"cmd": "perform", "action": CUT, "arg": ""})["obs"]
    assert obs["choice"]["kind"] == CUT_CHOICE and all(" pp · " in o["help"] for o in obs["choice"]["options"])
    obs = s.execute({"cmd": "choose", "option": "5r"})["obs"]
    assert obs["choice"] is None and obs["table"]["public"]["removed"] == 4
    assert AgentSession.new(seed=5).observe()["table"] is None


def test_the_cut_choice_shows_each_groups_heat() -> None:
    c = _controller()
    heat = c.table.public().heat
    c.perform(CUT)
    for option in c.view().choice.options:
        pp = heat[option.id]
        assert option.description == f"{pp:+.1f} pp · {'cut' if pp > 0 else 'keep'}"


def test_the_meter_reads_plain_blackjack_signs_under_a_classic_condition() -> None:
    from chaos_blackjack.j54.public import band_for, parse_bands

    c = _controller()
    _force(c, "j54_black_plus")
    snap = c.table.public()
    assert 0 <= snap.bar <= 1
    assert snap.rank_heat("5") > 0 and snap.rank_heat("10") < 0  # removing 5s helps, removing tens hurts
    bands = parse_bands("50:10,55:20,60:30")
    assert band_for(0.45, bands, 200, 5, 100) == {"low": 0, "stake_pct": 0, "suggested": 5}
    assert band_for(0.57, bands, 200, 5, 100) == {"low": 55, "stake_pct": 20, "suggested": 40}
    assert band_for(0.70, bands, 400, 5, 100)["suggested"] == 100  # within the bet range


def test_releasing_the_joker_shows_a_capture_chance() -> None:
    c = _controller()
    c.table.compute = 8
    c.perform(RELEASE)
    snap = c.table.public()
    assert snap.joker == IN_DECK and 0 < snap.capture < 1 and snap.deck_size == 53


def test_an_empty_shop_is_never_announced() -> None:
    c = _controller()
    for _ in range(4):
        _hand(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("7", "♦")])
        c.next_round()
        assert not [n for n in c.drain_notices() if n.kind == NoticeKind.SHOP_RESTOCKED]


def test_host_lines_cover_v2_and_the_capture_victory() -> None:
    from chaos_blackjack.content.builtin_persona import host_persona
    from chaos_blackjack.content.host_script import host_script, host_scripts

    expressions = set(host_persona("j54").portraits)
    capture = host_scripts("j54", "victory", mode="j54", variant="capture")
    assert capture and capture != host_scripts("j54", "victory", mode="j54")
    for event in ("intro", "victory", "defeat"):
        for script in host_scripts("j54", event, mode="j54") + capture:
            assert script and all(b.mood in expressions and b.text for b in script)
    assert host_script("j54", "victory", random.Random(1), variant="capture") in capture
    assert _controller().table.host_variant("victory") == ""
    persona = host_persona("j54")
    assert persona.line("table_condition") and persona.line("table_release")
    assert {persona.moods["table_condition"], persona.moods["table_release"]} <= expressions


# ------------------------------------------------------------------ saves


def test_a_save_in_the_middle_of_a_choice_restores_it() -> None:
    c = _controller(firmware=None)
    data = c.save("x")
    loaded = GameController.from_save(RunSaveData.from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.choice == c.choice and loaded.table.to_dict() == c.table.to_dict()
    loaded.choose("none")
    loaded.perform(CUT)
    data = loaded.save("y")
    again = GameController.from_save(RunSaveData.from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert again.choice.kind == CUT_CHOICE
    again.choose("Qr")
    assert again.table.group_counts()["Qr"] == 0 and again.table.compute == 1


def test_save_and_agent_state_restore_the_table() -> None:
    s = AgentSession.new(seed=5, mode="j54")
    for cmd in ({"cmd": "choose", "option": "none"}, {"cmd": "perform", "action": HOT_PURGE, "arg": ""},
                {"cmd": "bet", "amount": 10}, {"cmd": "act", "action": "stand"}):
        s.execute(cmd)
    resumed = AgentSession.from_state(s.to_state())
    assert resumed.controller.table.to_dict() == s.controller.table.to_dict()
    assert resumed.observe() == s.observe()
    for cmd in ({"cmd": "bet", "amount": 10}, {"cmd": "act", "action": "stand"}):
        assert resumed.execute(cmd) == s.execute(cmd)

    data = s.controller.save("x")
    loaded = GameController.from_save(type(data).from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.table.to_dict() == s.controller.table.to_dict()
    assert loaded.run.target_money == s.controller.run.target_money == 175


def test_a_demo_save_is_refused() -> None:
    c = _controller()
    with pytest.raises(ValueError):
        c.table.restore({"protocol": "capture", "cards": []})


@pytest.mark.parametrize("seed", range(20))
def test_runs_finish_without_errors(seed: int) -> None:
    rng = random.Random(seed)
    c = _controller(seed, firmware=None)
    for _ in range(600):
        v = c.view()
        if v.phase == TablePhase.RUN_OVER:
            break
        if v.choice is not None:
            options = [o.id for o in v.choice.options]
            c.choose(rng.choice(options))
        elif v.phase == TablePhase.BETTING:
            moves = [m for m in v.moves if m.table and m.enabled]
            if moves and rng.random() < 0.6:
                m = rng.choice(moves)
                c.perform(m.action, m.arg)
                continue
            c.place_bet(rng.randint(v.bet_min, v.bet_max))
        elif v.phase == TablePhase.PLAYER_TURN:
            c.hit() if v.player_total < 15 else c.stand()
        elif v.phase == TablePhase.DEALER_TURN:
            c.dealer_step()
        elif v.phase == TablePhase.ROUND_OVER:
            c.next_round()
    assert c.view().phase == TablePhase.RUN_OVER and c.run.round <= 16
    assert len(c.table.cards) >= c.table.min_deck


def test_a_seeded_run_through_the_agent_cli_finishes(capsys, tmp_path) -> None:
    """The one-shot CLI with a run file: firmware, cuts by heat, the suggested stake, until the run ends."""
    import json

    from chaos_blackjack.agent.__main__ import main

    def cli(*args: str) -> dict:
        main(["--state", str(tmp_path / "run.json"), "--compact", *args])
        return json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    r = cli("new", "--mode", "j54", "--seed", "11")
    assert r["ok"] and r["obs"]["choice"]["kind"] == FIRMWARE_CHOICE
    r = cli("choose", r["obs"]["choice"]["options"][0]["id"])
    for _ in range(300):
        obs = r["obs"]
        assert r["ok"], r
        if obs["phase"] == "run_over":
            break
        if obs["phase"] == "betting":
            public = obs["table"]["public"]
            cuts = {a["arg"]: a for a in obs["table_actions"] if a["action"] == CUT and a["arg"] and a["enabled"]}
            hot = max(cuts, key=lambda g: public["heat"].get(g, 0), default=None)
            if hot and public["heat"].get(hot, 0) > 0:
                r = cli("perform", CUT, hot)
                assert r["obs"]["table"]["public"]["compute"] == public["compute"] - 1
                continue
            low, high = obs["bet_range"]
            r = cli("bet", str(max(low, min(high, public["band"]["suggested"]))))
        else:
            r = cli("act", "hit" if obs["you"]["total"] < 13 else "stand")
    assert r["obs"]["phase"] == "run_over" and r["obs"]["run_end"]["kind"] in ("victory", "defeat")


def test_meta_run_saves_resumes_and_finishes() -> None:
    from chaos_blackjack import meta
    from chaos_blackjack.meta.fake import install_fake

    install_fake(demo=False)
    try:
        p = meta.create_player(1, "J54")
        run = meta.start_run(p.id, "j54", seed=9)
        c = run.controller
        assert c.table is not None and run.config.mode == "j54"
        c.choose("none")
        c.place_bet(10)
        c.stand()
        c.finish_dealer()
        c.next_round()
        c.save("auto")
        resumed = meta.resume_run(p.id)
        assert resumed is not None and resumed.controller.table.to_dict() == c.table.to_dict()
        rc = resumed.controller
        while rc.phase != TablePhase.RUN_OVER:
            v = rc.view()
            if rc.phase == TablePhase.BETTING:
                rc.place_bet(v.bet_min)
            elif rc.phase == TablePhase.PLAYER_TURN:
                rc.stand()
            elif rc.phase == TablePhase.DEALER_TURN:
                rc.finish_dealer()
            elif rc.phase == TablePhase.ROUND_OVER:
                rc.next_round()
        reward = meta.finish_run(resumed.run_id, rc)
        assert reward is not None
    finally:
        meta.use_service(None)


# ------------------------------------------------------- deck operations


def _ctx(cards=None, deck=None, removed=None, player=(), dealer=(), min_deck=0):
    from chaos_blackjack.j54.deck_ops import DeckContext

    counter = iter(range(10**6))
    return DeckContext(list(cards if cards is not None else []), list(removed or []),
                       lambda: random.Random(next(counter)), min_deck, deck, tuple(player), tuple(dealer))


def test_deck_operations_are_validated() -> None:
    from chaos_blackjack.j54.deck_ops import DeckOp

    for bad in ({"op": "explode"}, {"op": "add", "select": "drawn"}, {"op": "add", "count": "all"},
                {"op": "move_top", "select": "low", "when": "round_end"}, {"op": "add", "select": "rank:Z"},
                {"op": "remove", "count": 0}, {"op": "return", "select": "low"}):
        with pytest.raises(ValueError):
            DeckOp.from_params(bad)


def test_deletions_keep_the_minimum_and_feed_the_removed_pile() -> None:
    from chaos_blackjack.j54.deck_ops import DeckOp, apply

    ctx = _ctx(cards=[_c(r) for r in ("2", "3", "4", "K")], min_deck=2)
    gone = apply(DeckOp.from_params({"op": "remove", "select": "low", "count": "all"}), ctx)
    assert len(gone.cards) == 2 and len(ctx.cards) == 2 and ctx.removed == gone.cards


def test_deck_make_up_is_public() -> None:
    c = _controller()
    counts = dict(c.view().deck_counts)
    assert counts == {r: 4 for r in ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")}
