"""Item: Danger Radar — tell whether the next hit would bust the player.

The answer uses the rules in force (chaos value changes and bust limits), so
it stays useful when every round is dealt from a fresh deck.
"""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


class DangerRadar:
    name = "danger_radar"
    description = "Tell whether your next hit would bust you (under the rules in force)."

    def use(self, ctx: ItemContext) -> ItemResult:
        check = getattr(ctx, "next_hit_busts", None)
        busts = check() if check is not None else None
        if busts is None:
            return ItemResult(ok=False, message="The radar has nothing to read")
        ctx.emit_event(Event(EventType.ITEM_USED, {"item": self.name, "next_hit_busts": busts}))
        return ItemResult(ok=True, message="Radar: the next hit would BUST you." if busts
                          else "Radar: the next hit is safe.")


register_item(DangerRadar.name, DangerRadar)
