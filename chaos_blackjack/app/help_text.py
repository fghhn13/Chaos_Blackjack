"""Plain-English item help shared by front-ends (GUI tooltips, agent observations)."""

from __future__ import annotations

ITEM_HELP: dict[str, str] = {
    "peek": "Reveal the rank of the next card in the deck.",
    "fate_oracle": "Reveal the ranks of the next 3 cards in the deck.",
    "danger_radar": "Show how many 10/J/Q/K cards remain in the deck.",
    "hole_card_hacker": "Reveal the dealer's face-down card.",
    "swap": "Replace your first card with the top card of the deck.",
    "shield": "Primes a shield against chaos (currently has no game effect).",
}
