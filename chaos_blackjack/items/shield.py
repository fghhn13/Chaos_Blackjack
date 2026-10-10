"""Item: Shield — dispel every active chaos rule for the rest of the round."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class Shield:
    name = "shield"

    def use(self, ctx: ItemContext) -> ItemResult:
        rules = ctx.active_rule_ids
        if not rules:
            return ItemResult(ok=False, message="No chaos rule is active to dispel")
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {"item": self.name, "dispelled_rules": list(rules)},
            ),
        )
        return ItemResult(
            ok=True,
            message=f"Shield dispels {len(rules)} chaos rule{'s' if len(rules) != 1 else ''}",
            extra={"dispel_chaos_rules": True},
        )


register_item(Shield.name, Shield)
