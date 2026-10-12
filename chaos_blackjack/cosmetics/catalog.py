"""Built-in cosmetics. Prices: `cosmetic_price` rows; achievement rewards:
`achievement_reward` rows (both in data/seed/default.sql).

To add one: drop `<asset id>.png` in assets/ (or let the GUI draw a
placeholder), register it here, then give it a price row and/or name it as an
achievement reward. Each slot keeps exactly one `default=True` entry.
"""

from __future__ import annotations

from chaos_blackjack.cosmetics import Cosmetic, register_cosmetic


def _chips(prefix: str) -> dict[str, str]:
    return {f"chip_{v}": f"{prefix}_{v}" for v in (1, 5, 10, 25)}


for _c in (
    # Decks (card back, and optionally the card face)
    Cosmetic("card_back_standard", "deck", "House Standard", "The casino's own deck.", default=True),
    Cosmetic("card_back_crimson", "deck", "Crimson Lattice", "A deep red lattice back.",
             assets={"card_back": "card_back_crimson"}, order=10),
    Cosmetic("card_back_royal", "deck", "Royal Flush", "Gold leaf for blackjack collectors.", rarity="epic",
             assets={"card_back": "card_back_royal"}, order=20),
    Cosmetic("deck_poker_head", "deck", "Poker Head's Deck", "Poker Head's own cards, earned at his table.",
             rarity="legendary", assets={"card_back": "card_back_poker_head",
                                         "card_front_blank": "card_front_poker_head"}, order=30,
             series="poker_head"),
    # Tables
    Cosmetic("table_standard", "table", "Casino Green", "Classic green felt.", default=True),
    Cosmetic("table_midnight", "table", "Midnight Felt", "Dark blue felt for late games.", rarity="rare",
             assets={"table_background": "table_midnight"}, order=10),
    Cosmetic("table_chaos", "table", "Chaos Velvet", "Purple velvet for a chaotic evening.", rarity="epic",
             assets={"table_background": "table_chaos"}, order=20),
    Cosmetic("table_poker_head", "table", "Poker Head's Table", "Green felt and old gold, from his own room.",
             rarity="legendary", assets={"table_background": "table_poker_head"}, order=30,
             series="poker_head"),
    # Chip sets
    Cosmetic("chips_standard", "chips", "House Chips", "The casino's chips.", default=True),
    Cosmetic("chips_neon", "chips", "Neon Chips", "Chips that glow under the lamp.", rarity="rare",
             assets=_chips("chips_neon"), order=10),
    Cosmetic("chips_gold", "chips", "Gold Chips", "Earned over a hundred winning hands.", rarity="epic",
             assets=_chips("chips_gold"), order=20),
    # Avatars
    Cosmetic("avatar_standard", "avatar", "Newcomer", "A seat at the table.", default=True),
    Cosmetic("avatar_spade", "avatar", "Ace of Spades", "Sharp and simple.",
             assets={"avatar": "avatar_spade"}, order=10),
    Cosmetic("avatar_joker", "avatar", "White Flag", "For those who know when to fold.", rarity="rare",
             assets={"avatar": "avatar_joker"}, hidden=True, order=20),
):
    register_cosmetic(_c)
