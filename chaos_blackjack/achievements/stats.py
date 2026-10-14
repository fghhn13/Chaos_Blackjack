"""Stats — named numbers taken from one settled run.

Each player keeps, per stat, the lifetime `total` (sum over settled runs) and
the `best` single run. Achievements compare one of the two with a goal.
A new stat is one `register_stat`; if the run summary lacks the number, add a
counter to `chaos_blackjack.meta.tracker.RunTracker` first.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunFacts:
    """A settled run (victory or defeat), as stats see it."""

    mode: str
    result: str                    # victory | defeat
    rounds: int = 0
    peak_money: int = 0
    final_money: int = 0
    summary: Mapping[str, Any] = field(default_factory=dict)   # META_PROGRESSION.md §5.3

    def count(self, key: str) -> int:
        """A summary counter, or the sum of a {id: count} summary map; 0 when absent."""
        value = self.summary.get(key, 0)
        if isinstance(value, Mapping):
            return sum(int(v) for v in value.values())
        return int(value or 0)


@dataclass(frozen=True)
class Stat:
    id: str
    label: str
    from_run: Callable[[RunFacts], int]


_STATS: dict[str, Stat] = {}


def register_stat(s: Stat) -> Stat:
    _STATS[s.id] = s
    return s


def get_stat(stat_id: str) -> Stat | None:
    return _STATS.get(stat_id)


def stats() -> list[Stat]:
    return sorted(_STATS.values(), key=lambda s: s.id)


def run_stats(run: RunFacts) -> dict[str, int]:
    """Every registered stat's value for one run."""
    return {s.id: int(s.from_run(run)) for s in _STATS.values()}


def _won(run: RunFacts) -> bool:
    return run.result == "victory"


for _s in (
    Stat("runs", "Runs finished", lambda r: 1),
    Stat("victories", "Runs won", lambda r: int(_won(r))),
    Stat("victories_normal", "Classic runs won", lambda r: int(_won(r) and r.mode == "normal")),
    Stat("victories_chaos", "Poker Head runs won", lambda r: int(_won(r) and r.mode == "chaos")),
    Stat("item_free_victories", "Runs won without using an item",
         lambda r: int(_won(r) and r.count("items_used") == 0)),
    Stat("rounds", "Rounds played", lambda r: r.rounds),
    Stat("peak_money", "Peak bankroll", lambda r: r.peak_money),
    Stat("hands_won", "Hands won", lambda r: r.count("hands_won")),
    Stat("blackjacks", "Blackjacks", lambda r: r.count("blackjacks")),
    Stat("doubles", "Doubles", lambda r: r.count("doubles")),
    Stat("surrenders", "Surrenders", lambda r: r.count("surrenders")),
    Stat("five_card_hands", "Hands won with five or more cards", lambda r: r.count("five_card_hands")),
    Stat("win_streak", "Longest win streak", lambda r: r.count("win_streak")),
    Stat("items_used", "Items used", lambda r: r.count("items_used")),
    Stat("items_bought", "Items bought", lambda r: r.count("items_bought")),
    # The chip economy and Poker Head's build table (docs/design/CARRIED_CHIPS.zh-CN.md).
    Stat("ceiling_wins", "Runs won at the table's ceiling", lambda r: int(_won(r) and r.count("ceiling") > 0)),
    Stat("quick_hauls", "Poker Head runs won within 5 rounds",
         lambda r: int(_won(r) and r.mode == "chaos" and 0 < r.rounds <= 5)),
    Stat("fourfold_wins", "Hands won with a Fourfold Ticket", lambda r: r.count("fourfold_wins")),
    Stat("insurance_saves", "Busts saved by Bust Insurance", lambda r: r.count("insurance_saves")),
    Stat("fresh_21", "Fresh Hands into 21", lambda r: r.count("fresh_21")),
    Stat("comebacks", "Poker Head runs won after Poker Head's relief",
         lambda r: int(_won(r) and r.mode == "chaos" and bool(r.summary.get("after_relief")))),
):
    register_stat(_s)

# One stat per Poker Head core: runs won with it (Five Ways to Win).
CORES = ("ph_margin", "ph_late_retreat", "ph_redeal", "ph_late_double", "ph_account")
for _core in CORES:
    register_stat(Stat(f"core_win_{_core}", f"Poker Head runs won with {_core}",
                       lambda r, core=_core: int(_won(r) and r.mode == "chaos" and r.summary.get("core") == core)))
