#!/usr/bin/env python3
"""GPTsAPI connectivity check (reads GPTSAPI_* from the environment / .env).

  python scripts/debug_llm.py models   # list model ids (no completion billed)
  python scripts/debug_llm.py smoke    # one billed request, max 16 output tokens
  python scripts/debug_llm.py chaos    # one billed request through the Chaos AI prompt

Output is JSON; the API key is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chaos_blackjack.rules.modifiers import ActiveModifiers  # noqa: E402
from chaos_blackjack.ai.gptsapi_llm import (  # noqa: E402
    DEFAULT_MODEL,
    GptsApiLLM,
    create_client_from_env,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("models", "smoke", "chaos"))
    args = p.parse_args()
    try:
        client = create_client_from_env()
        model = os.environ.get("GPTSAPI_MODEL", "").strip() or DEFAULT_MODEL
        if args.command == "models":
            result = client.models()
            result["configured_model_listed"] = model in result["models"]
        elif args.command == "smoke":
            result = client.chat([{"role": "user", "content": "Reply with exactly: OK"}], model, 16)
            result["passed"] = result["answer"].strip() == "OK"
        else:
            from chaos_blackjack.ai.pipeline import ChaosPipeline
            from chaos_blackjack.ai.prompts_loader import load_prompt
            from chaos_blackjack.contracts.observation import ChaosObservation
            from chaos_blackjack.core.game_loop import GameLoop
            from chaos_blackjack.registry.loader import auto_load_plugins

            auto_load_plugins()
            llm = GptsApiLLM(client, model=model)
            pipeline = ChaosPipeline.from_profile_name("easy", "chaotic", llm)
            state = GameLoop(pipeline=pipeline).new_round(seed=1)
            obs = ChaosObservation(state=state, modifiers=ActiveModifiers(), chaos_budget_remaining=state.chaos_budget_remaining)
            raw = llm.complete(load_prompt(pipeline.prompt_name), pipeline._build_user_prompt(obs))  # noqa: SLF001
            result = {"model": model, "raw": raw, "error": llm.last_error, "usage": llm.last_usage}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("passed", True) and not result.get("error") else 1
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
