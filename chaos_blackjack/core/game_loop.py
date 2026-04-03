"""Turn orchestration — registry-driven chaos pipeline; no direct plugin imports."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field

from chaos_blackjack.contracts.llm import LLMBackend
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.events.dispatcher import EventDispatcher
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.rules.modifiers import ActiveModifiers
from chaos_blackjack.rules.rule_engine import DefaultBlackjackRules, RuleContext, RuleEngine


def _env_truthy(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _default_llm() -> LLMBackend:
    # Lazy imports avoid circular import: core → ai → pipeline → contracts → core
    from chaos_blackjack.ai.gemini_llm import try_create_gemini_llm
    from chaos_blackjack.ai.pipeline import StubLLM

    # Default: stub only (no network). Set CHAOS_USE_GEMINI=1 to use Gemini when key is in .env.
    if _env_truthy("CHAOS_USE_GEMINI"):
        llm = try_create_gemini_llm()
        if llm is not None:
            return llm
    return StubLLM(
        response_json='{"action":"apply_rule","rule_id":"modify_card_value","params":{"delta":-1}}',
    )


def _default_pipeline() -> "ChaosPipeline":
    from chaos_blackjack.ai.pipeline import ChaosPipeline

    return ChaosPipeline.from_profile_name(
        "easy",
        "chaotic",
        _default_llm(),
    )


def _standard_deck() -> list[Card]:
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    return [Card(Rank(r), "") for r in ranks for _ in range(4)]


def _shuffle(cards: list[Card], rng: random.Random) -> tuple[Card, ...]:
    rng.shuffle(cards)
    return tuple(cards)


def _remove_one_item(state: GameState, item_id: str) -> GameState:
    inv = list(state.inventory)
    if item_id in inv:
        inv.remove(item_id)
    return state.with_inventory(tuple(inv))


@dataclass
class GameLoop:
    """High-level loop; chaos goes through ChaosPipeline (JSON + permissions + registry)."""

    rules: RuleEngine = field(default_factory=DefaultBlackjackRules)
    pipeline: "ChaosPipeline" = field(default_factory=_default_pipeline)
    modifiers: ActiveModifiers = field(default_factory=ActiveModifiers)
    rng: random.Random = field(default_factory=random.Random)
    dispatcher: EventDispatcher | None = None
    chaos_budget_initial: int = 5
    initial_inventory: tuple[str, ...] = field(default_factory=lambda: ("peek",))
    _chaos_actions_this_turn: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        cb = self.pipeline.permission_profile.get("chaos_budget")
        if cb is not None:
            self.chaos_budget_initial = int(cb)

    def new_round(self, seed: int | None = None) -> GameState:
        if seed is not None:
            self.rng.seed(seed)
        self._chaos_actions_this_turn = 0
        self.modifiers = self.modifiers.with_cleared()
        deck = list(_standard_deck())
        deck_t = _shuffle(deck, self.rng)
        p1, p2, d1, d2, *rest = deck_t
        return GameState(
            player_hand=(p1, p2),
            dealer_hand=(d1, d2),
            deck=tuple(rest),
            phase=GamePhase.PLAYER_TURN,
            chaos_budget_remaining=self.chaos_budget_initial,
            inventory=self.initial_inventory,
        )

    def _emit(self, event: Event) -> None:
        if self.dispatcher is not None:
            self.dispatcher.dispatch(event)

    def emit_event(self, event: Event) -> None:
        """Public alias for plugins / UI (same as internal emit)."""
        self._emit(event)

    def apply_chaos_phase(self, state: GameState) -> GameState:
        """Run chaos pipeline once (interactive UX: before each player decision)."""
        return self._apply_chaos(state)

    def draw_for_player(self, state: GameState) -> GameState:
        return self._draw(state, to_player=True)

    def draw_for_dealer(self, state: GameState) -> GameState:
        return self._draw(state, to_player=False)

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

    def _apply_chaos(self, state: GameState) -> GameState:
        obs = ChaosObservation(
            state=state,
            modifiers=self.modifiers,
            chaos_budget_remaining=state.chaos_budget_remaining,
            chaos_actions_this_turn=self._chaos_actions_this_turn,
        )
        effect = self.pipeline.run(
            obs,
            emit=self._emit,
            peek_next_card_rank=lambda: state.deck[0].rank if state.deck else None,
        )
        s = state
        if effect.modifier is not None:
            self.modifiers = self.modifiers.with_added(effect.modifier)
            s = s.with_chaos_budget(max(0, s.chaos_budget_remaining - 1))
            self._chaos_actions_this_turn += 1
        if effect.consume_item_id:
            s = _remove_one_item(s, effect.consume_item_id)
            s = s.with_chaos_budget(max(0, s.chaos_budget_remaining - 1))
            self._chaos_actions_this_turn += 1
        return s

    def context(self) -> RuleContext:
        return RuleContext(modifiers=self.modifiers)

    def player_should_hit_simple(self, state: GameState) -> bool:
        v = self.rules.hand_value(state.player_hand, self.context())
        return v < 17

    def run_round_until_done(self, state: GameState) -> GameState:
        """Automated demo: player hits until >=17, then dealer draws until >=17."""
        self._emit(Event(EventType.TURN_START, {"phase": state.phase.name}))
        s = state
        while s.phase == GamePhase.PLAYER_TURN:
            s = self._apply_chaos(s)
            pv = self.rules.hand_value(s.player_hand, self.context())
            if self.rules.is_bust(pv, self.context()):
                return s.with_phase(GamePhase.RESOLVED)
            if self.player_should_hit_simple(s):
                s = self._draw(s, to_player=True)
            else:
                s = s.with_phase(GamePhase.DEALER_TURN)
                break

        while s.phase == GamePhase.DEALER_TURN:
            dv = self.rules.hand_value(s.dealer_hand, self.context())
            if self.rules.is_bust(dv, self.context()):
                return s.with_phase(GamePhase.RESOLVED)
            if dv >= 17:
                return s.with_phase(GamePhase.RESOLVED)
            s = self._draw(s, to_player=False)

        return s.with_phase(GamePhase.RESOLVED)

    def outcome_label(self, state: GameState) -> str:
        return self.rules.compare_player_dealer(state, self.context())
