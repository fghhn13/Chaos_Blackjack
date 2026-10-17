"""Onboarding milestones (docs/design/TUTORIAL.md).

A guided player (every player created since onboarding shipped) reaches these one by one; a player from
before it is not guided and counts as having reached all of them. Tables unlock through them
(GameMode.requires / reveal) and the first-time explanations show once each.
"""

from __future__ import annotations

import os
import sqlite3

TUTORIAL = "tutorial"                # finished or skipped the practice table
CLASSIC_MAX_WIN = "classic_max_win"  # won the Classic Table with its top stake: Poker Head's Table opens
POKER_HEAD_WIN = "poker_head_win"    # won Poker Head's Table: J-54's Table opens
PH_INTRO_BUILD = "ph_intro_build"    # heard how builds work at Poker Head's Table
PH_INTRO_RULES = "ph_intro_rules"    # heard how Poker Head's rules work
BET_CAP_LIFTED = "bet_cap_lifted"    # played enough Classic runs to bet freely
FIRST_RELIEF = "first_relief"        # heard Poker Head's first relief speech (later reliefs get a short one)
J54_SALE = "j54_sale"                # J-54's looks are sold (nothing reaches it while J-54's table is a demo)
# J-54's first visit, explained inside the first run (chaos_blackjack/j54/onboarding.py decides when).
J54_INTRO_TABLE = "j54_intro_table"          # the deck, the heat strip, compute and the two goals
J54_INTRO_FIRMWARE = "j54_intro_firmware"    # what a firmware is, as the choice opens
J54_INTRO_CONDITION = "j54_intro_condition"  # conditions and camps, at the first announcement
J54_INTRO_RELEASE = "j54_intro_release"      # the sealed Joker, once Release is affordable

ALL: tuple[str, ...] = (TUTORIAL, CLASSIC_MAX_WIN, POKER_HEAD_WIN, PH_INTRO_BUILD, PH_INTRO_RULES, BET_CAP_LIFTED,
                        FIRST_RELIEF, J54_SALE, J54_INTRO_TABLE, J54_INTRO_FIRMWARE, J54_INTRO_CONDITION,
                        J54_INTRO_RELEASE)

# A dealer's looks are sold once the player has reached this (series -> milestone, why not yet).
SALE_LOCKS: dict[str, tuple[str, str]] = {
    "poker_head": (POKER_HEAD_WIN, "Beat Poker Head's Table to buy this"),
    "j54": (J54_SALE, "Not sold yet"),
}

# A guided player's first Classic runs cap each bet at this share of the cash, so a new player cannot throw
# the whole stake on the first hands while learning (lifted after CAPPED_RUNS settled Classic runs).
CAPPED_RUNS = 3
CAP_FRACTION = 0.25


def guided_default() -> bool:
    """Whether a new player follows the onboarding (CHAOS_TUTORIAL=0 turns it off, e.g. for tests)."""
    return os.environ.get("CHAOS_TUTORIAL", "1") != "0"


def is_guided(db: sqlite3.Connection, player_id: int) -> bool:
    row = db.execute("SELECT guided FROM player WHERE id = ?", (player_id,)).fetchone()
    return bool(row and row["guided"])


def reached(db: sqlite3.Connection, player_id: int) -> frozenset[str]:
    """The milestones a player has reached (all of them for a player who is not guided)."""
    if not is_guided(db, player_id):
        return frozenset(ALL)
    return frozenset(r["milestone"] for r in db.execute(
        "SELECT milestone FROM player_milestone WHERE player_id = ?", (player_id,)))


def reach(db: sqlite3.Connection, player_id: int, milestone: str) -> bool:
    """Record a milestone; True when it is new (always False for a player who is not guided)."""
    if milestone not in ALL:
        raise ValueError(f"Unknown milestone {milestone!r}")
    if not is_guided(db, player_id):
        return False
    return db.execute("INSERT OR IGNORE INTO player_milestone (player_id, milestone) VALUES (?, ?)",
                      (player_id, milestone)).rowcount > 0


def sale_lock(series: str, reached: frozenset[str]) -> str:
    """Why a look of this series cannot be bought yet ("" = it can)."""
    milestone, reason = SALE_LOCKS.get(series, (None, ""))
    return "" if milestone is None or milestone in reached else reason


def after_run(db: sqlite3.Connection, player_id: int, mode: str, result: str, stake: int | None,
              top_stake: int | None) -> list[str]:
    """Milestones a settled run reaches, newly recorded, in order."""
    new = []
    if mode == "normal" and result == "victory" and stake is not None and top_stake is not None and stake >= top_stake:
        new.append(CLASSIC_MAX_WIN)
    if mode == "chaos" and result == "victory":
        new.append(POKER_HEAD_WIN)
    if mode == "normal":
        played = db.execute("SELECT COUNT(*) FROM run_history WHERE player_id = ? AND mode = 'normal' "
                            "AND result IN ('victory', 'defeat')", (player_id,)).fetchone()[0]
        if played >= CAPPED_RUNS:
            new.append(BET_CAP_LIFTED)
    return [m for m in new if reach(db, player_id, m)]


__all__ = ["ALL", "BET_CAP_LIFTED", "CAPPED_RUNS", "CAP_FRACTION", "CLASSIC_MAX_WIN", "FIRST_RELIEF", "PH_INTRO_BUILD",
           "J54_INTRO_CONDITION", "J54_INTRO_FIRMWARE", "J54_INTRO_RELEASE", "J54_INTRO_TABLE", "J54_SALE", "PH_INTRO_RULES", "POKER_HEAD_WIN", "SALE_LOCKS", "TUTORIAL", "after_run", "sale_lock", "guided_default", "is_guided", "reach",
           "reached"]
