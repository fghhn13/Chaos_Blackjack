"""Item: Fate Oracle — peek the top cards of the deck (3 by default).

Params: `cards` (balance profile).
"""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class FateOracle:
    name = "fate_oracle"
    description = "Reveal the ranks of the next 3 cards in the deck."

    def use(self, ctx: ItemContext) -> ItemResult:
        if not ctx.state.deck:
            return ItemResult(ok=False, message="Deck is empty")

        n = max(1, int(ctx.params.get("cards", 3)))
        ranks = [c.rank for c in ctx.state.deck[:n]]
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {
                    "item": self.name,
                    "peeked_ranks": ranks,
                },
            ),
        )
        shown = ", ".join(str(r) for r in ranks)
        return ItemResult(ok=True, message=f"Next {len(ranks)} cards: {shown} (Fate Oracle)")


register_item(FateOracle.name, FateOracle)

