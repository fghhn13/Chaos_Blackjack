"""CLI — menu-driven interactive UX or non-interactive demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chaos_blackjack.ai.gemini_llm import load_dotenv_from_project_root

load_dotenv_from_project_root()

from chaos_blackjack import auto_load_plugins
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.save_manager import list_saves, load_game
from chaos_blackjack.ui.session import (
    run_interactive_session,
    run_interactive_session_from_save,
)


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


def _prompt_int(
    *,
    stdin: TextIO,
    stdout: TextIO,
    prompt: str,
    min_val: int,
    max_val: int,
) -> int:
    while True:
        stdout.write(prompt)
        stdout.flush()
        raw = stdin.readline()
        if not raw:
            raise SystemExit(0)
        raw = raw.strip()
        try:
            v = int(raw)
        except ValueError:
            stdout.write(f"Please enter an integer between {min_val} and {max_val}.\n")
            continue
        if v < min_val or v > max_val:
            stdout.write(f"Please enter a value between {min_val} and {max_val}.\n")
            continue
        return v


def _menu_new_game(stdin: TextIO, stdout: TextIO, enable_chaos: bool) -> None:
    stdout.write("Choose Game Mode:\n")
    stdout.write("1. Double Money (100 -> 400)\n")
    stdout.write("2. Survival (10 rounds)\n")
    stdout.write("3. Custom\n\n")
    choice = _prompt_int(
        stdin=stdin,
        stdout=stdout,
        prompt="> ",
        min_val=1,
        max_val=3,
    )

    if choice == 1:
        run_interactive_session(
            seed=None,
            enable_chaos=enable_chaos,
            objective="double_money",
            start_money=100,
            target_money=400,
        )
        return
    if choice == 2:
        # Temporarily map survival objective to a very high target money.
        # End-of-run objective evaluation comes later.
        run_interactive_session(
            seed=None,
            enable_chaos=enable_chaos,
            objective="survival",
            start_money=100,
            target_money=10**9,
            round_limit=10,
        )
        return
    # Custom
    stdout.write("Custom start money:\n")
    raw = _prompt_int(
        stdin=stdin,
        stdout=stdout,
        prompt="Enter start_money (>=1): ",
        min_val=1,
        max_val=10**9,
    )
    run_interactive_session(
        seed=None,
        enable_chaos=enable_chaos,
        objective="custom",
        start_money=raw,
        target_money=10**9,
    )


def _menu_load_game(stdin: TextIO, stdout: TextIO, enable_chaos: bool) -> None:
    saves = list_saves()
    if not saves:
        stdout.write("No save files found.\n")
        return

    stdout.write("💾 Load Game\n")
    stdout.write("====================\n")
    for i, name in enumerate(saves, 1):
        try:
            data = load_game(name)
            summary = f"Round {data.round}, Money {data.money}, Objective {data.objective}"
        except Exception:
            summary = "(corrupted save)"
        stdout.write(f"{i}. {name}  ({summary})\n")
    stdout.write(f"{len(saves)+1}. Back\n\n")

    choice = _prompt_int(
        stdin=stdin,
        stdout=stdout,
        prompt="> ",
        min_val=1,
        max_val=len(saves) + 1,
    )
    if choice == len(saves) + 1:
        return

    sel = saves[choice - 1]
    data = load_game(sel)
    run_interactive_session_from_save(
        data,
        enable_chaos=enable_chaos,
        seed=None,
        stdin=stdin,
        stdout=stdout,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Chaos Blackjack CLI")
    p.add_argument(
        "--enable-chaos",
        action="store_true",
        help="Enable chaos actions during player turns (off by default in MVP v1 mode)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed (optional) for demo/menus",
    )

    sub = p.add_subparsers(dest="cmd")
    demo = sub.add_parser("demo", help="One automated round (no input)")
    demo.add_argument("--seed", type=int, default=42)

    args = p.parse_args()
    auto_load_plugins()

    if args.cmd == "demo":
        _run_demo(args.seed)
        return

    stdin = sys.stdin
    stdout = sys.stdout
    enable_chaos = bool(args.enable_chaos)

    # Boot + main menu
    stdout.write("🃏 Chaos Blackjack\n")
    stdout.write("==============================\n\n")
    while True:
        stdout.write("1. New Game\n")
        stdout.write("2. Load Game\n")
        stdout.write("3. Quit\n\n")
        choice = _prompt_int(
            stdin=stdin,
            stdout=stdout,
            prompt="> ",
            min_val=1,
            max_val=3,
        )
        if choice == 1:
            _menu_new_game(stdin, stdout, enable_chaos=enable_chaos)
        elif choice == 2:
            _menu_load_game(stdin, stdout, enable_chaos=enable_chaos)
        else:
            stdout.write("Bye.\n")
            return


if __name__ == "__main__":
    main()
