"""RunTracker — builds a run summary from the controller's notices.

It listens without consuming notices (GameController.add_listener), so the
GUI keeps draining them as usual. Summary shape: docs/design/META_PROGRESSION.md §5.3.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.notices import Notice, NoticeKind

if TYPE_CHECKING:
    from chaos_blackjack.app.controller import GameController


class RunTracker:
    def __init__(self, controller: "GameController") -> None:
        self.controller = controller
        self.rules_seen: Counter[str] = Counter()
        self.items_used: Counter[str] = Counter()
        self.items_bought: Counter[str] = Counter()
        self.blackjacks = self.doubles = self.surrenders = 0
        self.peak_money = controller.run.money
        controller.add_listener(self.on_notice)

    def on_notice(self, n: Notice) -> None:
        kind, data = n.kind, n.data
        if kind == NoticeKind.RULE_MODIFIER_APPLIED and data.get("rule_id"):
            self.rules_seen[str(data["rule_id"])] += 1
        elif kind == NoticeKind.ITEM_RESULT and data.get("ok") and data.get("item"):
            self.items_used[str(data["item"])] += 1
        elif kind == NoticeKind.ITEM_BOUGHT and data.get("item"):
            self.items_bought[str(data["item"])] += 1
        elif kind == NoticeKind.PLAYER_BLACKJACK:
            self.blackjacks += 1
        elif kind == NoticeKind.DOUBLED:
            self.doubles += 1
        elif kind == NoticeKind.SURRENDERED:
            self.surrenders += 1
        elif kind == NoticeKind.ROUND_SETTLED:
            result = data.get("result")
            money = getattr(result, "money_after", None)
            if money is not None:
                self.peak_money = max(self.peak_money, int(money))

    def detach(self) -> None:
        self.controller.remove_listener(self.on_notice)

    def summary(self) -> dict[str, Any]:
        c = self.controller
        rounds = c.last_result.round if c.last_result else max(0, c.run.round - 1)
        return {
            "rules_seen": dict(self.rules_seen),
            "items_used": dict(self.items_used),
            "items_bought": dict(self.items_bought),
            "rounds": rounds,
            "peak_money": max(self.peak_money, c.run.money),
            "blackjacks": self.blackjacks,
            "doubles": self.doubles,
            "surrenders": self.surrenders,
            "chaos_ai": "default" if c.config.enable_chaos else None,
        }
