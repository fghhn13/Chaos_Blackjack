"""Game modes — what a run is set up as, chosen when starting it.

    register_mode(GameMode("speed", "Speed", "...", icon="mode_speed",
                           overrides={"target_money": 300}, unlocked_by="unlock_speed"))

`overrides` are RunConfig fields. A mode with `unlocked_by` needs that meta
upgrade (effect `unlock_mode`); `None` means always available.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

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

    def apply(self, config: "RunConfig") -> "RunConfig":
        return replace(config, **self.overrides)


_MODES: dict[str, GameMode] = {}


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


register_mode(GameMode(
    "normal", "Classic", "Plain blackjack with the shop. The Chaos AI stays out of it.",
    icon="mode_normal", overrides={"enable_chaos": False}, order=0,
))
register_mode(GameMode(
    "chaos", "Chaos", "The Chaos AI may bend one rule every round.",
    icon="mode_chaos", overrides={"enable_chaos": True}, order=1,
))

__all__ = ["GameMode", "get_mode", "modes", "register_mode"]
