"""Asset manifest — the single list of art the GUI knows about.

Ids match black-jack-assets/docs/asset-list.md: drop `<id>.png` into any
asset dir and it replaces the placeholder. To add an asset, call
`register(AssetSpec(...))` (here or from a plugin module).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from chaos_blackjack.cosmetics import get_cosmetic
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
    # Codex mode icons; final mode_normal.png / mode_chaos.png override these.
    AssetSpec("mode_normal", "mode", ICON, ph.icon("CL", theme.GOLD), "Classic"),
    AssetSpec("mode_chaos", "mode", ICON, ph.icon("CH", theme.CHAOS_MAGENTA), "Chaos"),
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


# Cosmetics (docs/design/COSMETICS_ACHIEVEMENTS.md). Skin art uses the base
# asset's category and size; a cosmetic asset with neither a file nor an entry
# here draws the base look (AssetManager.resolve).
AVATAR = (256, 256)
register(AssetSpec("avatar", "avatar", AVATAR, ph.avatar("bust", theme.FELT, theme.GOLD_DIM), "Player avatar"))

_NEON = {1: (0xE8, 0xF4, 0xF2), 5: (0xF2, 0x4F, 0x9A), 10: (0x2F, 0xC4, 0xE6), 25: (0xB6, 0xF0, 0x4A)}
_GOLD_CHIPS = {1: (0xF0, 0xE2, 0xB8), 5: (0xC8, 0x8A, 0x3A), 10: (0x9A, 0x84, 0x4C), 25: (0xE2, 0xB8, 0x4A)}
_SKINS: dict[str, tuple[str, tuple[int, int], Placeholder]] = {
    "card_back_crimson": ("card", CARD, ph.lattice_back((0x4A, 0x10, 0x16), (0x8E, 0x2A, 0x30), theme.GOLD,
                                                        theme.GOLD_DIM)),
    "card_back_royal": ("card", CARD, ph.lattice_back((0x16, 0x1C, 0x3C), (0x3E, 0x4C, 0x86), (0xE8, 0xC8, 0x6A),
                                                      theme.GOLD)),
    "table_midnight": ("background", BG, ph.felt_table((0x16, 0x22, 0x38), (0x22, 0x32, 0x50), (0x6E, 0x7E, 0xA0))),
    "table_chaos": ("background", BG, ph.felt_table((0x2E, 0x18, 0x3C), (0x44, 0x26, 0x56), theme.CHAOS_MAGENTA)),
    **{f"chips_neon_{v}": ("chip", ICON, ph.chip(c, theme.DARK)) for v, c in _NEON.items()},
    **{f"chips_gold_{v}": ("chip", ICON, ph.chip(c, (0x6E, 0x50, 0x1E))) for v, c in _GOLD_CHIPS.items()},
    "avatar_spade": ("avatar", AVATAR, ph.avatar("spade", theme.DARK, theme.GOLD)),
    "avatar_joker": ("avatar", AVATAR, ph.avatar("flag", (0x3A, 0x2A, 0x44), theme.CHAOS_MAGENTA)),
}


def _skin_name(asset_id: str) -> str:
    cosmetic = get_cosmetic(asset_id) or get_cosmetic(asset_id.rsplit("_", 1)[0])
    return cosmetic.name if cosmetic else asset_id


for _id, (_category, _size, _draw) in _SKINS.items():
    register(AssetSpec(_id, _category, _size, _draw, _skin_name(_id)))
