"""Cosmetics, lifetime stats and achievements on the game database.

Helpers for MetaService; each takes an open connection and leaves transactions
to the caller. Contract: docs/design/COSMETICS_ACHIEVEMENTS.md.
"""

from __future__ import annotations

import json
import sqlite3

from chaos_blackjack.achievements import AchievementContext, RunFacts, achievements_catalog, run_stats
from chaos_blackjack.cosmetics import COSMETIC_SLOTS, Cosmetic, default_cosmetic, get_cosmetic
from chaos_blackjack.data.balance import Balance
from chaos_blackjack.meta.models import Unlock

SETTLED = ("victory", "defeat")


# --------------------------------------------------------------- cosmetics

def owned_cosmetics(db: sqlite3.Connection, player_id: int) -> dict[str, str]:
    """{cosmetic_id: source} stored for the player (defaults are owned implicitly)."""
    return {r["cosmetic_id"]: r["source"] for r in db.execute(
        "SELECT cosmetic_id, source FROM player_cosmetic WHERE player_id = ?", (player_id,))}


def owns(db: sqlite3.Connection, player_id: int, c: Cosmetic) -> bool:
    return c.default or db.execute(
        "SELECT 1 FROM player_cosmetic WHERE player_id = ? AND cosmetic_id = ?", (player_id, c.id)
    ).fetchone() is not None


def add_cosmetic(db: sqlite3.Connection, player_id: int, cosmetic_id: str, source: str) -> bool:
    """Give a cosmetic; False when it is unknown or already owned."""
    c = get_cosmetic(cosmetic_id)
    if c is None or c.default:
        return False
    cur = db.execute("INSERT OR IGNORE INTO player_cosmetic (player_id, cosmetic_id, source) VALUES (?, ?, ?)",
                     (player_id, cosmetic_id, source))
    return cur.rowcount > 0


def loadout(db: sqlite3.Connection, player_id: int) -> dict[str, Cosmetic]:
    """Equipped cosmetic per slot; unknown, unowned or missing entries show the default."""
    out = {slot: default_cosmetic(slot) for slot in COSMETIC_SLOTS}
    owned = owned_cosmetics(db, player_id)
    for r in db.execute("SELECT slot, cosmetic_id FROM player_loadout WHERE player_id = ?", (player_id,)):
        c = get_cosmetic(r["cosmetic_id"])
        if c is not None and c.slot == r["slot"] and (c.default or c.id in owned):
            out[c.slot] = c
    return out


def asset_aliases(equipped: dict[str, Cosmetic]) -> dict[str, str]:
    """Base asset id -> asset id for the equipped looks (identity entries left out)."""
    return {base: asset for c in equipped.values() for base, asset in c.asset_map().items() if base != asset}


# ------------------------------------------------------------------- stats

def stat_values(db: sqlite3.Connection, player_id: int) -> tuple[dict[str, int], dict[str, int]]:
    """(totals, best) per stat id."""
    rows = db.execute("SELECT stat_id, total, best FROM player_stat WHERE player_id = ?", (player_id,)).fetchall()
    return {r["stat_id"]: r["total"] for r in rows}, {r["stat_id"]: r["best"] for r in rows}


def fold_run(db: sqlite3.Connection, player_id: int, run: RunFacts) -> None:
    """Add one settled run to the player's lifetime stats."""
    for stat_id, value in run_stats(run).items():
        db.execute(
            "INSERT INTO player_stat (player_id, stat_id, total, best) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(player_id, stat_id) DO UPDATE SET total = total + excluded.total, "
            "best = MAX(best, excluded.best)",
            (player_id, stat_id, value, value),
        )


def facts(row: sqlite3.Row, summary: dict | None = None) -> RunFacts:
    """RunFacts from a run_history row (with its summary unless one is given)."""
    if summary is None:
        summary = json.loads(row["summary"] or "{}")
    return RunFacts(row["mode"], row["result"], int(row["rounds"] or 0), int(row["peak_money"] or 0),
                    int(row["final_money"] or 0), summary)


def needs_backfill(db: sqlite3.Connection, player_id: int) -> bool:
    """Settled runs exist but no stats: the player predates stats (migration 0006)."""
    if db.execute("SELECT 1 FROM player_stat WHERE player_id = ? LIMIT 1", (player_id,)).fetchone():
        return False
    return db.execute(
        "SELECT 1 FROM run_history WHERE player_id = ? AND result IN (?, ?) LIMIT 1", (player_id, *SETTLED)
    ).fetchone() is not None


def backfill(db: sqlite3.Connection, player_id: int, balance: Balance) -> list[Unlock]:
    """Rebuild stats from run history once, then unlock (and pay) what they reach."""
    if not needs_backfill(db, player_id):
        return []
    for row in db.execute("SELECT * FROM run_history WHERE player_id = ? AND result IN (?, ?) ORDER BY id",
                          (player_id, *SETTLED)).fetchall():
        fold_run(db, player_id, facts(row))
    return evaluate(db, player_id, balance)


# ------------------------------------------------------------ achievements

def seen(db: sqlite3.Connection, player_id: int) -> dict[tuple[str, str], int]:
    return {(r["kind"], r["entry_id"]): r["times"] for r in db.execute(
        "SELECT kind, entry_id, times FROM codex_seen WHERE player_id = ?", (player_id,))}


def context(db: sqlite3.Connection, player_id: int, run: RunFacts | None = None) -> AchievementContext:
    totals, best = stat_values(db, player_id)
    return AchievementContext(totals, best, seen(db, player_id), run)


def unlocked(db: sqlite3.Connection, player_id: int) -> dict[str, str]:
    """{achievement_id: unlocked_at}."""
    return {r["achievement_id"]: r["unlocked_at"] for r in db.execute(
        "SELECT achievement_id, unlocked_at FROM player_achievement WHERE player_id = ?", (player_id,))}


def evaluate(db: sqlite3.Connection, player_id: int, balance: Balance, run: RunFacts | None = None,
             run_id: int | None = None) -> list[Unlock]:
    """Unlock every achievement the player's stats now reach and pay its reward."""
    ctx = context(db, player_id, run)
    done = unlocked(db, player_id)
    rewards = {r.achievement_id: r for r in balance.achievement_rewards}
    out: list[Unlock] = []
    for a in achievements_catalog():
        if a.id in done:
            continue
        progress, goal = a.progress(ctx)
        if progress < goal:
            continue
        db.execute("INSERT INTO player_achievement (player_id, achievement_id, run_id) VALUES (?, ?, ?)",
                   (player_id, a.id, run_id))
        reward = rewards.get(a.id)
        tokens = reward.tokens if reward else 0
        if tokens:
            db.execute("UPDATE player SET tokens = tokens + ? WHERE id = ?", (tokens, player_id))
        # Unknown or already owned looks are left out: nothing new to show.
        new = tuple(c for c in (reward.cosmetic_ids if reward else ())
                    if add_cosmetic(db, player_id, c, f"achievement:{a.id}"))
        out.append(Unlock(a.id, a.name, tokens, new))
    return out
