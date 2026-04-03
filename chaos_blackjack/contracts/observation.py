"""Read-only view for chaos AI / pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from chaos_blackjack.core.game_state import GameState
from chaos_blackjack.rules.modifiers import ActiveModifiers


@dataclass(frozen=True)
class ChaosObservation:
    state: GameState
    modifiers: ActiveModifiers
    chaos_budget_remaining: int = 999
    chaos_actions_this_turn: int = 0
    last_event_summary: str | None = None
