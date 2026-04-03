#!/usr/bin/env python3
"""
Quick sanity check: registry, permissions, stub pipeline.
Run from repo root: python scripts/debug_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chaos_blackjack.ai.gemini_llm import load_dotenv_from_project_root
from chaos_blackjack.ai.permissions_loader import load_permission_profile
from chaos_blackjack.ai.pipeline import ChaosPipeline, StubLLM
from chaos_blackjack.ai.prompts_loader import load_prompt
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.registry.loader import auto_load_plugins
from chaos_blackjack.registry.registry import get_registry
from chaos_blackjack.rules.modifiers import ActiveModifiers


def main() -> None:
    load_dotenv_from_project_root()
    auto_load_plugins()
    reg = get_registry()

    print("=== Registry (probe) ===")
    print("  peek registered:", reg.resolve_item("peek") is not None)
    print("  modify_card_value builds:", reg.build_chaos_rule("modify_card_value", {"delta": 0}) is not None)

    print("\n=== easy.json ===")
    print(load_permission_profile("easy"))

    print("\n=== chaotic.txt (first 120 chars) ===")
    print(load_prompt("chaotic")[:120].replace("\n", " ") + "...")

    print("\n=== Stub pipeline run ===")
    pipe = ChaosPipeline.from_profile_name(
        "easy",
        "chaotic",
        StubLLM(
            response_json='{"action":"apply_rule","rule_id":"modify_card_value","params":{"delta":-1}}',
        ),
        registry=reg,
    )
    st = GameState(
        player_hand=(Card(Rank("8"), ""), Card(Rank("9"), "")),
        dealer_hand=(Card(Rank("6"), ""), Card(Rank("K"), "")),
        deck=(Card(Rank("2"), ""),),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=5,
        inventory=("peek",),
    )
    obs = ChaosObservation(
        state=st,
        modifiers=ActiveModifiers(),
        chaos_budget_remaining=5,
        chaos_actions_this_turn=0,
    )
    ev: list[str] = []

    def emit(e) -> None:
        ev.append(f"{e.type.name} {dict(e.payload)}")

    eff = pipe.run(obs, emit=emit, peek_next_card_rank=lambda: "3")
    print("  events:", ev)
    print("  effect modifier:", eff.modifier is not None, "log:", eff.log_message)


if __name__ == "__main__":
    main()
