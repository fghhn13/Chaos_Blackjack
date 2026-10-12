"""Cosmetics — unlockable looks for the card back, table, chip set and avatar.

A cosmetic only changes art: it maps a slot's base asset ids to its own asset
ids, and the GUI's AssetManager draws those instead. Game logic, RunConfig and
the agent CLI never see cosmetics. Contract:
docs/design/COSMETICS_ACHIEVEMENTS.md §3.

Adding one is a `register_cosmetic` entry (catalog.py or a content pack) plus
its art; selling it is a `cosmetic_price` row in the balance profile, and an
achievement can reward it through `achievement_reward`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COSMETIC_SLOTS = ("card_back", "table", "chips", "avatar")

# Base asset ids each slot replaces.
SLOT_ASSETS: dict[str, tuple[str, ...]] = {
    "card_back": ("card_back",),
    "table": ("table_background",),
    "chips": ("chip_1", "chip_5", "chip_10", "chip_25"),
    "avatar": ("avatar",),
}

SLOT_LABELS = {"card_back": "Card backs", "table": "Tables", "chips": "Chips", "avatar": "Avatars"}
RARITIES = ("common", "rare", "epic", "legendary")


@dataclass(frozen=True)
class Cosmetic:
    id: str                       # unique across slots
    slot: str                     # one of COSMETIC_SLOTS
    name: str
    description: str = ""
    rarity: str = "common"        # display only
    assets: dict[str, str] = field(default_factory=dict)  # base asset id -> asset id; empty: the base ids
    preview: str | None = None    # wardrobe tile asset id; None: the slot's first asset
    default: bool = False         # owned by every player
    hidden: bool = False          # not listed until owned
    order: int = 0

    def asset_map(self) -> dict[str, str]:
        """Every base asset id of the slot -> the asset id this cosmetic draws."""
        return {base: self.assets.get(base, base) for base in SLOT_ASSETS[self.slot]}

    @property
    def preview_asset(self) -> str:
        return self.preview or self.asset_map()[SLOT_ASSETS[self.slot][0]]


_COSMETICS: dict[str, Cosmetic] = {}


def register_cosmetic(c: Cosmetic) -> Cosmetic:
    """Add or replace (same id) a cosmetic."""
    if c.slot not in SLOT_ASSETS:
        raise ValueError(f"Cosmetic {c.id!r}: unknown slot {c.slot!r}; slots: {', '.join(COSMETIC_SLOTS)}")
    unknown = set(c.assets) - set(SLOT_ASSETS[c.slot])
    if unknown:
        raise ValueError(f"Cosmetic {c.id!r}: {sorted(unknown)} are not {c.slot} assets")
    if c.rarity not in RARITIES:
        raise ValueError(f"Cosmetic {c.id!r}: rarity must be one of {', '.join(RARITIES)}")
    _COSMETICS[c.id] = c
    return c


def get_cosmetic(cosmetic_id: str) -> Cosmetic | None:
    return _COSMETICS.get(cosmetic_id)


def cosmetics(slot: str | None = None) -> list[Cosmetic]:
    """Registered cosmetics (of one slot), defaults first, then by order and name."""
    found = [c for c in _COSMETICS.values() if slot is None or c.slot == slot]
    return sorted(found, key=lambda c: (COSMETIC_SLOTS.index(c.slot), not c.default, c.order, c.name, c.id))


def default_cosmetic(slot: str) -> Cosmetic:
    """The slot's default look (the last registered default wins)."""
    found = [c for c in _COSMETICS.values() if c.slot == slot and c.default]
    if not found:
        raise KeyError(f"No default cosmetic for slot {slot!r}")
    return found[-1]


from chaos_blackjack.cosmetics import catalog as _catalog  # noqa: E402,F401  (registers the built-ins)

__all__ = [
    "COSMETIC_SLOTS", "RARITIES", "SLOT_ASSETS", "SLOT_LABELS", "Cosmetic", "cosmetics", "default_cosmetic",
    "get_cosmetic", "register_cosmetic",
]
