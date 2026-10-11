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


BLACKJACK = 21


def bust_limit(ctx: RuleContext) -> int:
    """Highest total that is not a bust: 21, or lower while a modifier sets
    `bust_limit` (e.g. Fragile Bust)."""
    limits = [m.bust_limit for m in ctx.modifiers.items if getattr(m, "bust_limit", None) is not None]
    return min([BLACKJACK, *limits])


@runtime_checkable
class RuleEngine(Protocol):
    def hand_value(self, hand: tuple[Card, ...], ctx: RuleContext) -> int:
        ...

    def is_bust(self, value: int, ctx: RuleContext) -> bool:
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
        """Sum of card values after modifiers.

        An Ace counts high (11 + modifiers) and can drop by 10 to its low value
        (1 + the same modifiers) whenever the hand would otherwise bust under
        the active bust rule — so value shifts move both of its values instead
        of freezing it (e.g. "values -1": Ace is 10 or 0).
        """
        total = 0
        soft_aces = 0
        for card in hand:
            v = self._card_base_value(card)
            for m in ctx.modifiers.items:
                v = m.adjust_rank_value(card, v)
            if card.rank.upper() == "A":
                soft_aces += 1
            total += v
        while soft_aces > 0 and self.is_bust(total, ctx):
            total -= 10
            soft_aces -= 1
        return total

    def is_bust(self, value: int, ctx: RuleContext) -> bool:
        return value > bust_limit(ctx)

    def compare_player_dealer(self, state: GameState, ctx: RuleContext) -> str:
        pv = self.hand_value(state.player_hand, ctx)
        dv = self.hand_value(state.dealer_hand, ctx)
        pb = self.is_bust(pv, ctx)
        if pb and "reverse_bust" in ctx.modifiers.chaos_flags():
            return "push"  # Reverse Bust: a player bust is a draw instead of a loss
        db = self.is_bust(dv, ctx)
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
        flags = ctx.modifiers.chaos_flags()
        if "player_wins_ties" in flags:
            return "player"
        if "dealer_wins_ties" in flags:
            return "dealer"
        return "push"
