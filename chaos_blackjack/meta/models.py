"""Meta progression data passed to front-ends (immutable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController

SLOTS = (1, 2, 3)
MAX_NAME_LENGTH = 24


class MetaError(ValueError):
    """A meta action is not allowed; `str(e)` is a player-readable reason."""


@dataclass(frozen=True)
class PlayerStats:
    runs: int = 0
    victories: int = 0
    defeats: int = 0
    abandoned: int = 0
    best_money: int = 0
    tokens_earned: int = 0


@dataclass(frozen=True)
class Player:
    id: int
    slot: int
    name: str
    tokens: int
    upgrades: dict[str, int]          # permanent: level; consumable: copies held
    stats: PlayerStats
    created_at: str = ""
    last_played_at: str | None = None


@dataclass(frozen=True)
class PlayerSlot:
    slot: int
    player: Player | None


@dataclass(frozen=True)
class UpgradeOffer:
    upgrade_id: str
    name: str
    description: str                  # what the next level / one copy does
    kind: str                         # permanent | consumable
    owned: int                        # level or copies held
    max_level: int
    next_cost: int | None             # None when maxed
    can_buy: bool
    reason: str = ""                  # why not, when can_buy is False


@dataclass(frozen=True)
class RunStart:
    run_id: int
    mode: str
    config: "RunConfig"
    applied: dict[str, int]           # upgrade id -> level / copies used
    controller: "GameController"


@dataclass(frozen=True)
class PendingRun:
    """An unfinished run's save, summarised without loading it."""

    run_id: int
    mode: str
    round: int
    money: int
    updated_at: str


@dataclass(frozen=True)
class RunReward:
    tokens: int
    breakdown: tuple[tuple[str, int], ...]   # (label, tokens)
    result: str                              # victory | defeat
    player: Player


@dataclass(frozen=True)
class RunRecord:
    id: int
    started_at: str
    ended_at: str | None
    mode: str
    result: str | None
    rounds: int | None
    final_money: int | None
    peak_money: int | None
    tokens_earned: int | None
    balance_profile: str | None
    upgrades: dict[str, int] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
