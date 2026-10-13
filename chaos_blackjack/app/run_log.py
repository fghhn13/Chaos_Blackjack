"""Run log — the whole run's record, saved with the run.

The controller feeds every notice through `RunLog.record`; lines that matter
later (deals, results, rules, deck changes, money, shop) are kept with their
round and category. The log is capped (oldest lines go first) and also keeps
a few counters for the run summary, which survive the cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.app.notices import Notice, NoticeKind

CATEGORIES = ("hand", "chaos", "deck", "money", "shop", "items")
DEFAULT_LIMIT = 400

_OUTCOME_TEXT = {
    "player": "You win", "blackjack": "Blackjack", "dealer": "Dealer wins",
    "push": "Push", "surrender": "Surrendered",
}


def _settled(n: Notice) -> str:
    r = n.data.get("result")
    if r is None:
        return ""
    sign = "+" if r.delta > 0 else ""
    return (f"{_OUTCOME_TEXT.get(r.outcome, r.outcome)}: you {r.player_total}, dealer {r.dealer_total} "
            f"({sign}{r.delta}, bankroll {r.money_after})")


def _rule_name(n: Notice) -> str:
    from chaos_blackjack.ui.descriptions import rule_display_name

    return rule_display_name(str(n.data.get("rule_id", "")))


# notice kind -> (category, text maker); kinds not listed are not logged.
_LOGGED: dict[str, tuple[str, Any]] = {
    NoticeKind.ROUND_STARTED: ("hand", lambda n: f"Round {n.data.get('round')} started, bet {n.data.get('bet')}"),
    NoticeKind.DRAW_CARD: ("hand", lambda n: f"{'You draw' if n.data.get('to_player', True) else 'Dealer draws'} "
                                             f"{n.data.get('rank', '?')}"),
    NoticeKind.PLAYER_BUST: ("hand", lambda n: f"Bust at {n.data.get('total')}"),
    NoticeKind.PLAYER_BLACKJACK: ("hand", lambda n: "Blackjack!"),
    NoticeKind.DEALER_BLACKJACK: ("hand", lambda n: "Dealer has blackjack"),
    NoticeKind.DOUBLED: ("hand", lambda n: f"Doubled: bet {n.data.get('bet')}"),
    NoticeKind.SURRENDERED: ("hand", lambda n: f"Surrendered, {n.data.get('refund')} returned"),
    NoticeKind.DEALER_STANDS: ("hand", lambda n: f"Dealer stands on {n.data.get('total')}"),
    NoticeKind.DEALER_BUSTS: ("hand", lambda n: f"Dealer busts at {n.data.get('total')}"),
    NoticeKind.ROUND_SETTLED: ("money", _settled),
    NoticeKind.FEE_PAID: ("money", lambda n: n.text),
    NoticeKind.RULE_MODIFIER_APPLIED: ("chaos", lambda n: f"Chaos rule: {_rule_name(n)}"),
    NoticeKind.CHAOS_NARRATION: ("chaos", lambda n: f"“{n.data.get('text')}”"),
    NoticeKind.CHAOS_POKE_REPLY: ("chaos", lambda n: f"“{n.data.get('text')}”"),
    NoticeKind.CHAOS_DISPELLED: ("chaos", lambda n: "Chaos rules dispelled"),
    NoticeKind.TABLE_EVENT: ("deck", lambda n: n.text),
    NoticeKind.ITEM_BOUGHT: ("shop", lambda n: n.text),
    NoticeKind.SHOP_REROLLED: ("shop", lambda n: n.text),
    NoticeKind.SHOP_RESTOCKED: ("shop", lambda n: n.text),
    NoticeKind.ITEM_RESULT: ("items", lambda n: n.text),
    NoticeKind.RUN_ENDED: ("money", lambda n: n.text),
}


@dataclass
class LogEntry:
    round: int
    category: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"round": self.round, "category": self.category, "text": self.text}


@dataclass
class RunLog:
    limit: int = DEFAULT_LIMIT
    entries: list[LogEntry] = field(default_factory=list)
    # Run summary counters (kept whatever the cap drops).
    stats: dict[str, int] = field(default_factory=lambda: {
        "hands": 0, "wins": 0, "losses": 0, "pushes": 0, "naturals": 0, "peak": 0, "fees": 0})

    def record(self, round_no: int, notice: Notice) -> None:
        spec = _LOGGED.get(notice.kind)
        if spec is None:
            return
        category, make = spec
        text = make(notice)
        if text:
            self.entries.append(LogEntry(round_no, category, str(text)))
            del self.entries[:-self.limit]
        self._count(notice)

    def _count(self, n: Notice) -> None:
        s = self.stats
        if n.kind == NoticeKind.FEE_PAID:
            s["fees"] += int(n.data.get("fee", 0))
        if n.kind != NoticeKind.ROUND_SETTLED or n.data.get("result") is None:
            return
        r = n.data["result"]
        s["hands"] += 1
        if r.outcome in ("player", "blackjack"):
            s["wins"] += 1
        elif r.outcome in ("dealer", "surrender"):
            s["losses"] += 1
        else:
            s["pushes"] += 1
        if r.outcome == "blackjack":
            s["naturals"] += 1
        s["peak"] = max(s["peak"], int(r.money_after))

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self.entries], "stats": dict(self.stats)}

    def restore(self, data: dict[str, Any] | None) -> None:
        if not data:
            return
        self.entries = [LogEntry(int(e["round"]), str(e["category"]), str(e["text"]))
                        for e in data.get("entries", [])][-self.limit:]
        self.stats.update({k: int(v) for k, v in (data.get("stats") or {}).items()})
