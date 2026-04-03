"""Item: Danger Radar — count how many 10-value cards remain in the deck."""

from __future__ import annotations

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import register_item


_HIGH_RANKS = {"10", "J", "Q", "K"}


class DangerRadar:
    name = "danger_radar"

    def use(self, ctx: ItemContext) -> ItemResult:
        total = len(ctx.state.deck)
        if total == 0:
            return ItemResult(ok=False, message="Deck is empty")

        high_count = sum(
            1 for c in ctx.state.deck if c.rank.upper() in _HIGH_RANKS
        )
        rate = high_count / total if total else 0.0
        ctx.emit_event(
            Event(
                EventType.ITEM_USED,
                {
                    "item": self.name,
                    "danger_high_count": high_count,
                    "danger_total": total,
                    "danger_rate": rate,
                },
            ),
        )
        msg_rate = f"{rate:.0%}"
        return ItemResult(
            ok=True,
            message=f"Remaining deck danger: {high_count}/{total} are 10/J/Q/K (rate {msg_rate})",
        )


register_item(DangerRadar.name, DangerRadar)

