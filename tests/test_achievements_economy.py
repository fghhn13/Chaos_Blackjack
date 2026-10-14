"""Achievements for the chip economy and Poker Head's build table (2026-10-14)."""

from dataclasses import replace

from chaos_blackjack.achievements import AchievementContext, get_achievement
from chaos_blackjack.achievements.stats import CORES, RunFacts, run_stats
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.meta.tracker import RunTracker
from chaos_blackjack.modes import get_mode
from chaos_blackjack.poker_head.ownership import Holdings


def _table(core="ph_redeal"):
    cfg = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=7, use_llm=False))
    settings = {**cfg.mode_settings, "chaos.money_base": 100, "chaos.director.stages": "[[1, 0, 3, 99]]"}
    c = GameController(replace(cfg, enable_chaos=False, start_money=100, target_money=500, target_multiple=0.0,
                               exit_multiple=0.0, mode_settings=settings), save_fn=lambda d, n: n)
    c.choice = None
    c.table.loadout.core = core
    c.table.holdings = Holdings()
    c.table._sync_items()  # noqa: SLF001
    c.shop = c.table.roll_shop()
    return c, RunTracker(c)


def _deal(c, player, dealer, deck, bet=10):
    c.table.prepared = tuple(Card(Rank(x), "♠") for x in (*player, *dealer, *deck))
    c.table.prepared_round = c.run.round
    c.place_bet(bet)


def _item(c, name):
    c.table.holdings.add(name, 0)
    c.table._sync_items()  # noqa: SLF001


def test_the_tracker_counts_fourfold_wins_insurance_saves_and_fresh_hands_into_21():
    c, t = _table()
    _item(c, "ph_quad")
    c.use_item("ph_quad")
    _deal(c, ("5", "6"), ("10", "7"), ("10", "2"))
    c.double_down()
    c.finish_dealer()
    c.next_round()
    _item(c, "ph_insurance")
    _deal(c, ("10", "6"), ("10", "6"), ("K", "Q"))
    c.use_item("ph_insurance")
    c.hit()
    c.finish_dealer()
    c.next_round()
    _deal(c, ("10", "6"), ("10", "7"), ("A", "K", "5"))
    c.perform("ph_redeal")
    s = t.summary()
    assert (s["fourfold_wins"], s["insurance_saves"], s["fresh_21"], s["core"]) == (1, 1, 1, "ph_redeal")


def test_stats_read_the_new_counters():
    won = RunFacts("chaos", "victory", rounds=4, summary={"ceiling": 1, "core": "ph_margin", "after_relief": 1,
                                                          "fourfold_wins": 2})
    stats = run_stats(won)
    assert (stats["ceiling_wins"], stats["quick_hauls"], stats["comebacks"], stats["fourfold_wins"]) == (1, 1, 1, 2)
    assert stats["core_win_ph_margin"] == 1 and stats["core_win_ph_redeal"] == 0
    slow = run_stats(replace(won, rounds=12))
    lost = run_stats(replace(won, result="defeat"))
    assert slow["quick_hauls"] == 0 and lost["comebacks"] == 0 and lost["core_win_ph_margin"] == 0


def test_five_ways_needs_a_win_with_every_core():
    five = get_achievement("five_ways")
    totals = {f"core_win_{c}": 1 for c in CORES[:4]}
    assert five.progress(AchievementContext(totals=totals)) == (4, 5)
    totals[f"core_win_{CORES[4]}"] = 2
    assert five.progress(AchievementContext(totals=totals)) == (5, 5)


def test_every_new_achievement_pays_chips():
    rewards = {r.achievement_id: r.tokens for r in default_balance().achievement_rewards}
    for a in ("to_the_brim", "in_and_out", "all_in", "saved_by_the_bell", "fresh_start", "back_from_broke",
              "five_ways"):
        assert get_achievement(a) is not None and rewards[a] >= 100
