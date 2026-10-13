"""J-54's table (demo): persistent deck, protocols, fee, contracts, Joker, deck rules."""

from __future__ import annotations

from dataclasses import replace

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.j54.table import J54Table, joker
from chaos_blackjack.modes import J54_CONTRACTS, J54_RULES, get_mode
from chaos_blackjack.rules.modifiers import ActiveModifiers


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _config(seed: int = 1, protocol: str | None = None, **settings) -> RunConfig:
    cfg = get_mode("j54").apply(RunConfig.from_balance(default_balance(), seed=seed))
    extra = {f"j54.{k}": v for k, v in settings.items()}
    if protocol:
        extra["j54.protocols"] = protocol
    return replace(cfg, mode_settings={**cfg.mode_settings, **extra})


def _controller(seed: int = 1, protocol: str | None = None, **settings) -> GameController:
    c = GameController(_config(seed, protocol, **settings), save_fn=lambda d, n: n)
    c.drain_notices()
    return c


def _rig(c: GameController, player, dealer, deck=()) -> None:
    """Make the next deal fixed (the table's deck is still used for everything else)."""

    def fixed_round(seed=None, *, inventory_override=None, cards=None):
        c.loop.modifiers = c.loop.modifiers.with_cleared()
        return GameState(tuple(player), tuple(dealer), tuple(deck), GamePhase.PLAYER_TURN,
                         inventory=inventory_override or ())

    c.loop.new_round = fixed_round  # type: ignore[method-assign]


def _no_chaos(c: GameController) -> None:
    c.loop.pipeline.llm.choices = ()  # the offline Chaos AI stays calm


def _bet(c: GameController, amount: int = 10) -> None:
    c.place_bet(amount)
    if c.phase == TablePhase.CHAOS:
        c.resolve_chaos()


# ------------------------------------------------------------------ mode


def test_mode_keeps_its_rules_and_contracts_to_itself() -> None:
    base = RunConfig.from_balance(default_balance())
    j54 = get_mode("j54").apply(base)
    assert j54.rule_pool == J54_RULES and set(j54.shop_prices) == set(J54_CONTRACTS)
    assert j54.enable_chaos and j54.host == "j54" and j54.shop_refresh_rounds == 1
    for other in ("normal", "chaos"):
        cfg = get_mode(other).apply(base)
        assert not set(cfg.shop_prices) & set(J54_CONTRACTS)
        assert not {r for r, _, _ in cfg.chaos_stub} & set(J54_RULES)
        assert cfg.shop_refresh_rounds == 2
    assert set(J54_RULES) <= set(get_mode("chaos").apply(base).disabled_rules)  # Poker Head: "all" but these
    assert get_mode("normal").apply(base).rule_pool == ()


def test_plain_tables_have_no_mechanics() -> None:
    c = GameController(get_mode("normal").apply(RunConfig.from_balance(default_balance(), seed=1)))
    assert c.table is None and c.view().table_info == () and c.view().fee == 0


def test_protocol_is_drawn_per_run_and_sets_the_goal() -> None:
    seen = {_controller(seed).table.protocol for seed in range(30)}
    assert seen == {"capture", "capital"}
    capital = _controller(protocol="capital")
    assert (capital.run.objective, capital.run.target_money) == ("j54_capital", 250)
    capture = _controller(protocol="capture")
    assert (capture.run.objective, capture.run.target_money) == ("j54_capture", 0)
    assert dict(capture.view().table_info)["Joker"] == "sealed"


# --------------------------------------------------------------- economy


def test_compute_fee_grows_and_is_charged_before_the_bet() -> None:
    t = _controller().table
    assert [t.fee(r) for r in (1, 4, 5, 9, 13, 17, 21, 25)] == [0, 0, 1, 2, 4, 8, 16, 32]
    c = _controller(fee_steps="3")
    lo, hi = c.bet_limits()
    assert (lo, hi) == (5, (100 - 3) // 2)
    _no_chaos(c)
    _rig(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("7", "♦")])
    c.place_bet(10)
    assert c.run.money == 97 and any(n.kind == NoticeKind.FEE_PAID for n in c.drain_notices())


def test_minimum_bet_follows_the_fee() -> None:
    c = _controller(fee_steps="12")
    assert c.bet_limits()[0] == 12


# ------------------------------------------------------------------ deck


def test_deck_persists_and_entropy_adds_low_cards() -> None:
    c = _controller(protocol="capital")
    _no_chaos(c)
    assert c.table.deck_size == 52
    _rig(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("7", "♦")])
    _bet(c)
    c.stand()
    c.finish_dealer()
    assert c.table.deck_size == 53
    added = c.table.cards[-1]
    assert str(added.rank) in ("2", "3", "4", "5", "6")
    assert len(c.table.round_cards()) == 53  # the next round shuffles the changed deck


def test_contract_now_applies_at_once_and_is_not_an_item() -> None:
    c = _controller(protocol="capital")
    offer = next(o for o in c.shop.offers if o.item == "j54_low_purge") if any(
        o.item == "j54_low_purge" for o in c.shop.offers) else None
    if offer is None:
        c.shop = replace(c.shop, offers=c.shop.offers + (replace(c.shop.offers[0], item="j54_low_purge", price=10),))
    lows_before = sum(str(x.rank) in "23456" and len(str(x.rank)) == 1 for x in c.table.cards)
    c.buy("j54_low_purge")
    lows_after = sum(str(x.rank) in "23456" and len(str(x.rank)) == 1 for x in c.table.cards)
    assert lows_before - lows_after == 6 and c.table.deck_size == 46
    assert c.run.items == () and c.view().items == ()


def test_triggered_contract_waits_for_a_win() -> None:
    c = _controller(protocol="capital", entropy=0)
    _no_chaos(c)
    c.table.buy("j54_streamline", c.run)
    assert c.table.pending == ["j54_streamline"]
    assert dict(c.table.info(c.run))["Contracts"] == "Streamline Contract"
    _rig(c, [_c("10"), _c("6")], [_c("10", "♥"), _c("9", "♦")])  # 16 vs 19: a loss
    _bet(c)
    c.stand()
    c.finish_dealer()
    assert c.table.pending == ["j54_streamline"] and c.table.deck_size == 52
    c.next_round()
    _rig(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("8", "♦")])  # 19 vs 18: a win
    _bet(c)
    c.stand()
    c.finish_dealer()
    assert c.table.pending == [] and c.table.deck_size == 47


def test_deletions_stop_at_the_minimum_deck() -> None:
    t = _controller(protocol="capital").table
    for _ in range(20):
        t._fire("j54_streamline")
    assert t.deck_size == 12


# ----------------------------------------------------------------- Joker


def test_start_experiment_is_pinned_until_bought() -> None:
    c = _controller(protocol="capture")
    assert [o.item for o in c.shop.offers].count("j54_start_experiment") == 1
    assert len(c.shop.offers) == c.config.shop_slots
    c.run.money = 200
    c.buy("j54_start_experiment")
    assert c.table.jokers_in_deck == 1 and c.table.experiment
    assert sum(1 for x in c.table.round_cards() if str(x.rank) == "JK") == 1
    c.shop = c._roll_shop()
    assert "j54_start_experiment" not in [o.item for o in c.shop.offers]
    assert "j54_start_experiment" not in [o.item for o in _controller(protocol="capital").shop.offers]


def test_drawing_the_joker_wins_the_capture_protocol() -> None:
    c = _controller(protocol="capture")
    _no_chaos(c)
    c.table.jokers_sealed, c.table.jokers_in_deck, c.table.experiment = 0, 1, True
    _rig(c, [_c("10"), _c("4")], [_c("10", "♥"), _c("7", "♦")], deck=[joker(), _c("9")])
    _bet(c)
    c.hit()
    v = c.view()
    assert v.phase == TablePhase.RUN_OVER and v.run_end.kind == "victory"
    assert all(str(x.rank) != "JK" for x in c.state.player_hand)
    assert v.last_result.outcome == "push" and v.money == 100
    assert dict(c.table.info(c.run))["Joker"] == "captured"


def test_the_dealer_never_keeps_the_joker() -> None:
    c = _controller(protocol="capture")
    _no_chaos(c)
    c.table.jokers_sealed, c.table.jokers_in_deck, c.table.experiment = 0, 1, True
    _rig(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("4", "♦")], deck=[joker(), _c("3"), _c("9"), _c("K")])
    _bet(c)
    c.stand()
    c.finish_dealer()
    dealer = [str(x.rank) for x in c.state.dealer_hand]
    assert "JK" not in dealer and dealer[2] == "3"
    assert "JK" in [str(x.rank) for x in c.state.deck] and c.state.deck[0] != joker()
    assert not c.table.won and c.table.jokers_in_deck == 1
    # penalty (1) + entropy (2 once the experiment started)
    assert c.table.deck_size == 53 + 1 + 2


def test_capital_protocol_wins_at_the_target() -> None:
    c = _controller(protocol="capital")
    _no_chaos(c)
    c.run.money = 245
    _rig(c, [_c("10"), _c("9")], [_c("10", "♥"), _c("7", "♦")])
    _bet(c)
    c.stand()
    c.finish_dealer()
    assert c.phase == TablePhase.RUN_OVER and c.run_end.kind == "victory"


# ------------------------------------------------------------ deck rules


def test_injection_and_purge_change_this_round_and_the_rest_of_the_run() -> None:
    c = _controller(protocol="capital")
    t = c.table
    t.round_cards()
    state = GameState((_c("10"), _c("8")), (_c("10", "♥"), _c("7", "♦")),
                      (_c("5", "♦"), _c("5", "♣"), _c("9", "♦"), _c("K", "♦")), GamePhase.PLAYER_TURN)
    mods = ActiveModifiers(items=(c.registry.build_chaos_rule("j54_sample_injection", {"count": 3, "select": "rank:Q"}),))
    state, mods = t.after_chaos(state, mods)
    assert len(state.deck) == 7 and t.deck_size == 55
    assert "3 cards of rank Q" in mods.items[0].describe()
    mods = mods.with_added(c.registry.build_chaos_rule("j54_redundancy_purge", {"count": 3, "select": "rank:5"}))
    before = t.deck_size
    state, mods = t.after_chaos(state, mods)
    assert [str(x.rank) for x in state.deck].count("5") == 0 and t.deck_size == before - 2
    assert len(mods.items) == 2 and t.after_chaos(state, mods)[0] == state  # applied once


def test_burn_protocol_removes_the_drawn_cards() -> None:
    c = _controller(protocol="capital", entropy=0)
    _no_chaos(c)
    _rig(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("7", "♦")])
    _bet(c)
    c.loop.modifiers = c.loop.modifiers.with_added(c.registry.build_chaos_rule("j54_burn", {}))
    c.stand()
    c.finish_dealer()
    assert c.table.deck_size == 48
    assert _c("10") not in c.table.cards and _c("7", "♦") not in c.table.cards


# ------------------------------------------------------- save / agents


def test_save_and_agent_state_restore_the_table() -> None:
    s = AgentSession.new(seed=5, mode="j54")
    for cmd in ({"cmd": "bet", "amount": 10}, {"cmd": "act", "action": "stand"}):
        s.execute(cmd)
    resumed = AgentSession.from_state(s.to_state())
    assert resumed.controller.table.to_dict() == s.controller.table.to_dict()
    assert resumed.observe() == s.observe()
    for cmd in ({"cmd": "bet", "amount": 10}, {"cmd": "act", "action": "stand"}):
        assert resumed.execute(cmd) == s.execute(cmd)

    data = s.controller.save("x")
    assert data.table == s.controller.table.to_dict()
    loaded = GameController.from_save(type(data).from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.table.to_dict() == s.controller.table.to_dict()
    assert (loaded.run.objective, loaded.run.target_money) == (s.controller.run.objective,
                                                                s.controller.run.target_money)


def test_agent_observation_shows_the_table() -> None:
    obs = AgentSession.new(seed=5, mode="j54").observe()
    assert obs["table"]["info"]["Protocol"] in ("Single Capture", "Capital") and obs["table"]["fee"] == 0
    assert all(o["item"].startswith("j54_") and o["help"] for o in obs["shop"]["offers"])
    assert AgentSession.new(seed=5).observe()["table"] is None


@pytest.mark.parametrize("seed", range(12))
def test_runs_finish_without_errors(seed: int) -> None:
    c = _controller(seed)
    for _ in range(400):
        v = c.view()
        if v.phase == TablePhase.RUN_OVER:
            break
        if v.phase == TablePhase.BETTING:
            for o in v.shop_offers:
                if o.affordable and v.money - o.price > 40:
                    c.buy(o.item)
                    v = c.view()
            c.place_bet(v.bet_min)
        elif v.phase == TablePhase.CHAOS:
            c.resolve_chaos()
        elif v.phase == TablePhase.PLAYER_TURN:
            c.hit() if v.player_total < 15 else c.stand()
        elif v.phase == TablePhase.DEALER_TURN:
            c.dealer_step()
        elif v.phase == TablePhase.ROUND_OVER:
            c.next_round()
    assert c.view().phase == TablePhase.RUN_OVER
    assert isinstance(c.table, J54Table)


def test_meta_run_saves_resumes_and_finishes() -> None:
    from chaos_blackjack import meta
    from chaos_blackjack.meta.fake import install_fake

    install_fake(demo=False)
    try:
        p = meta.create_player(1, "J54")
        run = meta.start_run(p.id, "j54", seed=9)
        c = run.controller
        assert c.table is not None and run.config.mode == "j54"
        _bet(c)
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
                rc.place_bet(v.bet_max)
            elif rc.phase == TablePhase.CHAOS:
                rc.resolve_chaos()
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
    import random as _random

    from chaos_blackjack.j54.deck_ops import DeckContext

    counter = iter(range(10**6))
    return DeckContext(list(cards if cards is not None else []), list(removed or []),
                       lambda: _random.Random(next(counter)), min_deck, deck, tuple(player), tuple(dealer))


def test_deck_operations_are_validated() -> None:
    from chaos_blackjack.j54.deck_ops import DeckOp

    for bad in ({"op": "explode"}, {"op": "add", "select": "drawn"}, {"op": "add", "count": "all"},
                {"op": "move_top", "select": "low", "when": "round_end"}, {"op": "add", "select": "rank:Z"},
                {"op": "remove", "count": 0}, {"op": "return", "select": "low"}):
        with pytest.raises(ValueError):
            DeckOp.from_params(bad)


def test_moves_only_reorder_this_round() -> None:
    from chaos_blackjack.j54.deck_ops import DeckOp, apply

    deck = [_c("K"), _c("2"), _c("A", "♥"), _c("5"), joker()]
    ctx = _ctx(cards=[*deck[:4]], deck=list(deck))
    result = apply(DeckOp.from_params({"op": "move_bottom", "select": "high", "count": "all"}), ctx)
    assert [str(c.rank) for c in ctx.deck[:3]] == ["2", "5", "JK"] and len(result.cards) == 2
    assert {str(c.rank) for c in ctx.deck[3:]} == {"K", "A"} and len(ctx.cards) == 4
    apply(DeckOp.from_params({"op": "move_top", "select": "rank:5", "count": 1}), ctx)
    assert str(ctx.deck[0].rank) == "5"


def test_return_and_copy_bring_cards_back() -> None:
    from chaos_blackjack.j54.deck_ops import DeckOp, apply

    ctx = _ctx(cards=[_c("9")], removed=[_c("2"), _c("3"), _c("4")], deck=[_c("9")],
               player=(_c("10"), _c("7")), dealer=(_c("Q", "♥"), _c("6")))
    back = apply(DeckOp.from_params({"op": "return", "select": "removed", "count": 2}), ctx)
    assert len(back.cards) == 2 and len(ctx.removed) == 1 and len(ctx.cards) == 3 and len(ctx.deck) == 3
    copied = apply(DeckOp.from_params({"op": "copy", "select": "dealer_up", "count": "all"}), ctx)
    assert [str(c.rank) for c in copied.cards] == ["Q"] and len(ctx.cards) == 4
    apply(DeckOp.from_params({"op": "copy", "select": "player_hand", "count": "all"}), ctx)
    assert len(ctx.cards) == 6


def test_deletions_keep_the_minimum_and_feed_the_removed_pile() -> None:
    from chaos_blackjack.j54.deck_ops import DeckOp, apply

    ctx = _ctx(cards=[_c(r) for r in ("2", "3", "4", "K")], min_deck=2)
    gone = apply(DeckOp.from_params({"op": "remove", "select": "low", "count": "all"}), ctx)
    assert len(gone.cards) == 2 and len(ctx.cards) == 2 and ctx.removed == gone.cards


def test_backflow_returns_deleted_cards_at_the_table() -> None:
    c = _controller(protocol="capital")
    c.buy("j54_low_purge") if any(o.item == "j54_low_purge" for o in c.shop.offers) else c.table._fire("j54_low_purge")
    assert len(c.table.removed) == 6 and dict(c.view().table_info)["Removed"] == "6 cards"
    _no_chaos(c)
    _rig(c, [_c("10"), _c("8")], [_c("10", "♥"), _c("7", "♦")], deck=[_c("9")])
    _bet(c)
    rule = c.registry.build_chaos_rule("j54_data_backflow", {})
    c.state, c.loop.modifiers = c.table.after_chaos(c.state, c.loop.modifiers.with_added(rule))
    assert len(c.table.removed) == 2 and len(c.state.deck) == 5


def test_new_rules_are_data_and_describe_themselves() -> None:
    from chaos_blackjack.rules.plugins.j54_deck import DECK_RULES

    cfg = _config()
    assert set(DECK_RULES) == set(J54_RULES) == set(cfg.rule_pool)
    reg = _controller().registry
    for rid in DECK_RULES:
        m = reg.build_chaos_rule(rid, cfg.chaos_rule_params.get(rid, {}))
        assert m.describe().startswith(DECK_RULES[rid][0] + ": ")
    assert "bottom" in reg.build_chaos_rule("j54_layered_sort", {}).describe()


def test_deck_make_up_is_public() -> None:
    c = _controller(protocol="capture")
    counts = dict(c.view().deck_counts)
    assert counts == {r: 4 for r in ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")}
    obs = AgentSession.new(seed=5, mode="j54").observe()
    assert sum(obs["table"]["deck"].values()) == 52
