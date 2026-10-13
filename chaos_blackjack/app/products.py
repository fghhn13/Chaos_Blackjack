"""Product catalog — what a table sells or grants, as data (docs/design/ITEM_ARCHITECTURE.md).

A product row names a thing once: its English name and effect text, its kind
and the phases a consumable may be used in. Prices and effect numbers live in
the balance profile, never here. Tables register their rows; the controller,
the GUI and the agent read names, descriptions and phase labels from this
catalog instead of asking each table.

    register_products(rows)
    product("ph_peek").when   # "On your turn"
"""

from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("consumable", "permanent", "finance", "core", "contract")
# Display groups: icon colour and frame (gui/theme.py GROUP_COLORS).
GROUPS = ("permanent", "consumable", "special")
BETTING, PLAYER_TURN = "betting", "player_turn"

_KIND_LABELS = {"consumable": "Consumable", "permanent": "Permanent", "finance": "Finance",
                "core": "Core", "contract": "Contract"}


@dataclass(frozen=True)
class ProductDef:
    id: str
    name: str
    kind: str
    description: str
    style: str = ""
    phases: frozenset[str] = field(default_factory=frozenset)
    target: str = ""  # what a use must choose: "", rule, holding, core
    system: bool = False  # a management item (e.g. a core invitation) shown with the special group

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Product {self.id}: unknown kind {self.kind!r}")
        if not self.phases <= {BETTING, PLAYER_TURN}:
            raise ValueError(f"Product {self.id}: unknown phases {sorted(self.phases)}")

    @property
    def kind_label(self) -> str:
        return _KIND_LABELS[self.kind]

    @property
    def group(self) -> str:
        """permanent, consumable or special (cores, money products, contracts, system items)."""
        if self.kind == "permanent":
            return "permanent"
        if self.kind == "consumable" and not self.system:
            return "consumable"
        return "special"

    @property
    def when(self) -> str:
        """When the product acts, in a few English words."""
        if self.kind == "consumable":
            return phase_label(self.phases)
        if self.kind == "finance":
            return "Buy before betting"
        return "Passive"


def phase_label(phases: frozenset[str]) -> str:
    if phases == {BETTING, PLAYER_TURN}:
        return "Before betting or on your turn"
    if phases == {BETTING}:
        return "Before betting"
    if phases == {PLAYER_TURN}:
        return "On your turn"
    return "Not usable"


_PRODUCTS: dict[str, ProductDef] = {}


def register_products(rows) -> None:
    for row in rows:
        _PRODUCTS[row.id] = row


def product(item_id: str) -> ProductDef | None:
    """The catalog row of an id (None for items outside the catalog, e.g. the
    classic item plugins). A table may map other ids to its rows
    (`TableMechanics.product`, e.g. Poker Head's starter aliases)."""
    _load_builtin_products()
    return _PRODUCTS.get(item_id)


def _load_builtin_products() -> None:
    import chaos_blackjack.poker_head.catalog  # noqa: F401  (registers ph_*)
