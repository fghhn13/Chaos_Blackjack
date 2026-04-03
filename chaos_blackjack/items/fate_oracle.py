"""Item: Fate Oracle — peek the top 3 cards of the deck."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class FateOracle:
    name = "fate_oracle"

    def use(self, ctx: ItemContext) -> ItemResult:
        if not ctx.state.deck:
            return ItemResult(ok=False, message="Deck is empty")

        top3 = ctx.state.deck[:3]
        ranks = [c.rank for c in top3]
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
        return ItemResult(ok=True, message=f"Top {len(ranks)} cards: {shown}")


register_item(FateOracle.name, FateOracle)

