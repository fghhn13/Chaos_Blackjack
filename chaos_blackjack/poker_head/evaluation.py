"""One actor-aware evaluation for play, forecasts, public totals and settlement.

Order for every card (docs/design/POKER_HEAD_CHAOS_RULES_AND_AGENT.zh-CN.md §4.1):
printed value → environment fixed rewrite → environment shifts → (legacy Chaos
modifiers) → the player's build effects (player only) → ace high/low choice →
recognition (Almost Perfect, player only) → bust check against the actor's
limit. Naturals use the two original cards and never come through here.

Everything that values a hand — the bust check, the outcome, Risk Pointer,
Open Audit, the GUI total — goes through this one engine.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.poker_head import environment as env
from chaos_blackjack.rules.rule_engine import BLACKJACK, DefaultBlackjackRules, RuleContext, bust_limit

if TYPE_CHECKING:
    from chaos_blackjack.poker_head.table import PokerHeadTable


class BuildRules(DefaultBlackjackRules):
    def __init__(self, table: "PokerHeadTable", base) -> None:
        self.table = table
        self.base = base

    def _env(self) -> tuple[env.EnvRule, ...]:
        return self.table.env_rules()

    # --- limits and recognition ---------------------------------------------------------------
    def limit(self, ctx: RuleContext) -> int:
        """The actor's bust limit: the environment's base (or a legacy Chaos limit), plus the player's build."""
        legacy = bust_limit(ctx)
        limit = env.base_bust_limit(ctx.actor, self._env(), BLACKJACK)
        limit = min(limit, legacy) if legacy < BLACKJACK else limit
        if ctx.actor == "player":
            for e in self.table.effects():
                limit = e.bust_limit(limit)
        return limit

    def recognize(self, total: int, ctx: RuleContext) -> int:
        if ctx.actor == "player":
            for e in self.table.effects():
                total = e.recognize(total)
        return total

    # --- card values -------------------------------------------------------------------------------
    def card_range(self, card: Card, ctx: RuleContext) -> tuple[int, int]:
        """(high, low) of one card for the actor; equal unless it is a switching ace."""
        high, low = env.card_values(card, ctx.actor, self._env())
        for m in ctx.modifiers.items:  # legacy Chaos modifiers (until the director replaces them)
            high, low = m.adjust_rank_value(card, high), m.adjust_rank_value(card, low)
        if ctx.actor == "player":
            for e in self.table.effects():
                high, low = e.card_value(card, high), e.card_value(card, low)
            for e in self.table.effects():
                low = e.card_low(card, low)
        return high, low

    def card_value(self, card: Card, ctx: RuleContext) -> int:
        """A card's high value (a switching ace counts high)."""
        return self.card_range(card, ctx)[0]

    def actual(self, hand: tuple[Card, ...], ctx: RuleContext) -> int:
        """The total before recognition; switching aces drop to low while the hand would bust."""
        ranges = [self.card_range(card, ctx) for card in hand]
        total = sum(high for high, _ in ranges)
        drops = sorted((high - low for high, low in ranges if high > low), reverse=True)
        limit = self.limit(ctx)
        for drop in drops:
            if self.recognize(total, ctx) <= limit:
                break
            total -= drop
        return total

    def hand_value(self, hand: tuple[Card, ...], ctx: RuleContext) -> int:
        return self.recognize(self.actual(hand, ctx), ctx)

    def is_bust(self, value: int, ctx: RuleContext) -> bool:
        return value > self.limit(ctx)

    # --- outcome -------------------------------------------------------------------------------------
    def compare_player_dealer(self, state, ctx: RuleContext) -> str:
        pc, dc = replace(ctx, actor="player"), replace(ctx, actor="dealer")
        p, d = self.hand_value(state.player_hand, pc), self.hand_value(state.dealer_hand, dc)
        rules = self._env()
        flags = ctx.modifiers.chaos_flags()
        if self.is_bust(p, pc):
            result = env.bust_result("player", rules)
            if result is None and any(e.insures_bust for e in self.table.effects()):  # Bust Insurance
                result = "push" if self.is_bust(d, dc) else "dealer"
            return result or ("push" if "reverse_bust" in flags else "dealer")
        if self.is_bust(d, dc):
            return env.bust_result("dealer", rules) or "player"
        if p != d:
            return "player" if p > d else "dealer"
        result = env.tie_result(rules)
        if result is not None:
            return result
        if "player_wins_ties" in flags:
            return "player"
        return "dealer" if "dealer_wins_ties" in flags else "push"
