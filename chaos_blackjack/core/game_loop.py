"""Turn orchestration — wires events, rules, and chaos without collapsing layers."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from chaos_blackjack.ai.chaos_agent import ChaosAgent, ChaosObservation, NoOpChaosAgent
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.events.dispatcher import EventDispatcher
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.rule_engine import DefaultBlackjackRules, RuleContext, RuleEngine


def _standard_deck() -> list[Card]:
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    return [Card(Rank(r), "") for r in ranks for _ in range(4)]


def _shuffle(cards: list[Card], rng: random.Random) -> tuple[Card, ...]:
    rng.shuffle(cards)
    return tuple(cards)


@dataclass
class GameLoop:
    """High-level loop; swap `rules`, `chaos`, or event wiring via subclassing."""

    rules: RuleEngine = field(default_factory=DefaultBlackjackRules)
    chaos: ChaosAgent = field(default_factory=NoOpChaosAgent)
    modifiers: ActiveModifiers = field(default_factory=ActiveModifiers)
    rng: random.Random = field(default_factory=random.Random)
    dispatcher: EventDispatcher | None = None

    def new_round(self, seed: int | None = None) -> GameState:
        if seed is not None:
            self.rng.seed(seed)
        deck = list(_standard_deck())
        deck_t = _shuffle(deck, self.rng)
        p1, p2, d1, d2, *rest = deck_t
        return GameState(
            player_hand=(p1, p2),
            dealer_hand=(d1, d2),
            deck=tuple(rest),
            phase=GamePhase.PLAYER_TURN,
        )

    def _emit(self, event: Event) -> None:
        if self.dispatcher is not None:
            self.dispatcher.dispatch(event)

    def _draw(self, state: GameState, to_player: bool) -> GameState:
        if not state.deck:
            return state
        card, *rest = state.deck
        new_deck = tuple(rest)
        self._emit(
            Event(EventType.DRAW_CARD, {"to_player": to_player, "rank": card.rank}),
        )
        if to_player:
            return state.with_deck(new_deck).with_player_hand(state.player_hand + (card,))
        return state.with_deck(new_deck).with_dealer_hand(state.dealer_hand + (card,))

    def _apply_chaos(self, state: GameState) -> None:
        obs = ChaosObservation(state=state, modifiers=self.modifiers)
        mod = self.chaos.maybe_propose_modifier(obs)
        if mod is not None:
            self.modifiers = self.modifiers.with_added(mod)

    def context(self) -> RuleContext:
        return RuleContext(modifiers=self.modifiers)

    def player_should_hit_simple(self, state: GameState) -> bool:
        """Placeholder AI for demo — replace with UI / policy."""
        v = self.rules.hand_value(state.player_hand, self.context())
        return v < 17

    def run_round_until_done(self, state: GameState) -> GameState:
        """Automated demo: player hits until >=17, then dealer draws on soft 17 rule <17."""
        self._emit(Event(EventType.TURN_START, {"phase": state.phase.name}))
        self._apply_chaos(state)
        s = state
        while s.phase == GamePhase.PLAYER_TURN:
            self._apply_chaos(s)
            pv = self.rules.hand_value(s.player_hand, self.context())
            if self.rules.is_bust(pv):
                return s.with_phase(GamePhase.RESOLVED)
            if self.player_should_hit_simple(s):
                s = self._draw(s, to_player=True)
            else:
                s = s.with_phase(GamePhase.DEALER_TURN)
                break

        while s.phase == GamePhase.DEALER_TURN:
            dv = self.rules.hand_value(s.dealer_hand, self.context())
            if self.rules.is_bust(dv):
                return s.with_phase(GamePhase.RESOLVED)
            if dv >= 17:
                return s.with_phase(GamePhase.RESOLVED)
            s = self._draw(s, to_player=False)

        return s.with_phase(GamePhase.RESOLVED)

    def outcome_label(self, state: GameState) -> str:
        return self.rules.compare_player_dealer(state, self.context())
