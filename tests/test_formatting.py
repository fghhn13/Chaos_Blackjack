"""CLI formatting helpers."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.ui.formatting import format_dealer_visible, format_hand


def test_format_hand() -> None:
    h = (Card(Rank("7"), ""), Card(Rank("A"), ""))
    s = format_hand(h)
    assert "7" in s and "A" in s


def test_dealer_hole_hidden() -> None:
    h = (Card(Rank("6"), ""), Card(Rank("K"), ""))
    assert "?" in format_dealer_visible(h, hide_hole=True)
    assert "?" not in format_dealer_visible(h, hide_hole=False)
