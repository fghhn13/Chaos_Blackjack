"""Read-only snapshot of everything a front-end needs to draw one frame."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from chaos_blackjack.logic.run_end_policy import RunEndResult


class TablePhase(Enum):
    BETTING = "betting"          # waiting for place_bet(); the shop is open
    CHAOS = "chaos"              # waiting for resolve_chaos() (may call an LLM)
    PLAYER_TURN = "player_turn"  # hit / stand / use_item
    DEALER_TURN = "dealer_turn"  # dealer_step() until it returns False
    ROUND_OVER = "round_over"    # result shown; next_round()
    RUN_OVER = "run_over"        # victory or defeat; terminal


class Action:
    """Action ids a front-end can bind to buttons / keys."""

    BET = "bet"
    BUY = "buy"
    REROLL = "reroll"  # roll the shop's current stock again (once per stock)
    RESOLVE_CHAOS = "resolve_chaos"
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SURRENDER = "surrender"
    USE_ITEM = "use_item"
    DEALER_STEP = "dealer_step"
    NEXT_ROUND = "next_round"
    SAVE = "save"


@dataclass(frozen=True)
class CardView:
    rank: str
    suit: str
    face_up: bool = True


@dataclass(frozen=True)
class ItemView:
    id: str
    count: int
    description: str = ""


@dataclass(frozen=True)
class ShopOfferView:
    item: str
    price: int
    sold: bool
    affordable: bool  # unsold and the bankroll can still place a bet afterwards
    description: str = ""


@dataclass(frozen=True)
class RuleView:
    id: str
    description: str


@dataclass(frozen=True)
class RoundResult:
    round: int
    outcome: str  # "player" | "dealer" | "push" | "blackjack" | "surrender"
    player_total: int
    dealer_total: int
    player_bust: bool
    bet: int
    delta: int
    money_after: int
    doubled: bool = False
    dealer_blackjack: bool = False


@dataclass(frozen=True)
class GameView:
    phase: TablePhase
    round: int
    money: int
    start_money: int
    target_money: int
    objective: str
    current_bet: int
    bet_min: int
    bet_max: int
    win_streak: int

    player_cards: tuple[CardView, ...]
    dealer_cards: tuple[CardView, ...]
    player_total: int | None
    dealer_total: int | None  # None while the hole card is hidden
    deck_count: int

    items: tuple[ItemView, ...]
    shop_offers: tuple[ShopOfferView, ...]
    shop_restock_in: int  # rounds until the shop rolls new stock
    hole_revealed: bool   # the dealer's hole card was exposed by an item

    chaos_enabled: bool
    chaos_budget: int
    active_rules: tuple[RuleView, ...]
    narration: str | None

    available_actions: frozenset[str]
    last_result: RoundResult | None
    run_end: RunEndResult | None
    # Chips the next reroll costs (0 = free), or None when this stock cannot be rerolled.
    shop_reroll_price: int | None = None
    # A mode's own mechanics (e.g. J-54): (label, value) rows to show, and the
    # chips charged before this round's bet.
    table_info: tuple[tuple[str, str], ...] = ()
    fee: int = 0

    def can(self, action: str) -> bool:
        return action in self.available_actions
