"""Item: Hole Card Hacker — reveal dealer's hidden (hole) card."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class HoleCardHacker:
    name = "hole_card_hacker"

    def use(self, ctx: ItemContext) -> ItemResult:
        # Dealer's first card is visible; second card (index 1) is the hole card.
        if len(ctx.state.dealer_hand) < 2:
            return ItemResult(ok=False, message="Dealer hole card not available")

        hole_rank = ctx.state.dealer_hand[1].rank
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {
                    "item": self.name,
                    "hole_rank": hole_rank,
                    "dealer_visible_rank": ctx.state.dealer_hand[0].rank
                    if ctx.state.dealer_hand
                    else None,
                },
            ),
        )
        return ItemResult(ok=True, message=f"Dealer hole card: {hole_rank}")


register_item(HoleCardHacker.name, HoleCardHacker)

