"""Card / hand display — readable, aligned."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card

_SUITS = ("♠", "♥", "♦", "♣")


def format_card(card: Card, style_index: int = 0) -> str:
    suit = card.suit if card.suit else _SUITS[style_index % 4]
    return f"{card.rank}{suit}"


def format_hand(cards: tuple[Card, ...]) -> str:
    parts = [format_card(c, i) for i, c in enumerate(cards)]
    return "[" + ", ".join(parts) + "]"


def format_dealer_visible(hand: tuple[Card, ...], hide_hole: bool) -> str:
    if not hand:
        return "[]"
    first = format_card(hand[0], 0)
    if len(hand) == 1:
        return f"[{first}]"
    if hide_hole:
        return f"[{first}, ?]"
    rest = [format_card(c, i + 1) for i, c in enumerate(hand[1:])]
    return f"[{first}, " + ", ".join(rest) + "]"
