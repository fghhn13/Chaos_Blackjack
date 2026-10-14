"""Passive build effects: cores, permanents and this round's prepared consumables.

Each effect implements only the hooks it needs; the table folds every active
effect over a hook in a fixed order (core, permanents in slot order, then
preparations). Player-only hooks never touch the dealer's values. Adding a
permanent = a catalog row + one class here + a seed row
(docs/design/ITEM_ARCHITECTURE.md §5, §10).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

from chaos_blackjack.app.choice import Move
from chaos_blackjack.app.view import Action, TablePhase
from chaos_blackjack.core.game_state import Card, GameState, Rank

if TYPE_CHECKING:
    from chaos_blackjack.poker_head.context import BuildContext


@dataclass
class Settlement:
    """One hand's cash result while effects adjust it."""

    outcome: str
    bet: int
    doubled: bool
    delta: int            # base result (a surrender's loss, a win's profit, ...)
    cards: int            # cards in the player's final hand
    player_total: int
    round_no: int
    bonus_pct: int = 0    # extra profit on a win, as a % of the final bet
    extra: int = 0        # flat chips added after bonuses (Recovery Receipt)

    @property
    def wins(self) -> bool:
        return self.outcome in ("player", "blackjack")

    def hand(self) -> int:
        """The hand's own result with bonuses (Recovery Receipt's refund not included)."""
        return math.floor(self.delta + self.bet * self.bonus_pct / 100) if self.wins else self.delta

    def final(self) -> int:
        return self.hand() + self.extra


class Effect:
    """Neutral hooks; an effect overrides what it changes."""

    unlocks_finance = False    # financial products may be stocked and bought
    suppresses_chaos = False   # this round plays without Chaos rules
    insures_bust = False       # a player bust lets the dealer play; a dealer bust then makes it a push

    def __init__(self, ctx: "BuildContext", product_id: str) -> None:
        self.ctx = ctx
        self.id = product_id

    def param(self, key: str):
        return self.ctx.param(self.id, key)

    # --- hand values (player only) ------------------------------------------
    def bust_limit(self, limit: int) -> int:
        return limit

    def card_low(self, card: Card, low: int) -> int:
        """A card's lowest value; below its high value it switches like an ace (evaluation.BuildRules.actual)."""
        return low

    def card_value(self, card: Card, value: int) -> int:
        return value

    def recognize(self, total: int) -> int:
        return total

    # --- round ------------------------------------------------------------------
    def opening(self, state: GameState) -> GameState:
        """The opening cards were dealt, before naturals are checked."""
        return state

    def natural(self, player: bool, dealer: bool) -> str | None:
        return None

    def player_turn(self) -> None:
        """Your turn began, or a card or item changed it."""

    def actions(self, actions: set[str]) -> None:
        """Add or remove hand actions (in place)."""

    def table_moves(self) -> tuple[Move, ...]:
        return ()

    def perform(self, action: str) -> bool:
        """Run one of this effect's moves; False when it is not this effect's."""
        return False

    def double_multiplier(self, multiplier: int) -> int:
        return multiplier

    def surrender_rate(self, rate: int) -> int:
        return rate

    def settle(self, s: Settlement) -> None:
        pass

    def removed(self) -> None:
        """The permanent was replaced: drop what it was holding for later."""

    # --- shop and money -----------------------------------------------------------
    def price_factor(self, kind: str) -> Fraction:
        """Multiplier on a product's base price (prices are rounded up once, after every factor)."""
        return Fraction(1)

    def shop_slots(self, slots: int) -> int:
        return slots

    def free_rerolls(self, count: int) -> int:
        return count

    def investment_profit(self, profit: int) -> int:
        return profit


EFFECTS: dict[str, type[Effect]] = {}


def effect(*ids: str):
    def register(cls: type[Effect]) -> type[Effect]:
        for item_id in ids:
            EFFECTS[item_id] = cls
        return cls
    return register


def build_effect(ctx: "BuildContext", product_id: str) -> Effect:
    return EFFECTS.get(product_id, Effect)(ctx, product_id)


# --- cores (Room to Breathe, Fresh Hand and Private Account here; Exit Clause and Raise Permission below)


@effect("ph_margin")
class RoomToBreathe(Effect):
    def bust_limit(self, limit):
        return limit + self.ctx.setting("margin_bonus")


@effect("ph_retreat")
class GracefulRetreat(Effect):
    def surrender_rate(self, rate):
        return self.ctx.setting("surrender_pct")


@effect("ph_approx")
class AlmostPerfect(Effect):
    # Naturals use the two original cards (GameController._is_natural), so 20/22 never make one.
    def recognize(self, total):
        return 21 if total in self.ctx.setting("approx_values") else total


@effect("ph_stakes")
class HighStakes(Effect):
    def settle(self, s):
        if s.doubled and s.wins:
            s.bonus_pct += self.ctx.setting("double_bonus_pct")


@effect("ph_redeal")
class FreshHand(Effect):
    """Core: once per round, before your first action, both opening cards go and the next two come in."""

    ACTION = "ph_redeal"

    def table_moves(self):
        if self.ctx.phase != TablePhase.PLAYER_TURN:
            return ()
        reason = ("Used this round." if self.id in self.ctx.round.used
                  else "Only before your first action." if len(self.ctx.player_hand) != 2
                  else "" if len(self.ctx.deck) >= 2 else "The deck is running out.")
        return (Move(self.ACTION, "", "Use Fresh Hand", not reason, reason),)

    def perform(self, action):
        if action != self.ACTION:
            return False
        state = self.ctx.state
        self.ctx.set_state(state.with_player_hand(tuple(state.deck[:2])).with_deck(state.deck[2:]))
        self.ctx.round.used.append(self.id)
        self.ctx.table.deck_changed()
        self.ctx.message("Fresh Hand: your opening cards were swapped for the next two.")
        return True


@effect("ph_account")
class PrivateAccount(Effect):
    unlocks_finance = True

    def shop_slots(self, slots):
        return slots + self.ctx.setting("extra_shop_slots")


# --- multi-card -----------------------------------------------------------------------


@effect("ph_long_reward", "ph_five_reward")
class CardCountReward(Effect):
    def settle(self, s):
        if s.wins and s.cards >= self.param("cards"):
            s.bonus_pct += self.param("bonus_pct")


@effect("ph_court")
class CourtDiscount(Effect):
    # J, Q and K switch like aces: their value, or `value` when that keeps the hand from busting.
    def card_low(self, card, low):
        return min(low, self.param("value")) if str(card.rank).upper() in ("J", "Q", "K") else low


@effect("ph_mark")
class SleeveMark(Effect):
    def player_turn(self):
        r = self.ctx.round
        if self.id not in r.used and self.ctx.deck:
            r.used.append(self.id)
            r.shown = [str(self.ctx.deck[0].rank)]
            self.ctx.message(f"Sleeve Mark: the next rank is {r.shown[0]}.")


# --- surrender ------------------------------------------------------------------------


@effect("ph_late_retreat")
class ExitClause(Effect):
    def actions(self, actions):
        if self.ctx.table.config.allow_surrender:
            actions.add(Action.SURRENDER)


@effect("ph_loss_discount")
class RetreatDiscount(Effect):
    def surrender_rate(self, rate):
        return max(self.param("minimum_pct"), rate - self.param("discount_pct"))


@effect("ph_claim")
class RecoveryReceipt(Effect):
    def settle(self, s):
        t = self.ctx.table
        claim = t.claim
        if claim and claim["round"] == s.round_no:
            if s.wins:
                s.extra += claim["refund"]
                self.ctx.message(f"Recovery Receipt returns {claim['refund']} chips.")
            t.claim = None
        if s.outcome == "surrender" and s.delta < 0:  # only a paid surrender (never Loss Waiver)
            refund = math.ceil(s.bet * self.ctx.setting("base_surrender_pct") / 100)
            t.claim = {"round": s.round_no + 1, "refund": refund}

    def removed(self):
        self.ctx.table.claim = None


@effect("ph_ace")
class ComebackAce(Effect):
    def opening(self, state):
        t = self.ctx.table
        if not t.ace_pending or not state.player_hand:
            return state
        t.ace_pending = False
        first = state.player_hand[0]
        self.ctx.message("Comeback Ace: your first opening card is an ace.")
        return state.with_player_hand((Card(Rank("A"), first.suit),) + state.player_hand[1:])

    def settle(self, s):
        if s.outcome == "surrender":
            self.ctx.table.ace_pending = True

    def removed(self):
        self.ctx.table.ace_pending = False


# --- precision ---------------------------------------------------------------------------


@effect("ph_jackpot")
class PerfectPayout(Effect):
    def settle(self, s):
        if s.wins and (s.outcome == "blackjack" or s.player_total == 21):
            s.delta = s.bet * self.param("multiplier")


@effect("ph_sleeve")
class SpareSleeve(Effect):
    ACTION = "ph_sleeve"

    def table_moves(self):
        if self.ctx.phase != TablePhase.PLAYER_TURN:
            return ()
        reason = ("Used this round." if self.id in self.ctx.round.used
                  else "" if self.ctx.deck else "The deck is empty.")
        return (Move(self.ACTION, "", "Use Spare Sleeve", not reason, reason),)

    def perform(self, action):
        if action != self.ACTION:
            return False
        state = self.ctx.state
        self.ctx.set_state(state.with_player_hand((state.deck[0],) + state.player_hand[1:]).with_deck(state.deck[1:]))
        self.ctx.round.used.append(self.id)
        self.ctx.table.deck_changed()
        self.ctx.message("Spare Sleeve: your first card was replaced.")
        return True


@effect("ph_borrow")
class BorrowedGlory(Effect):
    def natural(self, player, dealer):
        if dealer:
            self.ctx.message("Borrowed Glory: the dealer's opening blackjack is your win.")
            return "blackjack"
        return None


# --- double -----------------------------------------------------------------------------------


@effect("ph_late_double")
class RaisePermission(Effect):
    def actions(self, actions):
        hand = self.ctx.player_hand
        if (self.ctx.table.config.allow_double and len(hand) > 2
                and self.ctx.cash >= self.ctx.bet * self.ctx.table.double_cover()):
            actions.add(Action.DOUBLE)


@effect("ph_risk")
class SharedRisk(Effect):
    def settle(self, s):
        if s.outcome == "dealer" and s.doubled:
            s.delta = -math.ceil(s.bet * (100 - self.param("discount_pct")) / 100)


@effect("ph_audit")
class OpenAudit(Effect):
    def player_turn(self):
        hand = self.ctx.dealer_hand
        if len(hand) < 2 or self.ctx.hole_revealed:
            return
        if self.ctx.dealer_hole_value() >= self.param("threshold"):
            self.ctx.reveal_hole()
            self.ctx.message("Open Audit reveals the dealer's hole card.")


# --- finance ---------------------------------------------------------------------------


@effect("ph_discount")
class PurchasingPrivilege(Effect):
    def price_factor(self, kind):
        if kind == "finance":
            return Fraction(1)
        return Fraction(100 - self.param("discount_pct"), 100)


@effect("ph_yield")
class YieldPrivilege(Effect):
    def investment_profit(self, profit):
        return math.floor(profit * (100 + self.param("bonus_pct")) / 100) if profit > 0 else profit


@effect("ph_refresh")
class PriorityExchange(Effect):
    def free_rerolls(self, count):
        return count + 1


# --- prepared consumables (this round only) ---------------------------------------------


@effect("ph_buffer")
class TemporaryAllowance(Effect):
    def bust_limit(self, limit):
        return limit + self.param("bonus")


@effect("ph_insurance")
class BustInsurance(Effect):
    insures_bust = True


@effect("ph_silence")
class SilenceSeal(Effect):
    suppresses_chaos = True


@effect("ph_quad")
class FourfoldTicket(Effect):
    def double_multiplier(self, multiplier):
        return self.param("multiplier")


@effect("ph_waiver")
class LossWaiver(Effect):
    def surrender_rate(self, rate):
        return 0
