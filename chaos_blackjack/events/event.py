"""Event definitions — all state changes are driven through events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Mapping


class EventType(Enum):
    """Extend with new gameplay actions without touching the dispatcher core."""

    TURN_START = auto()
    DRAW_CARD = auto()
    STAND = auto()
    DEALER_PLAY = auto()
    CHECK_BUST = auto()
    ROUND_END = auto()
    # Chaos / meta
    RULE_MODIFIER_APPLIED = auto()
    ITEM_USED = auto()
    CHAOS_ACTION_REJECTED = auto()


@dataclass(frozen=True)
class Event:
    """Immutable event with optional structured payload."""

    type: EventType
    payload: Mapping[str, Any] = field(default_factory=dict)
