"""Prompt → LLM JSON → permission check → registry → modifier / item use."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from chaos_blackjack.contracts.ai_action import StructuredAIAction, parse_structured_action
from chaos_blackjack.contracts.items import ItemContext
from chaos_blackjack.contracts.llm import LLMBackend
from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.ai.permission_validator import validate_chaos_action
from chaos_blackjack.ai.permissions_loader import load_permission_profile
from chaos_blackjack.ai.prompts_loader import load_prompt
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.registry.registry import Registry, get_registry
from chaos_blackjack.rules.modifiers import RuleModifier


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


@dataclass
class ChaosPipeline:
    """Sandboxed chaos: structured JSON only, then registry + permissions."""

    permission_profile: dict[str, Any]
    prompt_name: str
    llm: LLMBackend
    registry: Registry | None = None

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
        return ChaosPipeline(
            permission_profile=load_permission_profile(permission_name),
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
        system = load_prompt(self.prompt_name)
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

        ok, reason = validate_chaos_action(
            parsed,
            self.permission_profile,
            budget_remaining=obs.chaos_budget_remaining,
            actions_this_turn=obs.chaos_actions_this_turn,
        )
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

            ctx = ItemContext(
                state=obs.state,
                emit_event=lambda e: emit(e),
                peek_next_card_rank=peek_next_card_rank,
            )
            inst = cls()
            result = inst.use(ctx)
            if result.ok:
                return ChaosEffect(
                    consume_item_id=iid,
                    log_message=result.message,
                    narration=narration,
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

    def _build_user_prompt(self, obs: ChaosObservation) -> str:
        pv = sum(1 for _ in obs.state.player_hand)
        dv = sum(1 for _ in obs.state.dealer_hand)
        return (
            f"Player hand size: {pv}, dealer up-cards visible count: {dv}. "
            f"Deck remaining: {len(obs.state.deck)}. "
            f"Chaos budget left: {obs.chaos_budget_remaining}. "
            f"Chaos actions this turn: {obs.chaos_actions_this_turn}. "
            f"Inventory: {list(obs.state.inventory)}. "
            "Choose your JSON action."
        )


@dataclass
class StubLLM:
    """Deterministic JSON for tests and CLI demo."""

    response_json: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self.response_json
