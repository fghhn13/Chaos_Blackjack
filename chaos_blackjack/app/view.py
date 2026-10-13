"""Read-only snapshot of everything a front-end needs to draw one frame."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from chaos_blackjack.app.choice import Choice, Move
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
    CHOOSE = "choose"  # answer the pending choice
    CANCEL = "cancel"  # drop the pending choice (when it allows it)


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
    usable: bool = False   # it can be used right now
    name: str = ""         # display name ("" = derive from the id)
    when: str = ""         # when it can be used, e.g. "Before betting"
    reason: str = ""       # why it cannot be used now
    group: str = ""        # permanent | consumable | special (icon colour); "" for plain items
    note: str = ""         # a remark that applies now (e.g. an item ban)


@dataclass(frozen=True)
class ShopOfferView:
    item: str
    price: int
    sold: bool
    affordable: bool  # it can be bought right now (unsold, allowed, leaves enough to bet)
    description: str = ""
    name: str = ""
    kind: str = ""    # catalog kind (consumable, permanent, finance, ...); "" for plain items
    when: str = ""
    reason: str = ""  # why it cannot be bought now
    group: str = ""   # permanent | consumable | special (icon colour); "" for plain items
    base_price: int | None = None  # before markups and discounts (None when it equals `price`)
    price_note: str = ""           # why the price differs, e.g. "+20% Price Hike, −10% Purchasing Privilege"


class TablePublic(Protocol):
    """A table's public snapshot (frozen dataclass): what any player may see."""

    kind: str

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RuleView:
    id: str
    description: str          # everything about the rule in one paragraph
    name: str = ""            # display name ("" = derive from the id)
    effect: str = ""          # what it does
    scope: str = ""           # what it acts on (e.g. "Both hands", "The shop")
    remaining: int | None = None   # rounds left including this one; None = until removed or replaced
    removal: str = ""         # how it goes away
    silenced: bool = False    # suppressed this round (e.g. Silence Seal)
    icon: str = ""            # asset id ("" = the id)


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
    # (rank, cards) of the whole deck when the table makes it public (J-54); () elsewhere.
    deck_counts: tuple[tuple[str, int], ...] = ()
    # Everything the player can do now (app/choice.py); GUI and agent derive legality from it.
    moves: tuple[Move, ...] = ()
    choice: Choice | None = None          # the pending question, if any
    table_public: TablePublic | None = None
    # (label, value, target) of a goal that is not the bankroll (Poker Head: net assets); None = bankroll/target.
    goal: tuple[str, int, int] | None = None
    # Whether the Chaos AI's action budget applies (False at a table whose own director changes the rules).
    chaos_budget_shown: bool = True

    def move(self, action: str, arg: str = "") -> Move | None:
        return next((m for m in self.moves if m.action == action and m.arg == arg), None)

    def can(self, action: str) -> bool:
        return action in self.available_actions
