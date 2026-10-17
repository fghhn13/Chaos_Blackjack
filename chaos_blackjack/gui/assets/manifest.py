"""Asset manifest — the single list of art the GUI knows about.

Ids match black-jack-assets/docs/asset-list.md: drop `<id>.png` into any
asset dir and it replaces the placeholder. To add an asset, call
`register(AssetSpec(...))` (here or from a plugin module).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from chaos_blackjack.content.builtin_persona import default_persona, host_persona
from chaos_blackjack.cosmetics import cosmetics
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.assets import placeholders as ph
from chaos_blackjack.poker_head.catalog import PRODUCTS as POKER_HEAD_PRODUCTS

Placeholder = Callable[[tuple[int, int], Callable[[int], pygame.font.Font]], pygame.Surface]


@dataclass(frozen=True)
class AssetSpec:
    id: str
    category: str
    size: tuple[int, int]  # delivery size (asset-list.md); placeholders draw at this size
    placeholder: Placeholder
    description: str = ""
    # Recolour a one-colour silhouette file at load time (alpha kept); None = draw the file as it is.
    tint: tuple[int, int, int] | None = None


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
_J54_RED = (0xC8, 0x3A, 0x3A)  # J-54's jester red
_J54_BLACK = (0x17, 0x17, 0x19)

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
    # Poker Head mode: his own portrait until a dedicated icon ships.
    AssetSpec("mode_poker_head", "mode", ICON, ph.fitted_image(default_persona().portraits["neutral"]),
              "Poker Head"),
    # Chaos rules — ids equal registry rule names
    AssetSpec("fragile_bust", "rule", ICON, ph.icon("FB", theme.CHAOS_MAGENTA), "Fragile Bust"),
    AssetSpec("great_crash", "rule", ICON, ph.icon("GC", theme.CHAOS_MAGENTA), "Great Crash"),
    AssetSpec("modify_card_value", "rule", ICON, ph.icon("±", theme.CHAOS_MAGENTA), "Value Shift"),
    AssetSpec("odd_even_chaos", "rule", ICON, ph.icon("OE", theme.CHAOS_MAGENTA), "Odd-Even Chaos"),
    AssetSpec("reverse_bust", "rule", ICON, ph.icon("RB", theme.CHAOS_MAGENTA), "Reverse Bust"),
    AssetSpec("suit_power", "rule", ICON, ph.icon("SP", theme.CHAOS_MAGENTA), "Suit Power"),
    AssetSpec("tiebreaker_shift", "rule", ICON, ph.icon("TB", theme.CHAOS_MAGENTA), "Tiebreaker Shift"),
    # J-54's table (demo; placeholders): mode icon, deck rules and contracts.
    AssetSpec("mode_j54", "mode", ICON, ph.fitted_image(host_persona("j54").portraits["resting_mania"]), "J-54"),
    AssetSpec("j54_black_plus", "rule", ICON, ph.icon("B+", _J54_RED), "Black Bias"),
    AssetSpec("j54_even_plus", "rule", ICON, ph.icon("E+", _J54_RED), "Even Bias"),
    AssetSpec("j54_hearts_scale", "rule", ICON, ph.icon("H2", _J54_RED), "Heart Gain"),
    AssetSpec("j54_stand_19", "rule", ICON, ph.icon("19", _J54_RED), "High Threshold"),
    AssetSpec("j54_stand_15", "rule", ICON, ph.icon("15", _J54_RED), "Low Threshold"),
    AssetSpec("j54_low_plus", "rule", ICON, ph.icon("L+", _J54_RED), "Low Bias"),
    AssetSpec("j54_faces_set", "rule", ICON, ph.icon("F5", _J54_RED), "Face Reset"),
    AssetSpec("j54_burn", "rule", ICON, ph.icon("BN", _J54_RED), "Burn Protocol"),
    AssetSpec("j54_sample_injection", "rule", ICON, ph.icon("S+", _J54_RED), "Sample Injection"),
    AssetSpec("j54_redundancy_purge", "rule", ICON, ph.icon("R-", _J54_RED), "Redundancy Purge"),
    AssetSpec("j54_ace_injection", "rule", ICON, ph.icon("A+", _J54_RED), "Ace Injection"),
    AssetSpec("j54_layered_sort", "rule", ICON, ph.icon("LS", _J54_RED), "Layered Sort"),
    AssetSpec("j54_data_backflow", "rule", ICON, ph.icon("DB", _J54_RED), "Data Backflow"),
    AssetSpec("j54_streamline", "item", ICON, ph.icon("ST", _J54_RED), "Streamline Contract"),
    AssetSpec("j54_low_purge", "item", ICON, ph.icon("LP", _J54_RED), "Low Purge Contract"),
    AssetSpec("j54_high_injection", "item", ICON, ph.icon("HI", _J54_RED), "High Injection Contract"),
    AssetSpec("j54_freeze", "item", ICON, ph.icon("FZ", _J54_RED), "Freeze Contract"),
    AssetSpec("j54_start_experiment", "item", ICON, ph.icon("JK", _J54_RED), "Start Experiment"),
    # J-54 badges (j54/parts.py)
    AssetSpec("j54_joker_sealed", "icon", ICON, ph.icon("JK", theme.TEXT_MUTED), "Joker sealed"),
    AssetSpec("j54_joker_in_the_deck", "icon", ICON, ph.icon("JK", theme.GOLD), "Joker in the deck"),
    AssetSpec("j54_joker_captured", "icon", ICON, ph.icon("JK", (0x9C, 0xC2, 0x96)), "Joker captured"),
    AssetSpec("j54_goal", "icon", ICON, ph.icon("$", theme.GOLD), "Capital goal"),
    AssetSpec("j54_compute", "icon", ICON, ph.icon("C", theme.GOLD), "Compute"),
    AssetSpec("j54_next", "icon", ICON, ph.icon(">", (0xE0, 0xB0, 0x60)), "Next condition"),
    AssetSpec("j54_bounty", "icon", ICON, ph.icon("B$", theme.GOLD), "Sample bounty"),
    AssetSpec("j54_cut", "icon", ICON, ph.icon("CT", _J54_RED), "Cut"),
    AssetSpec("j54_hot_purge", "icon", ICON, ph.icon("HP", _J54_RED), "Hot Purge"),
    AssetSpec("j54_release", "icon", ICON, ph.icon("RL", theme.GOLD), "Release the Joker"),
    AssetSpec("fw_mid", "icon", ICON, ph.icon("46", (0x9C, 0xC2, 0x96)), "Midrange Firmware"),
    AssetSpec("fw_fives", "icon", ICON, ph.icon("56", (0x9C, 0xC2, 0x96)), "Fives Firmware"),
    AssetSpec("fw_low", "icon", ICON, ph.icon("24", (0x9C, 0xC2, 0x96)), "Low Firmware"),
    AssetSpec("fw_margin", "icon", ICON, ph.icon("22", (0x9C, 0xC2, 0x96)), "Margin Firmware"),
    AssetSpec("j54_fee", "icon", ICON, ph.icon("F", (0xE0, 0xB0, 0x60)), "Compute fee"),
    AssetSpec("j54_freeze", "icon", ICON, ph.icon("*", (0x9C, 0xB8, 0xD8)), "Freeze"),
):
    register(_spec)


# Poker Head build icons share their IDs with the product catalog.
# Selection and visual meanings: docs/design/POKER_HEAD_ART.md.
# Poker Head's environment rule types (poker_head/environment.py); placeholders until art exists.
for _type, _mark, _name in (("fixed", "=#", "Card Rewrite"), ("shift", "+-", "Card Shift"), ("bust", "21", "Bust Limit"),
                            ("tie", "==", "Tie Rule"), ("bust_outcome", "BX", "Bust Pardon"),
                            ("profit_cap", "$|", "Withdrawal Limit"), ("item_ban", "X", "Item Ban"),
                            ("markup", "%+", "Price Hike"), ("hidden", "??", "Face-Down Card")):
    register(AssetSpec("ph_env_" + _type, "rule", ICON, ph.icon(_mark, theme.CHAOS_MAGENTA), _name))


# Membership badges (meta/membership.py; art: scripts/draw_membership_badges.py).
for _level, _color in enumerate(((0x8C, 0x64, 0x3C), (0xA8, 0xB0, 0xB6), theme.GOLD, (0x3E, 0x8E, 0x6E),
                                 theme.CHAOS_MAGENTA), start=1):
    register(AssetSpec(f"member_{_level}", "icon", ICON, ph.icon(str(_level), _color), f"Membership level {_level}"))


# Icons are tinted by product group (theme.GROUP_COLORS); permanents keep the art's gold.
for _product in POKER_HEAD_PRODUCTS.values():
    _group = _product.to_def().group
    register(AssetSpec(_product.id, "item", ICON,
                       ph.icon(_product.id.removeprefix("ph_")[:2].upper(), theme.GROUP_COLORS[_group]),
                       _product.name, tint=None if _group == "permanent" else theme.GROUP_COLORS[_group]))


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
    # Poker Head's deck and table (art: assets/cosmetics/procedural; the rest of his
    # House Collection ships as files in assets/cosmetics/poker_head)
    "card_back_poker_head": ("card", CARD, ph.flower_back((0xA8, 0x36, 0x5A), (0xF4, 0xE4, 0xC8), theme.FELT,
                                                          theme.INK)),
    "card_front_poker_head": ("card", CARD, ph.framed_front((0xF6, 0xEA, 0xD0), (0xA8, 0x36, 0x5A), theme.INK)),
    "table_poker_head": ("background", BG, ph.felt_table((0x2E, 0x46, 0x3A), (0x3A, 0x54, 0x46), (0xB0, 0x96, 0x5A))),
    "card_back_poker_head_gold": ("card", CARD, ph.lattice_back((0x8E, 0x3C, 0x59), (0xD5, 0xB9, 0x75), (0xD5, 0xB9, 0x75),
                                                               (0xB7, 0xA4, 0x77))),
    **{f"chips_poker_head_{v}": ("chip", ICON, ph.chip(c, (0x17, 0x1C, 0x1B))) for v, c in
       {1: (0xF1, 0xE6, 0xD2), 5: (0xA2, 0x3D, 0x43), 10: (0x34, 0x4B, 0x72), 25: (0x3B, 0x65, 0x52)}.items()},
    "avatar_poker_head_j": ("avatar", AVATAR, ph.avatar("bust", (0x1D, 0x30, 0x29), (0xB7, 0xA4, 0x77))),
    **{f"chips_neon_{v}": ("chip", ICON, ph.chip(c, theme.DARK)) for v, c in _NEON.items()},
    **{f"chips_gold_{v}": ("chip", ICON, ph.chip(c, (0x6E, 0x50, 0x1E))) for v, c in _GOLD_CHIPS.items()},
    # J-54's look (art: assets/cosmetics/j54, scripts/generate_j54_theme.py)
    "card_back_j54": ("card", CARD, ph.lattice_back(_J54_BLACK, _J54_RED, _J54_RED, _J54_RED)),
    "card_back_j54_calculator": ("card", CARD, ph.lattice_back(_J54_RED, _J54_BLACK, _J54_BLACK, _J54_BLACK)),
    "card_front_j54": ("card", CARD, ph.framed_front((0xED, 0xE4, 0xD2), _J54_RED, theme.INK)),
    "table_j54": ("background", BG, ph.felt_table(_J54_BLACK, (0x2C, 0x29, 0x2D), _J54_RED)),
    **{f"chips_j54_{v}": ("chip", ICON, ph.chip(c, _J54_BLACK)) for v, c in
       {1: (0xED, 0xE4, 0xD2), 5: _J54_RED, 10: (0x8E, 0x89, 0x85), 25: (0x77, 0x23, 0x2F)}.items()},
    "avatar_j54": ("avatar", AVATAR, ph.avatar("bust", _J54_BLACK, _J54_RED)),
    "avatar_j54_computer": ("avatar", AVATAR, ph.avatar("bust", _J54_RED, _J54_BLACK)),
    "avatar_spade": ("avatar", AVATAR, ph.avatar("spade", theme.DARK, theme.GOLD)),
    "avatar_joker": ("avatar", AVATAR, ph.avatar("flag", (0x3A, 0x2A, 0x44), theme.CHAOS_MAGENTA)),
}


def _skin_name(asset_id: str) -> str:
    """The name of the cosmetic that draws `asset_id` (for asset reports)."""
    return next((c.name for c in cosmetics() if asset_id in c.asset_map().values()), asset_id)


for _id, (_category, _size, _draw) in _SKINS.items():
    register(AssetSpec(_id, _category, _size, _draw, _skin_name(_id)))
