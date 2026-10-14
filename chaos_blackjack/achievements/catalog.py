"""Built-in achievements. Rewards: `achievement_reward` rows in
data/seed/default.sql (an achievement without a row pays nothing).

Most entries are one line: a stat, a goal and a scope ("total" over all runs,
or "run" for one run). Use `check` only when no stat fits.
"""

from __future__ import annotations

from dataclasses import replace

from chaos_blackjack.achievements import Achievement, AchievementContext, register_achievement
from chaos_blackjack.achievements.stats import CORES

RULE_SCHOLAR_GOAL = 5


def _rules_seen(ctx: AchievementContext) -> tuple[int, int]:
    return sum(1 for kind, _ in ctx.seen if kind == "rule"), RULE_SCHOLAR_GOAL


def _core_wins(ctx: AchievementContext) -> tuple[int, int]:
    return sum(1 for core in CORES if ctx.totals.get(f"core_win_{core}", 0) > 0), len(CORES)


for _order, _a in enumerate((
    Achievement("first_win", "First Win", "Win a run.", stat="victories"),
    Achievement("chaos_conqueror", "Poker Face", "Win a run against Poker Head.", stat="victories_chaos"),
    Achievement("bare_hands", "Bare Hands", "Win a run without using an item.", stat="item_free_victories"),
    Achievement("regular", "Regular", "Finish 10 runs.", stat="runs", goal=10),
    Achievement("marathon", "Marathon", "Play 250 rounds.", stat="rounds", goal=250),
    Achievement("natural_talent", "Natural Talent", "Get 3 blackjacks in one run.",
                stat="blackjacks", goal=3, scope="run"),
    Achievement("blackjack_collector", "Blackjack Collector", "Get 50 blackjacks.", stat="blackjacks", goal=50),
    Achievement("hot_streak", "Hot Streak", "Win 5 hands in a row.", stat="win_streak", goal=5, scope="run"),
    Achievement("five_card_trick", "Five Card Trick", "Win a hand holding five or more cards.",
                stat="five_card_hands"),
    Achievement("double_trouble", "Double Trouble", "Double down 25 times.", stat="doubles", goal=25),
    Achievement("hundred_hands", "Hundred Hands", "Win 100 hands.", stat="hands_won", goal=100),
    Achievement("rule_scholar", "Rule Scholar", f"Meet {RULE_SCHOLAR_GOAL} different Chaos rules.",
                check=_rules_seen),
    Achievement("white_flag", "White Flag", "Surrender 30 times.", stat="surrenders", goal=30, hidden=True),
    # The chip economy and the build table: risky play counts as a way to play too.
    Achievement("to_the_brim", "To the Brim", "Win a run by reaching the table's ceiling.", stat="ceiling_wins"),
    Achievement("in_and_out", "In and Out", "Win at Poker Head's table within 5 rounds.", stat="quick_hauls"),
    Achievement("all_in", "All In", "Win a hand with a Fourfold Ticket.", stat="fourfold_wins"),
    Achievement("saved_by_the_bell", "Saved by the Bell", "Turn a bust into a push with Bust Insurance.",
                stat="insurance_saves"),
    Achievement("fresh_start", "Fresh Start", "Swap into 21 with Fresh Hand.", stat="fresh_21"),
    Achievement("back_from_broke", "Back from Broke", "Win at Poker Head's table after taking his relief.",
                stat="comebacks"),
    Achievement("five_ways", "Five Ways to Win", "Win at Poker Head's table with each of the five cores.",
                check=_core_wins),
)):
    register_achievement(replace(_a, order=_order))
