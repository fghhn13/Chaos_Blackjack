"""Poker Head's public table snapshot — what any player at the table may see.

Built fresh by `PokerHeadTable.public()`; frozen, so a view never changes the
table and later table changes never reach an old view. It never holds the
frozen deal or a stock's private outcome. Parts (parts.py) and the agent
observation read only this.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EntryView:
    id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class PositionView:
    id: str
    name: str
    principal: int
    debt: int
    remaining: int    # rounds until maturity
    wins: int


@dataclass(frozen=True)
class PokerHeadPublic:
    core: EntryView | None
    no_core: bool
    slots: int
    equipped: tuple[EntryView, ...]
    cash: int
    invested: int
    debt: int
    net_assets: int
    target: int
    positions: tuple[PositionView, ...]
    preparations: tuple[EntryView, ...]   # consumables prepared for this round
    forecast: tuple[str, ...]             # Fate Forecast's cards, as shown when used
    forecast_changed: bool                # a card effect moved the deck since
    next_rank: str                        # a rank revealed by Card Lens or Sleeve Mark ("" = none)
    claim_refund: int                     # Recovery Receipt: chips a win next round returns (0 = none)
    claim_round: int
    ace_armed: bool                       # Comeback Ace sets the next opening card
    min_bet: int
    rule_slots: int
    dealer_stage: str = ""                # the director's stage (Probing, Pressure, Control, Onslaught)
    dealer_slots: int = 0                 # rules the dealer may keep at this stage
    kind: str = "poker_head"

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON data (lists, not tuples), detached from the snapshot."""
        return json.loads(json.dumps(asdict(self)))
