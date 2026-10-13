"""Poker Head's 41 build products, declared once (docs/design/POKER_HEAD_EFFECTS.zh-CN.md).

Each row is (key, English name, kind, style, effect text[, phases]); phases
are "B" (before betting) and "P" (on your turn) for consumables. Prices and
effect numbers come from the balance profile (`shop_item` rows,
`mode.chaos.*` settings), never from here.

`PRODUCTS` keeps this compact shape for the codex reference
(codex/build_reference.py); the same rows are registered in the shared
catalog (app/products.py) as `ProductDef`s, which the controller, GUI and
agent read. Behaviour lives in effects.py (cores and permanents) and
items.py (consumables).
"""

from dataclasses import dataclass

from chaos_blackjack.app.products import BETTING, PLAYER_TURN, ProductDef, register_products


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    kind: str          # core | permanent | item | finance
    style: str
    description: str
    phases: str = ""   # "B", "P" or "BP" for consumables

    def to_def(self) -> ProductDef:
        phases = frozenset({BETTING} if "B" in self.phases else set()) | frozenset(
            {PLAYER_TURN} if "P" in self.phases else set())
        return ProductDef(self.id, self.name, "consumable" if self.kind == "item" else self.kind, self.description,
                          self.style, phases if self.kind == "item" else frozenset(), _TARGETS.get(self.id, ""),
                          system=self.id in SYSTEM)


# Management items: they change the build itself, so they show with the special group.
SYSTEM = ("ph_gift", "ph_change")
_TARGETS = {"ph_gift": "core", "ph_change": "core", "ph_remove": "rule", "ph_buyback": "holding"}

_ROWS = (
    ("margin", "Room to Breathe", "core", "long", "Raise your bust limit by one."),
    ("retreat", "Graceful Retreat", "core", "retreat", "Surrender loses only 20% of your bet."),
    ("approx", "Almost Perfect", "core", "exact", "After natural settlement, your 20 and 22 count as 21."),
    ("stakes", "High Stakes", "core", "double", "A doubled win earns another 25% of the final bet."),
    ("account", "Private Account", "core", "finance", "An extra shop slot and access to financial products."),
    ("long_reward", "Long Hand Dividend", "permanent", "long", "Win with four or more cards for another 20% of the bet."),
    ("court", "Court Discount", "permanent", "long", "Your J, Q and K count as five."),
    ("five_reward", "Five Card Feast", "permanent", "long", "Win with five or more cards for another full bet."),
    ("mark", "Sleeve Mark", "permanent", "long", "See the next rank when your turn begins."),
    ("late_retreat", "Exit Clause", "permanent", "retreat", "You may surrender after hitting, before busting."),
    ("loss_discount", "Retreat Discount", "permanent", "retreat", "Surrender loses ten percentage points less; minimum 10%."),
    ("claim", "Recovery Receipt", "permanent", "retreat", "Pay a surrender loss; win the next hand to recover the undiscounted fee."),
    ("ace", "Comeback Ace", "permanent", "retreat", "After surrendering, your next hand starts with an ace."),
    ("jackpot", "Perfect Payout", "permanent", "exact", "A winning 21 pays three times your final bet."),
    ("sleeve", "Spare Sleeve", "permanent", "exact", "One free replacement of your first card each round.", "P"),
    ("borrow", "Borrowed Glory", "permanent", "exact", "The dealer's starting blackjack becomes your starting win."),
    ("late_double", "Raise Permission", "permanent", "double", "You may double after hitting."),
    ("risk", "Shared Risk", "permanent", "double", "Lose a doubled hand and pay only 75% of the final bet."),
    ("audit", "Open Audit", "permanent", "double", "Automatically reveal a dealer hole card worth at least ten."),
    ("discount", "Purchasing Privilege", "permanent", "finance", "Shop goods cost 10% less; investments and debt are excluded."),
    ("yield", "Yield Privilege", "permanent", "finance", "Increase positive investment profit by 25%."),
    ("refresh", "Priority Exchange", "permanent", "finance", "One extra free shop refresh per restock.", "B"),
    ("gift", "The Dealer's Invitation", "item", "common", "Choose one of two cores, or take 30 chips and no core this run.", "B"),
    ("change", "Amendment Letter", "item", "common", "Choose one of two new cores; keep your purchased goods.", "B"),
    ("peek", "Card Lens", "item", "long", "Reveal the next rank.", "P"),
    ("swap", "Sleeve Clip", "item", "long", "Replace your first card with the next deck card.", "P"),
    ("hole", "Hole Probe", "item", "retreat", "Reveal the dealer's hole card.", "P"),
    ("radar", "Risk Pointer", "item", "common", "Check whether your next hit would bust under the current effects.", "P"),
    ("oracle", "Fate Forecast", "item", "common", "Before betting, see the first two cards left after the initial deal.", "B"),
    ("remove", "Clause Removal", "item", "common", "Remove one persistent Chaos rule of your choice.", "BP"),
    ("silence", "Silence Seal", "item", "common", "Suppress all Chaos rules for this round, including new ones.", "BP"),
    ("buffer", "Temporary Allowance", "item", "long", "Raise your bust limit by two for this round.", "BP"),
    ("waiver", "Loss Waiver", "item", "retreat", "Surrender without a loss; no recovery receipt is created.", "P"),
    ("aces", "Aces to the Top", "item", "exact", "Move all remaining aces to the top, retaining their order.", "P"),
    ("undo", "Card Recall", "item", "exact", "Remove your last card; keep at least two.", "P"),
    ("quad", "Fourfold Ticket", "item", "double", "Your next double this round stakes four times the original bet.", "BP"),
    ("buyback", "Original Price Receipt", "item", "double", "Return another consumable for its actual purchase price; check victory at once.", "B"),
    ("deposit", "Fixed Deposit", "finance", "finance", "Invest 30; receive 40 after two rounds."),
    ("bond", "Performance Bond", "finance", "finance", "Invest 20; win two of three rounds for 45, otherwise receive 10."),
    ("stock", "Risk Stock", "finance", "finance", "Invest 30; after two rounds, a 50% chance of 90, otherwise nothing."),
    ("loan", "Short Loan", "finance", "finance", "Receive 40 now; repay 50 after three rounds. One loan at a time."),
)


PRODUCTS = {"ph_" + r[0]: Product("ph_" + r[0], *r[1:]) for r in _ROWS}
CORES = tuple(p.id for p in PRODUCTS.values() if p.kind == "core")
PERMANENTS = tuple(p.id for p in PRODUCTS.values() if p.kind == "permanent")
SHOP_IDS = tuple(p.id for p in PRODUCTS.values() if p.kind != "core" and p.id != "ph_gift")
# One slot of every stock prefers one of these general consumables.
COMMON = ("ph_peek", "ph_swap", "ph_hole", "ph_radar", "ph_oracle", "ph_remove", "ph_silence")
# Older starter items (meta progression) play as their Poker Head counterparts at this table.
ALIASES = {"peek": "ph_peek", "swap": "ph_swap", "hole_card_hacker": "ph_hole", "danger_radar": "ph_radar",
           "fate_oracle": "ph_oracle", "shield": "ph_silence"}

register_products(p.to_def() for p in PRODUCTS.values())


def product(item_id: str) -> Product | None:
    return PRODUCTS.get(ALIASES.get(item_id, item_id))


def canonical(item_id: str) -> str:
    return ALIASES.get(item_id, item_id)
