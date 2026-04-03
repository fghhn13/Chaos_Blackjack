"""Item: Shield — reserved for blocking chaos effects."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class Shield:
    name = "shield"

    def use(self, ctx: ItemContext) -> ItemResult:
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {"item": self.name, "shield_requested": True},
            ),
        )
        return ItemResult(
            ok=True,
            message="Shield primed. (MVP: no active chaos blocking yet)",
        )


register_item(Shield.name, Shield)

