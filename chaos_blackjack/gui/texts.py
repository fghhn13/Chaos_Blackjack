"""Player-facing strings for the GUI.

The controller emits notice kinds + data; this module turns them into UI
copy. Add a formatter to NOTICE_TEXT for each new notice kind you want in the
event feed — unknown kinds fall back to `notice.text`.
"""

from __future__ import annotations

from collections.abc import Callable

from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import RoundResult
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.assets.manifest import MANIFEST

Line = tuple[str, theme.Color]

GOOD = (0x7C, 0xD6, 0x92)
BAD = (0xE0, 0x6A, 0x6A)


def asset_name(asset_id: str) -> str:
    """Display name for an item / rule id (manifest description)."""
    spec = MANIFEST.get(asset_id)
    return spec.description if spec and spec.description else asset_id


def _draw(n: Notice) -> Line:
    who = "You draw" if n.data.get("to_player", True) else "Dealer draws"
    return f"{who} {n.data.get('rank', '?')}", theme.TEXT


NOTICE_TEXT: dict[str, Callable[[Notice], Line | None]] = {
    NoticeKind.DRAW_CARD: _draw,
    NoticeKind.ROUND_STARTED: lambda n: (f"Round {n.data.get('round')} — bet {n.data.get('bet')}", theme.GOLD),
    NoticeKind.PLAYER_BUST: lambda n: (f"Bust! {n.data.get('total')}", BAD),
    NoticeKind.PLAYER_BLACKJACK: lambda n: ("Blackjack!", theme.GOLD),
    NoticeKind.DEALER_BLACKJACK: lambda n: ("Dealer has blackjack", BAD),
    NoticeKind.DOUBLED: lambda n: (f"Double down! Bet is now {n.data.get('bet')}", theme.GOLD),
    NoticeKind.SURRENDERED: lambda n: (f"Surrendered — {n.data.get('refund')} returned", theme.TEXT_MUTED),
    NoticeKind.DEALER_STANDS: lambda n: (f"Dealer stands on {n.data.get('total')}", theme.TEXT),
    NoticeKind.DEALER_BUSTS: lambda n: (f"Dealer busts! {n.data.get('total')}", GOOD),
    NoticeKind.REWARD_GRANTED: lambda n: (f"Streak reward: {asset_name(str(n.data.get('item')))}", theme.GOLD),
    NoticeKind.RULE_MODIFIER_APPLIED: lambda n: (f"⚡ Chaos rule: {asset_name(str(n.data.get('rule_id')))}", theme.CHAOS_MAGENTA),
    NoticeKind.CHAOS_ACTION_REJECTED: lambda n: ("Chaos AI action blocked", theme.TEXT_MUTED),
    NoticeKind.CHAOS_NARRATION: lambda n: (f"Chaos AI: “{n.data.get('text')}”", theme.CHAOS_MAGENTA),
    NoticeKind.ITEM_RESULT: lambda n: (n.text, theme.GOLD if n.data.get("ok") else BAD),
    NoticeKind.GAME_SAVED: lambda n: ("Game saved", GOOD),
    # Shown elsewhere (banner / phase changes) — keep out of the feed.
    NoticeKind.PHASE_CHANGED: lambda n: None,
    NoticeKind.ROUND_SETTLED: lambda n: None,
    NoticeKind.RUN_ENDED: lambda n: None,
    NoticeKind.ITEM_USED: lambda n: None,  # ITEM_RESULT carries the message
}


def notice_line(notice: Notice) -> Line | None:
    fmt = NOTICE_TEXT.get(notice.kind)
    if fmt is not None:
        return fmt(notice)
    return (notice.text, theme.TEXT) if notice.text else None


def outcome_banner(r: RoundResult) -> tuple[str, str, theme.Color]:
    """(headline, detail, color) for the round-over banner."""
    if r.outcome == "blackjack":
        head, color = "Blackjack!", theme.GOLD
    elif r.outcome == "player":
        head, color = "You win", GOOD
    elif r.outcome == "surrender":
        head, color = "Surrendered", theme.TEXT_MUTED
    elif r.outcome == "push":
        head, color = "Push", theme.TEXT
    elif r.dealer_blackjack:
        head, color = "Dealer blackjack", BAD
    elif r.player_bust:
        head, color = "Bust", BAD
    else:
        head, color = "Dealer wins", BAD
    sign = "+" if r.delta > 0 else ""
    detail = f"You {r.player_total}  ·  Dealer {r.dealer_total}  ·  {sign}{r.delta}"
    if r.doubled:
        detail += " (doubled)"
    return head, detail, color


def run_end_text(kind: str) -> tuple[str, str]:
    if kind == "victory":
        return "Victory!", "You reached the target bankroll"
    return "Bankrupt", "You ran out of chips"
