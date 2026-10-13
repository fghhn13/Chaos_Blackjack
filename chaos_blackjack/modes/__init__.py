"""Game modes — what a run is set up as, chosen when starting it.

Each mode is hosted by one Chaos AI and has its own rule pool, item pool and
goal (docs/design/AI_MODES.md):

    register_mode(GameMode("speed", "Speed", "...", icon="mode_speed", host="poker_head",
                           overrides={"target_money": 300}, rules=("great_crash",),
                           items=("peek", "shield"), intro=("Quick hands tonight.",)))

`overrides` are RunConfig fields. A mode with `unlocked_by` needs that meta
upgrade (effect `unlock_mode`); `None` means always available.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from chaos_blackjack.content.host_script import HostLine, host_script, summary_mood

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig


@dataclass(frozen=True)
class GameMode:
    id: str
    name: str
    description: str
    icon: str = ""                      # asset id
    overrides: dict[str, Any] = field(default_factory=dict)
    unlocked_by: str | None = None      # meta upgrade id, or None = always available
    order: int = 0
    host: str = "poker_head"            # who presents the table: a bundled host id
    series: str = "core"                # "core", or the expansion it belongs to (see register_series)
    ai_id: str = "default"              # Chaos AI pipeline (registry id)
    rules: tuple[str, ...] | None = None    # Chaos rule pool; None = every rule the profile enables
    items: tuple[str, ...] | None = None    # shop item pool; None = every item the profile sells
    intro: tuple[str, ...] = ()         # fallback greeting when the host has no line library
    # The rules and items of this mode's pools belong to it alone: modes without
    # a pool ("all") do not get them (e.g. J-54's deck rules and contracts).
    exclusive: bool = False

    def apply(self, config: "RunConfig") -> "RunConfig":
        """The run's config in this mode: goal overrides, host, AI and pools."""
        # "<mode id>.config.<field>" balance settings override RunConfig fields at this table.
        prefix = f"{self.id}.config."
        tuned = {k[len(prefix):]: v for k, v in config.mode_settings.items() if k.startswith(prefix)}
        config = replace(config, **{**tuned, **self.overrides})
        values: dict[str, Any] = {"mode": self.id, "host": self.host}
        if self.ai_id != "default":
            values["ai_id"] = self.ai_id
        if self.rules is not None:
            pool = tuple(self.rules)
            values["rule_pool"] = pool
            values["chaos_stub"] = tuple(c for c in config.chaos_stub if c[0] in pool or c[0] == "")
        else:
            claimed = _claimed(self.id, "rules")
            values["chaos_stub"] = tuple(c for c in config.chaos_stub if c[0] not in claimed)
            values["disabled_rules"] = tuple(sorted({*config.disabled_rules, *claimed}))
        if self.items is not None:
            values["shop_prices"] = {k: v for k, v in config.shop_prices.items() if k in self.items}
        else:
            claimed = _claimed(self.id, "items")
            values["shop_prices"] = {k: v for k, v in config.shop_prices.items() if k not in claimed}
        return replace(config, **values)


# Player-facing label of the expansion group in the Collection and the Shop.
EXPANSIONS_LABEL = "Dealers"


@dataclass(frozen=True)
class Series:
    """A collection of tables: the Classic Table (core), or an expansion named
    after its dealer (e.g. Poker Head). The Collection and the Shop are grouped
    by series."""

    id: str
    name: str
    expansion: bool = True
    order: int = 0


_MODES: dict[str, GameMode] = {}
_SERIES: dict[str, Series] = {}


def register_series(series: Series) -> Series:
    _SERIES[series.id] = series
    return series


def get_series(series_id: str) -> Series:
    """A registered series; an unknown id becomes an expansion named after it."""
    return _SERIES.get(series_id) or Series(series_id, series_id.replace("_", " ").title(), True, 99)


def series_list() -> list[Series]:
    """Core first, then expansions (only series that have a mode)."""
    used = {m.series for m in _MODES.values()} | {"core"}
    return sorted((get_series(s) for s in used), key=lambda s: (s.expansion, s.order, s.name))


def _claimed(mode_id: str, pool: str) -> frozenset[str]:
    """Rule or item ids that other exclusive modes keep to themselves."""
    return frozenset(i for m in _MODES.values() if m.exclusive and m.id != mode_id for i in getattr(m, pool) or ())


def register_mode(mode: GameMode) -> GameMode:
    _MODES[mode.id] = mode
    return mode


def get_mode(mode_id: str) -> GameMode:
    try:
        return _MODES[mode_id]
    except KeyError:
        raise KeyError(f"Unknown game mode {mode_id!r}; known: {', '.join(_MODES)}") from None


def modes() -> list[GameMode]:
    return sorted(_MODES.values(), key=lambda m: (m.order, m.id))


def sold_items(config: "RunConfig") -> set[str]:
    """Items a table with this config can stock (Classic never sells Shield)."""
    return {item for item in config.shop_prices if item != "shield" or config.enable_chaos}


def item_series(item_id: str, config: "RunConfig") -> str:
    """The series an item belongs to: "core" when a core table sells it (or no
    table does), else the first expansion whose tables sell it."""
    selling = [m.series for m in modes() if item_id in sold_items(m.apply(config))]
    if not selling or "core" in selling:
        return "core"
    return min(selling, key=lambda s: (get_series(s).order, s))


def _title(rule_id: str) -> str:
    return rule_id.replace("_", " ").title()


def intro_script(mode: GameMode, config: "RunConfig", rng: random.Random | None = None, *,
                 summary: list[str] | None = None) -> list[HostLine]:
    """What the host says before the first round: a random greeting from the
    host's line library (or the mode's `intro`), then the goal and what may
    change, generated from the run's config (or `summary`, a table's own goal)."""
    host = config.host or mode.host
    mood = summary_mood(host)
    greeting = host_script(host, "intro", rng, mode=mode.id) or [HostLine(mood, text) for text in mode.intro]
    return greeting + [HostLine(mood, text) for text in (summary or rules_summary(config))]


def intro_lines(mode: GameMode, config: "RunConfig", rng: random.Random | None = None) -> list[str]:
    """The text of `intro_script`."""
    return [line.text for line in intro_script(mode, config, rng)]


def rules_summary(config: "RunConfig") -> list[str]:
    """The run's goal and which rules may change, in the host's words (a table
    with its own goal, like J-54's protocols, says its own; see TableMechanics.summary)."""
    goal = f"Reach {config.target_money} chips from {config.start_money} and the table is yours."
    if not config.enable_chaos:
        return [f"{goal} No rule changes here; the shop opens between hands."]
    pool = sorted(rid for rid, _, weight in config.chaos_stub if rid and weight > 0)
    if config.rule_pool is not None:
        pool = [r for r in pool if r in config.rule_pool]
    if not pool:
        bend = "I may bend a rule before each hand."
    elif len(pool) <= 3:
        bend = "I may bend a rule before each hand: " + ", ".join(_title(r) for r in pool) + "."
    else:
        shown = ", ".join(_title(r) for r in pool[:2])
        bend = f"I may bend a rule before each hand: {shown} and {len(pool) - 2} more."
    return [f"{goal} {bend}"]


register_series(Series("core", "Classic Table", expansion=False, order=0))
register_series(Series("poker_head", "Poker Head", expansion=True, order=1))
register_series(Series("j54", "J-54", expansion=True, order=2))

register_mode(GameMode(
    "normal", "Classic Table",
    "Poker Head deals by the book and the rules never change. Know your blackjack and win each hand on judgement.",
    icon="mode_normal", overrides={"enable_chaos": False}, order=0, host="poker_head", rules=(), series="core",
))
register_mode(GameMode(
    "chaos", "Poker Head's Table",
    "Familiar blackjack, with a dealer fond of small adjustments. Watch the rule change announced each round "
    "and adapt your strategy.",
    icon="mode_poker_head", overrides={"enable_chaos": True}, order=1, host="poker_head", series="poker_head",
))
# Demo of the deck-rebuilding table (docs/design/J54_TABLE.md); its mechanics are chaos_blackjack/j54.
J54_RULES = ("j54_burn", "j54_sample_injection", "j54_redundancy_purge", "j54_ace_injection")
J54_CONTRACTS = ("j54_streamline", "j54_low_purge", "j54_high_injection", "j54_freeze", "j54_start_experiment")
register_mode(GameMode(
    "j54", "J-54's Table (demo)",
    "J-54 does not bend the rules; it rewrites the deck, and the deck lasts the whole run. Sign contracts to "
    "reshape it, pay the compute fee each round and complete the protocol before the deck turns against you.",
    icon="mode_j54", overrides={"enable_chaos": True}, order=2, host="j54", series="j54",
    rules=J54_RULES, items=J54_CONTRACTS, exclusive=True,
))

__all__ = [
    "EXPANSIONS_LABEL", "GameMode", "Series", "get_mode", "get_series", "intro_lines", "intro_script", "item_series", "modes",
    "register_mode", "register_series", "rules_summary", "series_list", "sold_items",
]
