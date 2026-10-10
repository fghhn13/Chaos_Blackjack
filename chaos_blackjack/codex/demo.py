"""Deterministic table replays with real controller actions and no UI or LLM.

Only the deal, starting inventory and explicitly requested rule applications
are rigged. Valuation, item effects, legal actions, naturals, dealer play and
settlement all belong to GameController. Rule previews deliberately bypass
AI selection/eligibility (including disabled rules), not rule parameters.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from chaos_blackjack.ai.pipeline import ChaosPipeline, StubLLM
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.codex.models import DemoFrame, DemoScript
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.registry import get_registry

_ACTIONS = frozenset({
    "deal", "apply_rule", "use_item", "hit", "stand", "double", "surrender",
    "dealer", "caption", "pause",
})
_TERMINAL = (TablePhase.ROUND_OVER, TablePhase.RUN_OVER)


def _cards(values: tuple[str, ...]) -> tuple[Card, ...]:
    cards = []
    for value in values:
        if (not isinstance(value, str) or len(value) < 2 or value[-1] not in "♠♥♦♣"
                or value[:-1] not in {"A", "J", "Q", "K", *map(str, range(2, 11))}):
            raise ValueError(f"Invalid demo card: {value!r}; expected a rank and suit, e.g. K♠")
        cards.append(Card(Rank(value[:-1]), value[-1]))
    return tuple(cards)


def rule_params(rule_id: str, config: RunConfig) -> dict[str, Any]:
    """Use the offline AI's proposal as a base; fixed profile tuning wins."""
    params: dict[str, Any] = {}
    for rid, proposed, _weight in config.chaos_stub:
        if rid == rule_id:
            params.update(proposed)
            break
    params.update(config.chaos_rule_params.get(rule_id, {}))
    return params


class _RiggedLoop(GameLoop):
    def __init__(self, script: DemoScript, dispatcher) -> None:
        # Supplying a pipeline explicitly avoids _default_llm and .env loading,
        # even if the caller has CHAOS_USE_LLM=1.
        super().__init__(
            dispatcher=dispatcher,
            pipeline=ChaosPipeline.from_profile_name("easy", "chaotic", StubLLM('{"action":"noop"}')),
        )
        self.player = _cards(script.player)
        self.dealer = _cards(script.dealer)
        self.deck = _cards(script.deck)

    def new_round(self, seed=None, *, inventory_override=None) -> GameState:
        self.modifiers = self.modifiers.with_cleared()
        self._chaos_actions_this_turn = 0
        self.last_chaos_narration = None
        return GameState(
            player_hand=self.player, dealer_hand=self.dealer, deck=self.deck,
            phase=GamePhase.PLAYER_TURN, chaos_budget_remaining=self.chaos_budget_initial,
            inventory=inventory_override if inventory_override is not None else (),
        )


def run_demo(script: DemoScript, config: RunConfig) -> list[DemoFrame]:
    """Run a single rigged round, returning independent snapshots to animate.

    ``deal`` takes an optional integer bet (default: the profile minimum).
    ``apply_rule`` takes an id or {rule_id, params}; fixed RunConfig tuning
    wins over explicit params. ``use_item`` takes an item id, automatically
    supplied in the demo inventory. ``dealer`` emits a frame per draw and
    settlement. ``caption``/``pause`` repeat the current snapshot without
    sleeping. If tuning ends the round early, remaining gameplay steps stop.
    Invalid scripts/actions raise ValueError/ActionError instead of being
    turned into an apparently successful demonstration.
    """
    if len(script.player) != 2 or len(script.dealer) != 2:
        raise ValueError("A demo deal needs two player cards and two dealer cards")
    if sum(s.action == "deal" for s in script.steps) != 1:
        raise ValueError("A demo script must contain exactly one deal")
    for step in script.steps:
        if step.action not in _ACTIONS:
            raise ValueError(f"Unknown demo action: {step.action!r}")
        if step.action == "use_item" and not isinstance(step.arg, str):
            raise ValueError("use_item needs an item id")

    cfg = replace(config, seed=0, enable_chaos=script.chaos)
    controller = GameController(cfg, loop_factory=lambda d: _RiggedLoop(script, d))
    # Supply one copy for each scripted use; no purchases or player saves.
    controller.run.items = tuple(s.arg for s in script.steps if s.action == "use_item")
    frames: list[DemoFrame] = []
    caption = ""
    dealt = False
    rule_pending = any(s.action == "apply_rule" for s in script.steps)

    def frame() -> None:
        frames.append(DemoFrame(controller.view(), caption, tuple(controller.drain_notices())))

    for step in script.steps:
        caption = step.caption or caption
        action = step.action
        if action in {"caption", "pause"}:
            frame()
            continue
        if controller.phase in _TERMINAL:
            break
        if action != "deal" and not dealt:
            raise ValueError("Gameplay steps must follow deal")
        if action == "deal":
            amount = step.arg if step.arg is not None else controller.bet_limits()[0]
            if isinstance(amount, bool) or not isinstance(amount, int):
                raise ValueError("deal needs an integer bet")
            controller.place_bet(amount)
            dealt = True
            if controller.phase == TablePhase.CHAOS and not rule_pending:
                controller.resolve_chaos()
        elif action == "apply_rule":
            if not script.chaos:
                raise ValueError("apply_rule requires a chaos demo")
            if controller.phase not in (TablePhase.CHAOS, TablePhase.PLAYER_TURN):
                raise ActionError("Rules can only be demonstrated before dealer play")
            if isinstance(step.arg, str):
                rid, proposed = step.arg, {}
            elif isinstance(step.arg, dict) and isinstance(step.arg.get("rule_id"), str):
                rid, proposed = step.arg["rule_id"], step.arg.get("params", {})
                if not isinstance(proposed, dict):
                    raise ValueError("Rule params must be a dictionary")
            else:
                raise ValueError("apply_rule needs a rule id or {rule_id, params}")
            params = {**rule_params(rid, cfg), **proposed, **cfg.chaos_rule_params.get(rid, {})}
            registry = getattr(controller, "registry", get_registry())
            modifier = registry.build_chaos_rule(rid, params)
            if modifier is None:
                raise ValueError(f"Unknown demo rule: {rid!r}")
            controller.loop.modifiers = controller.loop.modifiers.with_added(modifier)
            controller.loop.emit_event(Event(EventType.RULE_MODIFIER_APPLIED, {"rule_id": rid, "params": params}))
            if controller.phase == TablePhase.CHAOS:
                # The real controller checks naturals after the explicit rule.
                controller.resolve_chaos()
            else:
                controller._settle_if_player_bust()
        elif action == "use_item":
            result = controller.use_item(step.arg)
            if not result.ok:
                raise ActionError(result.message)
        elif action == "dealer":
            if controller.phase != TablePhase.DEALER_TURN:
                raise ActionError("dealer must follow stand or double")
            while controller.phase == TablePhase.DEALER_TURN:
                controller.dealer_step()
                frame()
            continue
        else:
            if controller.phase == TablePhase.CHAOS:
                raise ActionError("Apply the scripted rule before player actions")
            method = "double_down" if action == "double" else action
            getattr(controller, method)()
        frame()
    return frames
