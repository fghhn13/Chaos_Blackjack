"""Item plugin: reveal next deck card rank (read-only)."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class Peek:
    name = "peek"

    def use(self, ctx: ItemContext) -> ItemResult:
        rank = ctx.peek_next_card_rank()
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {"item": self.name, "peeked_rank": rank},
            ),
        )
        if rank is None:
            return ItemResult(ok=False, message="Deck empty")
        return ItemResult(ok=True, message=f"Next card rank: {rank}")


register_item("peek", Peek)
