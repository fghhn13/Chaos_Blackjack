"""Item: Swap — replace first player card with top deck card."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class Swap:
    name = "swap"

    def use(self, ctx: ItemContext) -> ItemResult:
        if not ctx.state.player_hand:
            return ItemResult(ok=False, message="No player cards to swap")
        if not ctx.state.deck:
            return ItemResult(ok=False, message="Deck is empty")

        old_rank = ctx.state.player_hand[0].rank
        new_rank = ctx.state.deck[0].rank
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {
                    "item": self.name,
                    "swap_from_rank": old_rank,
                    "swap_to_rank": new_rank,
                },
            ),
        )
        return ItemResult(
            ok=True,
            message=f"Swap queued: first card {old_rank} -> {new_rank}",
            extra={"swap_top_into_first_player_card": True},
        )


register_item(Swap.name, Swap)

