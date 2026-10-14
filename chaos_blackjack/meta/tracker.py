"""RunTracker — builds a run summary from the controller's notices.

It listens without consuming notices (GameController.add_listener), so the
GUI keeps draining them as usual. Summary shape: docs/design/META_PROGRESSION.md §5.3.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.economy import WIN_OUTCOMES
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
        self.hands_won = self.five_card_hands = self.win_streak = 0
        self.peak_money = controller.run.money
        self.spent = 0                     # chips spent in the run's shop (lifetime spend)
        # Poker Head's build table: Fourfold Ticket wins, Bust Insurance saves, Fresh Hand into 21.
        self.fourfold_wins = self.insurance_saves = self.fresh_21 = 0
        self._prepared: dict[str, int] = {}  # consumable -> the round it was used in
        controller.add_listener(self.on_notice)

    def on_notice(self, n: Notice) -> None:
        kind, data = n.kind, n.data
        if kind == NoticeKind.RULE_MODIFIER_APPLIED and data.get("rule_id"):
            self.rules_seen[str(data["rule_id"])] += 1
        elif kind == NoticeKind.ITEM_RESULT and data.get("ok") and data.get("item"):
            self.items_used[str(data["item"])] += 1
            if data["item"] in ("ph_quad", "ph_insurance"):
                self._prepared[str(data["item"])] = self.controller.run.round
        elif kind == NoticeKind.ITEM_RESULT and n.text.startswith("Fresh Hand:"):
            state = self.controller.state
            if state is not None and self.controller.hand_value(state.player_hand) == 21:
                self.fresh_21 += 1
        elif kind == NoticeKind.ITEM_BOUGHT and data.get("item"):
            self.items_bought[str(data["item"])] += 1
            self.spent += int(data.get("price") or 0)
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
            outcome, played = getattr(result, "outcome", None), getattr(result, "round", None)
            if outcome in WIN_OUTCOMES and getattr(result, "doubled", False) and self._prepared.get("ph_quad") == played:
                self.fourfold_wins += 1
            if (outcome == "push" and getattr(result, "player_bust", False)
                    and self._prepared.get("ph_insurance") == played):
                self.insurance_saves += 1
            if getattr(result, "outcome", None) in WIN_OUTCOMES:
                self.hands_won += 1
                state = self.controller.state
                if state is not None and len(state.player_hand) >= 5:
                    self.five_card_hands += 1
            self.win_streak = max(self.win_streak, self.controller.run.win_streak)

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
            "hands_won": self.hands_won,
            "five_card_hands": self.five_card_hands,
            "win_streak": self.win_streak,
            "spent": self.spent,
            "fourfold_wins": self.fourfold_wins,
            "insurance_saves": self.insurance_saves,
            "fresh_21": self.fresh_21,
            "core": getattr(getattr(c.table, "loadout", None), "core", None),
            # The run won by reaching its table's ceiling (a goal set as a multiple).
            "ceiling": int(bool(c.run_end and c.run_end.kind == "victory" and c.config.target_multiple
                                and c.run.money >= c.run.target_money)),
            "chaos_ai": "default" if c.config.enable_chaos else None,
        }
