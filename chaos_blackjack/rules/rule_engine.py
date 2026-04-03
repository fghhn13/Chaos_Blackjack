"""Laws of the game — separate from state and from AI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from chaos_blackjack.core.game_state import Card, GameState
from chaos_blackjack.rules.modifiers import ActiveModifiers


@dataclass(frozen=True)
class RuleContext:
    """Everything the rule engine needs besides raw state."""

    modifiers: ActiveModifiers


@runtime_checkable
class RuleEngine(Protocol):
    def hand_value(self, hand: tuple[Card, ...], ctx: RuleContext) -> int:
        ...

    def is_bust(self, value: int) -> bool:
        ...

    def compare_player_dealer(
        self,
        state: GameState,
        ctx: RuleContext,
    ) -> str:
        """Return 'player', 'dealer', 'push', or custom outcome keys."""
        ...


class DefaultBlackjackRules:
    """Standard blackjack value rules; modifiers apply per-card before summing."""

    def _card_base_value(self, card: Card) -> int:
        r = card.rank.upper()
        if r in ("J", "Q", "K", "10"):
            return 10
        if r == "A":
            return 11
        return int(r)

    def hand_value(self, hand: tuple[Card, ...], ctx: RuleContext) -> int:
        total = 0
        aces_as_eleven = 0
        for card in hand:
            base = self._card_base_value(card)
            v = base
            for m in ctx.modifiers.items:
                v = m.adjust_rank_value(card, v)
            if card.rank.upper() == "A" and v == 11:
                aces_as_eleven += 1
            total += v
        while total > 21 and aces_as_eleven > 0:
            total -= 10
            aces_as_eleven -= 1
        return total

    def is_bust(self, value: int) -> bool:
        return value > 21

    def compare_player_dealer(self, state: GameState, ctx: RuleContext) -> str:
        pv = self.hand_value(state.player_hand, ctx)
        dv = self.hand_value(state.dealer_hand, ctx)
        pb = self.is_bust(pv)
        db = self.is_bust(dv)
        if pb and db:
            return "push"
        if pb:
            return "dealer"
        if db:
            return "player"
        if pv > dv:
            return "player"
        if dv > pv:
            return "dealer"
        return "push"
