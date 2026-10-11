"""Prompt → LLM JSON → permission check → registry → modifier / item use."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from chaos_blackjack.contracts.ai_action import StructuredAIAction, parse_structured_action
from chaos_blackjack.contracts.llm import LLMBackend
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.ai.permissions_loader import load_permission_profile
from chaos_blackjack.ai.prompts_loader import load_prompt
from chaos_blackjack.ai.chaos_policy import ChaosPolicy
from chaos_blackjack.ai.chaos_scheduler import ChaosScheduler
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.registry.registry import Registry, get_registry
from chaos_blackjack.rules.modifiers import RuleModifier
from chaos_blackjack.core.game_state import GameState
from chaos_blackjack.items.runtime import execute_item


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", s)
    if m:
        return m.group(1).strip()
    return s


@dataclass
class ChaosEffect:
    modifier: RuleModifier | None = None
    consume_item_id: str | None = None
    log_message: str | None = None
    narration: str | None = None
    state_after: GameState | None = None


@dataclass
class ChaosPipeline:
    """Sandboxed chaos: structured JSON only, then registry + permissions."""

    permission_profile: dict[str, Any]
    policy: ChaosPolicy
    scheduler: ChaosScheduler
    prompt_name: str
    llm: LLMBackend
    registry: Registry | None = None
    # From the balance profile: fixed params per rule (they win over the AI's
    # params) and rules switched off for this run.
    rule_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    disabled_rules: frozenset[str] = frozenset()
    item_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    system_prompt: str | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = get_registry()

    @staticmethod
    def from_profile_name(
        permission_name: str,
        prompt_name: str,
        llm: LLMBackend,
        registry: Registry | None = None,
    ) -> ChaosPipeline:
        profile = load_permission_profile(permission_name)
        policy = ChaosPolicy.from_profile(profile)
        return ChaosPipeline(
            permission_profile=profile,
            policy=policy,
            scheduler=ChaosScheduler(policy),
            prompt_name=prompt_name,
            llm=llm,
            registry=registry,
        )

    def run(
        self,
        obs: ChaosObservation,
        *,
        emit: Callable[[Event], None],
        peek_next_card_rank: Callable[[], str | None],
    ) -> ChaosEffect:
        system = ((self.system_prompt if self.system_prompt is not None else load_prompt(self.prompt_name)) + "\n\nAuthoritative run-specific action constraints:\n"
                  + json.dumps(self.action_constraints(), ensure_ascii=False)
                  + "\nUse only these allowed ids. Fixed rule_params override any parameters you choose.")
        user = self._build_user_prompt(obs)
        raw = self.llm.complete(system, user)
        def _repair_user_prompt(prev_raw: str) -> str:
            # Keep the base prompt (so the model still sees the state/permissions),
            # then enforce JSON-only output.
            prev = prev_raw.strip()
            if len(prev) > 800:
                prev = prev[:800] + "..."
            return (
                user
                + "\n\nYour previous output was invalid JSON or didn't match the schema. "
                + "Return ONLY a single JSON object (no markdown/code fences) with keys: "
                + "{action, narration?, rule_id?, params?, item_id}. "
                + "Do not include any other text.\n\nPrevious output:\n"
                + prev
            )

        def _parse_once(raw_text: str) -> tuple[StructuredAIAction | None, str | None]:
            try:
                data = json.loads(_strip_json_fence(raw_text))
            except json.JSONDecodeError:
                return None, "invalid_json"
            if not isinstance(data, dict):
                return None, "not_object"
            parsed = parse_structured_action(data)
            if parsed is None:
                return None, "bad_action"
            return parsed, None

        parsed, parse_reason = _parse_once(raw)
        if parsed is None:
            repaired_raw = self.llm.complete(system, _repair_user_prompt(raw))
            repaired_parsed, repaired_reason = _parse_once(repaired_raw)
            if repaired_parsed is not None:
                parsed = repaired_parsed
            else:
                if repaired_reason == "invalid_json":
                    emit(
                        Event(
                            EventType.CHAOS_ACTION_REJECTED,
                            {"reason": "invalid_json", "raw": repaired_raw[:200]},
                        ),
                    )
                else:
                    emit(
                        Event(
                            EventType.CHAOS_ACTION_REJECTED,
                            {"reason": repaired_reason},
                        ),
                    )
                return ChaosEffect()

        ok, reason = self.policy.validate_action(parsed, obs)
        if not ok:
            emit(
                Event(
                    EventType.CHAOS_ACTION_REJECTED,
                    {"reason": reason, "action": parsed},
                ),
            )
            return ChaosEffect()

        narration = parsed.get("narration")
        act = parsed.get("action", "noop")
        if act == "noop":
            return ChaosEffect(log_message="noop", narration=narration)

        if act == "apply_rule":
            rid = parsed.get("rule_id") or ""
            params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
            if rid in self.disabled_rules:
                emit(
                    Event(
                        EventType.CHAOS_ACTION_REJECTED,
                        {"reason": "rule_disabled", "rule_id": rid},
                    ),
                )
                return ChaosEffect()
            params = {**params, **self.rule_params.get(rid, {})}
            assert self.registry is not None
            mod = self.registry.build_chaos_rule(rid, params)
            if mod is None:
                emit(
                    Event(
                        EventType.CHAOS_ACTION_REJECTED,
                        {"reason": "unknown_rule", "rule_id": rid},
                    ),
                )
                return ChaosEffect()
            emit(
                Event(
                    EventType.RULE_MODIFIER_APPLIED,
                    {"rule_id": rid, "params": params},
                ),
            )
            return ChaosEffect(
                modifier=mod,
                log_message=f"applied:{rid}",
                narration=narration,
            )

        if act == "use_item":
            iid = parsed.get("item_id") or ""
            assert self.registry is not None
            cls = self.registry.resolve_item(iid)
            if cls is None:
                emit(
                    Event(
                        EventType.CHAOS_ACTION_REJECTED,
                        {"reason": "unknown_item", "item_id": iid},
                    ),
                )
                return ChaosEffect()
            if iid not in obs.state.inventory:
                emit(
                    Event(
                        EventType.CHAOS_ACTION_REJECTED,
                        {"reason": "item_not_in_inventory", "item_id": iid},
                    ),
                )
                return ChaosEffect()

            after, result = execute_item(
                self.registry, obs.state, iid,
                emit=emit, peek_next_card_rank=peek_next_card_rank,
                params=self.item_params.get(iid),
                active_rule_ids=tuple(str(m.id) for m in obs.modifiers.items),
            )
            if result.ok:
                return ChaosEffect(
                    consume_item_id=iid,
                    log_message=result.message,
                    narration=narration,
                    state_after=after,
                )
            emit(
                Event(
                    EventType.CHAOS_ACTION_REJECTED,
                    {"reason": "item_failed", "message": result.message},
                ),
            )
            return ChaosEffect()

        emit(Event(EventType.CHAOS_ACTION_REJECTED, {"reason": "unknown_verb"}))
        return ChaosEffect()

    def action_constraints(self) -> dict[str, Any]:
        """Model-visible choices after this run's balance disables and tuning."""
        allowed = [rid for rid in self.policy.allowed_rules if rid not in self.disabled_rules]
        return {
            "allowed_rules": allowed,
            "allowed_items": list(self.policy.allowed_items) if self.policy.allowed_items is not None else None,
            "rule_params": {rid: dict(self.rule_params[rid]) for rid in allowed if rid in self.rule_params},
        }

    def _build_user_prompt(self, obs: ChaosObservation) -> str:
        if obs.context_json is not None:
            return "Full private game context:\n" + obs.context_json + "\nChoose your JSON action."
        # Offline strategies and models share one documented, visible-state input.
        # Neither the hidden dealer card nor deck order is sent to the backend.
        return json.dumps({
            "schema": 1,
            "player_cards": [{"rank": str(c.rank), "suit": c.suit} for c in obs.state.player_hand],
            "dealer_up_card": (
                {"rank": str(obs.state.dealer_hand[0].rank), "suit": obs.state.dealer_hand[0].suit}
                if obs.state.dealer_hand else None
            ),
            "deck_remaining": len(obs.state.deck),
            "chaos_budget_remaining": obs.chaos_budget_remaining,
            "chaos_actions_this_turn": obs.chaos_actions_this_turn,
            "inventory": list(obs.state.inventory),
            "active_rules": [str(m.id) for m in obs.modifiers.items],
            "allowed_rules": self.action_constraints()["allowed_rules"],
            "allowed_items": None if self.policy.allowed_items is None else list(self.policy.allowed_items),
        }, ensure_ascii=False)


@dataclass
class StubLLM:
    """Deterministic JSON for tests and CLI demo."""

    response_json: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self.response_json


# (rule_id, AI params, weight)
StubChoice = tuple[str, dict[str, Any], float]
DEFAULT_STUB_CHOICES: tuple[StubChoice, ...] = (("modify_card_value", {"delta": -1}, 1.0),)


@dataclass
class OfflineChaosStub(StubLLM):
    """The offline Chaos AI: applies a rule drawn by weight from `choices`.

    `reseed()` before each chaos turn makes the draw depend only on the run and
    round, so a run replays the same way however it is resumed. An entry with
    rule_id "" is a calm round (noop); with no positive weight it answers noop.
    """

    response_json: str = ""
    choices: tuple[StubChoice, ...] = DEFAULT_STUB_CHOICES
    rng: random.Random = field(default_factory=random.Random, repr=False)

    def reseed(self, seed: str) -> None:
        self.rng.seed(seed)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        live = [c for c in self.choices if c[2] > 0]
        if not live:
            return '{"action":"noop"}'
        rule_id, params, _ = self.rng.choices(live, weights=[c[2] for c in live])[0]
        if not rule_id:
            return '{"action":"noop"}'
        return json.dumps({"action": "apply_rule", "rule_id": rule_id, "params": params})
