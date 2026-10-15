"""What a player's Collection shows (docs/design/CODEX.md "Discovery").

A guided player (meta/onboarding.py) discovers entries by meeting them: a rule that came up at the table, an
item or build seen on a shop shelf, offered as a core, bought or used. Undiscovered entries show as "???"
with a hint where to look. A dealer's tab is a silhouette while the dealer's table is (New run shows the same)
and is missing while the table is not listed at all. Players from before onboarding see everything.

`codex_seen` rows (kind, entry id) map to Collection kinds: "item" (bought or used) and "offer" (seen on offer)
discover items and builds, "rule" Chaos rules, "environment" Poker Head's rules, "mode" tables, "ai" dealers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chaos_blackjack.codex.models import CodexEntry

# Collection kind -> the codex_seen kinds that discover it.
SEEN_KINDS: dict[str, tuple[str, ...]] = {
    "item": ("item", "offer"),
    "build": ("item", "offer"),
    "rule": ("rule",),
    "environment": ("environment",),
    "mode": ("mode",),
    "ai": ("ai",),
}
HINTS: dict[str, str] = {
    "item": "Not discovered yet. Look for it on a shop shelf.",
    "build": "Not discovered yet. Look for it in Poker Head's shop, or among the cores he offers.",
    "environment": "Not discovered yet. Poker Head has not put this rule on your table.",
    "rule": "Not discovered yet. The dealer has not used this rule on you.",
}


@dataclass(frozen=True)
class Discovery:
    seen: frozenset[tuple[str, str]] = frozenset()
    open_series: frozenset[str] = frozenset({"core"})
    teasers: dict[str, str] = field(default_factory=dict)   # series shown as a silhouette -> how to open it
    all_known: bool = False

    @classmethod
    def everything(cls) -> "Discovery":
        return cls(all_known=True)

    @classmethod
    def from_seen(cls, seen: Iterable[tuple[str, str]], options: Iterable[Any]) -> "Discovery":
        """From codex_seen rows and the player's tables (meta ModeOption: mode, unlocked, hint)."""
        open_series, teasers = {"core"}, {}
        for o in options:
            if o.unlocked:
                open_series.add(o.mode.series)
            elif o.hint:
                teasers.setdefault(o.mode.series, o.hint)
        return cls(frozenset(seen), frozenset(open_series), {s: t for s, t in teasers.items() if s not in open_series})

    def series_state(self, series: str) -> str:
        """"open", "silhouette" (named in New run, not open yet) or "hidden"."""
        if self.all_known or series in self.open_series:
            return "open"
        return "silhouette" if series in self.teasers else "hidden"

    def known(self, entry: "CodexEntry") -> bool:
        if self.all_known or entry.kind not in SEEN_KINDS or entry.kind == "mode":
            return True   # tables follow their tab; kinds without tracking are always shown
        return any((kind, entry.id) in self.seen for kind in SEEN_KINDS[entry.kind])

    def hint(self, entry: "CodexEntry") -> str:
        return HINTS.get(entry.kind, "Not discovered yet.")

    def count(self, entries: Iterable["CodexEntry"]) -> tuple[int, int]:
        """(discovered, total)."""
        entries = list(entries)
        return sum(self.known(e) for e in entries), len(entries)


__all__ = ["Discovery", "HINTS", "SEEN_KINDS"]
