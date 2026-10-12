"""Achievements — goals over a player's stats that pay tokens and/or a cosmetic.

Most achievements are declarative: a stat (see `stats.py`), a goal and a
scope ("total": the lifetime sum; "run": the best single run). Anything else
uses `check(context) -> (progress, goal)`. Rewards are balance numbers
(`achievement_reward` rows). Evaluation and storage live in the meta service.
Contract: docs/design/COSMETICS_ACHIEVEMENTS.md §4.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from chaos_blackjack.achievements.stats import RunFacts, Stat, get_stat, register_stat, run_stats, stats

SCOPES = ("total", "run")


@dataclass(frozen=True)
class AchievementContext:
    totals: Mapping[str, int] = field(default_factory=dict)   # lifetime sums, current run included
    best: Mapping[str, int] = field(default_factory=dict)     # best single run per stat
    seen: Mapping[tuple[str, str], int] = field(default_factory=dict)  # codex_seen
    run: RunFacts | None = None                               # the run just settled; None when backfilling


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    icon: str = "achievement"     # asset id
    stat: str | None = None       # declarative: this stat ...
    goal: int = 1                 # ... reaches this goal
    scope: str = "total"          # total | run
    check: Callable[[AchievementContext], tuple[int, int]] | None = None   # custom: (progress, goal)
    hidden: bool = False          # shown as ??? until unlocked
    order: int = 0

    def progress(self, ctx: AchievementContext) -> tuple[int, int]:
        """(progress, goal); unlocked when progress >= goal. Progress is capped at the goal."""
        if self.check is not None:
            done, goal = self.check(ctx)
        else:
            values = ctx.totals if self.scope == "total" else ctx.best
            done, goal = values.get(self.stat or "", 0), self.goal
        return min(int(done), int(goal)), int(goal)


_ACHIEVEMENTS: dict[str, Achievement] = {}


def register_achievement(a: Achievement) -> Achievement:
    """Add or replace (same id) an achievement."""
    if (a.stat is None) == (a.check is None):
        raise ValueError(f"Achievement {a.id!r}: set exactly one of `stat` or `check`")
    if a.stat is not None and get_stat(a.stat) is None:
        raise ValueError(f"Achievement {a.id!r}: unknown stat {a.stat!r}")
    if a.scope not in SCOPES:
        raise ValueError(f"Achievement {a.id!r}: scope must be one of {', '.join(SCOPES)}")
    if a.goal < 1:
        raise ValueError(f"Achievement {a.id!r}: goal must be at least 1")
    _ACHIEVEMENTS[a.id] = a
    return a


def get_achievement(achievement_id: str) -> Achievement | None:
    return _ACHIEVEMENTS.get(achievement_id)


def achievements_catalog() -> list[Achievement]:
    return sorted(_ACHIEVEMENTS.values(), key=lambda a: (a.order, a.name, a.id))


from chaos_blackjack.achievements import catalog as _catalog  # noqa: E402,F401  (registers the built-ins)

__all__ = [
    "Achievement", "AchievementContext", "RunFacts", "SCOPES", "Stat", "achievements_catalog", "get_achievement",
    "get_stat", "register_achievement", "register_stat", "run_stats", "stats",
]
