"""Collect user-visible feedback from game events."""

from __future__ import annotations

from collections.abc import Callable

from chaos_blackjack.events.event import Event, EventType


class FeedbackLog:
    """Append-only lines for the RESULT / FEEDBACK section."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, line: str) -> None:
        if line:
            self.lines.append(line)

    def drain(self) -> list[str]:
        out = self.lines[:]
        self.lines.clear()
        return out

    def wire_dispatcher(
        self,
        register: Callable[[EventType, Callable[[Event], None]], None],
    ) -> None:
        register(EventType.DRAW_CARD, self._on_draw)
        register(EventType.RULE_MODIFIER_APPLIED, self._on_rule)
        register(EventType.CHAOS_ACTION_REJECTED, self._on_reject)
        register(EventType.ITEM_USED, self._on_item)

    def _on_draw(self, e: Event) -> None:
        pl = e.payload
        to_player = pl.get("to_player", True)
        rank = pl.get("rank", "?")
        if to_player:
            self.add(f"You draw: {rank}")
        else:
            self.add(f"Dealer draws: {rank}")

    def _on_rule(self, e: Event) -> None:
        pl = e.payload
        rid = pl.get("rule_id", "?")
        params = pl.get("params") or {}
        if rid == "modify_card_value" and isinstance(params, dict) and "delta" in params:
            d = params["delta"]
            self.add(f"⚡ Chaos Effect Triggered: rank adjustment {d:+} per card")
        else:
            self.add(f"⚡ Chaos effect applied: {rid}")

    def _on_reject(self, e: Event) -> None:
        pl = e.payload
        r = pl.get("reason", "?")
        self.add(f"⚠ Chaos blocked: {r}")

    def _on_item(self, e: Event) -> None:
        pl = e.payload
        item = pl.get("item", "?")
        rk = pl.get("peeked_rank")
        if rk is not None:
            self.add(f"🎒 Item [{item}] — next rank peek: {rk}")
            return

        hole_rank = pl.get("hole_rank")
        if hole_rank is not None:
            self.add(f"🎒 Item [{item}] — dealer hole card: {hole_rank}")
            return

        peeked_ranks = pl.get("peeked_ranks")
        if isinstance(peeked_ranks, list) and peeked_ranks:
            shown = ", ".join(str(x) for x in peeked_ranks)
            self.add(f"🎒 Item [{item}] — top {len(peeked_ranks)} ranks: {shown}")
            return

        if pl.get("shield_requested"):
            self.add(f"🎒 Item [{item}] — shield primed")
            return

        swap_from = pl.get("swap_from_rank")
        swap_to = pl.get("swap_to_rank")
        if swap_from is not None and swap_to is not None:
            self.add(f"🎒 Item [{item}] — swap queued: {swap_from} -> {swap_to}")
            return

        danger_high_count = pl.get("danger_high_count")
        danger_total = pl.get("danger_total")
        if (
            isinstance(danger_high_count, int)
            and isinstance(danger_total, int)
            and danger_total > 0
        ):
            rate = pl.get("danger_rate")
            rate_s = f"{rate:.0%}" if isinstance(rate, float) else "?"
            self.add(
                f"🎒 Item [{item}] — high cards: {danger_high_count}/{danger_total} (rate {rate_s})"
            )
            return

        self.add(f"🎒 Item used: {item}")
