"""Asset manifest — the single list of art the GUI knows about.

Ids match black-jack-assets/docs/asset-list.md: drop `<id>.png` into any
asset dir and it replaces the placeholder. To add an asset, call
`register(AssetSpec(...))` (here or from a plugin module).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.assets import placeholders as ph

Placeholder = Callable[[tuple[int, int], Callable[[int], pygame.font.Font]], pygame.Surface]


@dataclass(frozen=True)
class AssetSpec:
    id: str
    category: str
    size: tuple[int, int]  # delivery size (asset-list.md); placeholders draw at this size
    placeholder: Placeholder
    description: str = ""


MANIFEST: dict[str, AssetSpec] = {}


def register(spec: AssetSpec) -> AssetSpec:
    MANIFEST[spec.id] = spec
    return spec


def by_category() -> dict[str, list[AssetSpec]]:
    out: dict[str, list[AssetSpec]] = {}
    for spec in MANIFEST.values():
        out.setdefault(spec.category, []).append(spec)
    return out


BG = (1920, 1080)
CARD = (512, 768)
ICON = (256, 256)
PORTRAIT = (512, 512)

for _spec in (
    AssetSpec("table_background", "background", BG, ph.table_background, "Table background"),
    AssetSpec("menu_background", "background", BG, ph.menu_background, "Menu background"),
    AssetSpec("ending_victory", "background", BG, ph.ending_victory, "Victory ending"),
    AssetSpec("ending_bankrupt", "background", BG, ph.ending_bankrupt, "Bankrupt ending"),
    AssetSpec("card_back", "card", CARD, ph.card_back, "Card back"),
    AssetSpec("card_front_blank", "card", CARD, ph.card_front_blank, "Blank card face"),
    *(
        AssetSpec(f"chip_{v}", "chip", ICON, ph.chip(c), f"{v} chip")
        for v, c in theme.CHIP_COLORS.items()
    ),
    *(
        AssetSpec(f"chaos_{e}", "character", PORTRAIT, ph.chaos_character(e), f"Chaos AI ({e})")
        for e in ("calm", "smug", "laugh", "angry")
    ),
    # Items — ids equal registry item names
    AssetSpec("peek", "item", ICON, ph.icon("PK", theme.GOLD), "Peek"),
    AssetSpec("swap", "item", ICON, ph.icon("SW", theme.GOLD), "Swap"),
    AssetSpec("shield", "item", ICON, ph.icon("SH", theme.GOLD), "Shield"),
    AssetSpec("danger_radar", "item", ICON, ph.icon("DR", theme.GOLD), "Danger Radar"),
    AssetSpec("fate_oracle", "item", ICON, ph.icon("FO", theme.GOLD), "Fate Oracle"),
    AssetSpec("hole_card_hacker", "item", ICON, ph.icon("HH", theme.GOLD), "Hole Card Hacker"),
    # Chaos rules — ids equal registry rule names
    AssetSpec("fragile_bust", "rule", ICON, ph.icon("FB", theme.CHAOS_MAGENTA), "Fragile Bust"),
    AssetSpec("great_crash", "rule", ICON, ph.icon("GC", theme.CHAOS_MAGENTA), "Great Crash"),
    AssetSpec("modify_card_value", "rule", ICON, ph.icon("±", theme.CHAOS_MAGENTA), "Value Shift"),
    AssetSpec("odd_even_chaos", "rule", ICON, ph.icon("OE", theme.CHAOS_MAGENTA), "Odd-Even Chaos"),
    AssetSpec("reverse_bust", "rule", ICON, ph.icon("RB", theme.CHAOS_MAGENTA), "Reverse Bust"),
    AssetSpec("suit_power", "rule", ICON, ph.icon("SP", theme.CHAOS_MAGENTA), "Suit Power"),
    AssetSpec("tiebreaker_shift", "rule", ICON, ph.icon("TB", theme.CHAOS_MAGENTA), "Tiebreaker Shift"),
):
    register(_spec)
