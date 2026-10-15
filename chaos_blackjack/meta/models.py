"""Meta progression data passed to front-ends (immutable)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chaos_blackjack.achievements import Achievement
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.cosmetics import Cosmetic

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
    avatar: str = "avatar"            # asset id of the equipped avatar
    relief_streak: int = 0            # Poker Head's reliefs since the last won run
    lifetime_spend: int = 0           # chips spent on goods (the membership level reads it)
    guided: bool = False              # follows the onboarding (meta/onboarding.py; older players do not)

    @property
    def chips(self) -> int:
        """The chip vault (stored as `tokens`; docs/design/META_PROGRESSION.md "Chip vault")."""
        return self.tokens


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
    mode: str | None = None           # only in this game mode; None = every mode


@dataclass(frozen=True)
class RunStart:
    run_id: int
    mode: str
    config: "RunConfig"
    applied: dict[str, int]           # upgrade id -> level / copies used
    controller: "GameController"
    notes: tuple[str, ...] = ()       # what the host adds before the first hand (e.g. a new player's bet cap)


@dataclass(frozen=True)
class PendingRun:
    """An unfinished run's save, summarised without loading it."""

    run_id: int
    mode: str
    round: int
    money: int
    updated_at: str


@dataclass(frozen=True)
class Unlock:
    """An achievement unlocked by a run (or by backfilling old runs) and what it paid."""

    achievement_id: str
    name: str
    tokens: int
    cosmetic_ids: tuple[str, ...] = ()     # newly owned looks (already owned ones left out)


@dataclass(frozen=True)
class RunReward:
    tokens: int                              # the vault's change at settling (chips)
    breakdown: tuple[tuple[str, int], ...]   # (label, chips): brought home, debt, achievements, relief
    result: str                              # victory | defeat
    player: Player
    unlocked: tuple[Unlock, ...] = ()
    milestones: tuple[str, ...] = ()         # onboarding milestones this run reached (meta/onboarding.py)


@dataclass(frozen=True)
class CosmeticOffer:
    cosmetic: "Cosmetic"
    owned: bool
    equipped: bool
    price: int | None                 # None: not sold
    can_buy: bool
    reason: str = ""                  # why it cannot be bought (when not owned)
    unlock_hint: str = ""             # how to get it, e.g. "Achievement: First Win" or "40 chips"


@dataclass(frozen=True)
class AchievementState:
    achievement: "Achievement"
    unlocked: bool
    unlocked_at: str | None
    progress: int
    goal: int
    reward_tokens: int = 0
    reward_cosmetics: tuple[str, ...] = ()


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
