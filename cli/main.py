"""CLI — interactive UX (default) or non-interactive demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chaos_blackjack.ai.gemini_llm import load_dotenv_from_project_root

load_dotenv_from_project_root()

from chaos_blackjack import auto_load_plugins
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.ui.session import run_interactive_session


def _run_demo(seed: int | None) -> None:
    auto_load_plugins()
    loop = GameLoop()
    state = loop.new_round(seed=seed or 42)
    final = loop.run_round_until_done(state)
    pv = loop.rules.hand_value(final.player_hand, loop.context())
    dv = loop.rules.hand_value(final.dealer_hand, loop.context())
    print("Chaos Blackjack v2 (automated demo)")
    print(f"  Active chaos modifiers: {len(loop.modifiers.items)}")
    print(f"  Player: {[c.rank for c in final.player_hand]} = {pv}")
    print(f"  Dealer: {[c.rank for c in final.dealer_hand]} = {dv}")
    print(f"  Outcome: {loop.outcome_label(final)}")


def main() -> None:
    p = argparse.ArgumentParser(description="Chaos Blackjack CLI")
    sub = p.add_subparsers(dest="cmd")

    play = sub.add_parser("play", help="Interactive session (UX_design.md)")
    play.add_argument("--seed", type=int, default=None, help="RNG seed (optional)")

    demo = sub.add_parser("demo", help="One automated round (no input)")
    demo.add_argument("--seed", type=int, default=42)

    args = p.parse_args()
    if args.cmd == "demo":
        _run_demo(args.seed)
    elif args.cmd == "play":
        run_interactive_session(seed=args.seed)
    else:
        run_interactive_session(seed=None)


if __name__ == "__main__":
    main()
