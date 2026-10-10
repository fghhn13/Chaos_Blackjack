"""Agent player CLI — see AGENTS.md.

One-shot commands (state kept in a file between calls):

  python -m chaos_blackjack.agent new [--seed N] [--chaos] [--llm]
  python -m chaos_blackjack.agent observe
  python -m chaos_blackjack.agent buy peek
  python -m chaos_blackjack.agent bet 20
  python -m chaos_blackjack.agent act hit|stand|double|surrender
  python -m chaos_blackjack.agent act use_item peek

Streaming (one JSON command per stdin line, one JSON reply per stdout line):

  python -m chaos_blackjack.agent play [--seed N] [--chaos]

Output is JSON. Exit code 0 = ok, 1 = the command was rejected, 2 = usage/state error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from chaos_blackjack.agent.session import AgentSession, LlmUnavailable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = PROJECT_ROOT / ".agent_runs" / "current.json"
BRIEF_OBS_KEYS = ("phase", "summary", "hint", "legal_actions", "bet_range", "shop", "last_round", "run_end")


def _emit(reply: dict[str, Any], *, brief: bool, compact: bool) -> None:
    if brief:
        obs = reply.get("obs", {})
        reply = {k: v for k, v in reply.items() if k not in ("obs", "run")}
        reply["obs"] = {k: obs[k] for k in BRIEF_OBS_KEYS if obs.get(k) is not None}
    text = json.dumps(reply, ensure_ascii=False, separators=(",", ":") if compact else None,
                      indent=None if compact else 2)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _log(state_path: Path, command: dict[str, Any], reply: dict[str, Any], steps: int) -> None:
    obs = reply.get("obs", {})
    record = {
        "t": round(time.time(), 3),
        "step": steps,
        "command": command,
        "ok": reply.get("ok"),
        "error": reply.get("error", {}).get("code") if not reply.get("ok") else None,
        "events": reply.get("events"),
        "phase": obs.get("phase"),
        "bankroll": obs.get("bankroll"),
    }
    with state_path.with_suffix(".log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _save(path: Path, session: AgentSession) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(session.to_state()), encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path) -> AgentSession:
    if not path.is_file():
        raise FileNotFoundError(f"No run at {path}. Start one with: python -m chaos_blackjack.agent new")
    return AgentSession.from_state(json.loads(path.read_text(encoding="utf-8")))


def _new_session(args: argparse.Namespace) -> AgentSession:
    config: dict[str, Any] = {}
    if args.start_money is not None:
        config["start_money"] = args.start_money
    if args.target_money is not None:
        config["target_money"] = args.target_money
    return AgentSession.new(seed=args.seed, chaos=args.chaos, use_llm=args.llm,
                            max_steps=args.max_steps, profile=args.profile, **config)


def _add_new_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--seed", type=int, default=None, help="deterministic deal (random if omitted)")
    p.add_argument("--chaos", action="store_true", help="let the Chaos AI change rules each round")
    p.add_argument("--llm", action="store_true",
                   help="drive the Chaos AI with the real GPTsAPI model (billed; needs .env). Default: offline stub")
    p.add_argument("--start-money", type=int, default=None)
    p.add_argument("--target-money", type=int, default=None)
    p.add_argument("--max-steps", type=int, default=2000)
    p.add_argument("--profile", default=None,
                   help="balance profile in data/game.db (default: $CHAOS_PROFILE or 'default')")


def _play_stream(args: argparse.Namespace) -> int:
    session = _new_session(args)
    _emit(session.execute({"cmd": "observe"}), brief=args.brief, compact=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
            if not isinstance(command, dict):
                raise ValueError("command must be a JSON object")
        except ValueError as e:
            _emit({"ok": False, "error": {"code": "invalid_json", "message": str(e)}}, brief=False, compact=True)
            continue
        if command.get("cmd") == "new":
            ns = argparse.Namespace(**{**vars(args), **{k.replace("-", "_"): v for k, v in command.items() if k != "cmd"}})
            session = _new_session(ns)
            reply = session.execute({"cmd": "observe"})
        elif command.get("cmd") in ("quit", "exit"):
            return 0
        else:
            reply = session.execute(command)
        _emit(reply, brief=args.brief, compact=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m chaos_blackjack.agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help=f"run file (default: {DEFAULT_STATE})")
    parser.add_argument("--brief", action="store_true", help="smaller output: summary, hint, legal actions")
    parser.add_argument("--compact", action="store_true", help="single-line JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_new_options(sub.add_parser("new", help="start a new run (overwrites the run file)"))
    sub.add_parser("observe", help="show the current observation")
    sub.add_parser("help", help="list game commands")
    buy = sub.add_parser("buy", help="buy a shop item (betting phase)")
    buy.add_argument("item")
    bet = sub.add_parser("bet", help="place a bet")
    bet.add_argument("amount", type=int)
    act = sub.add_parser("act", help="act in your turn")
    act.add_argument("action", choices=("hit", "stand", "double", "surrender", "use_item"))
    act.add_argument("item", nargs="?", help="item id for use_item")
    play = sub.add_parser("play", help="streaming JSON-lines mode on stdin/stdout")
    _add_new_options(play)
    args = parser.parse_args(argv)

    try:
        if args.command == "play":
            return _play_stream(args)
        if args.command == "new":
            session = _new_session(args)
            command: dict[str, Any] = {"cmd": "new", "seed": session.seed, "chaos": args.chaos, "llm": args.llm}
            log_path = args.state.with_suffix(".log.jsonl")
            if log_path.exists():
                log_path.unlink()
            reply = session.execute({"cmd": "observe"})
        else:
            session = _load(args.state)
            command = {"cmd": args.command}
            if args.command == "bet":
                command["amount"] = args.amount
            elif args.command == "buy":
                command["item"] = args.item
            elif args.command == "act":
                command["action"] = args.action
                if args.item:
                    command["item"] = args.item
            reply = session.execute(command)
        reply["run"] = {"seed": session.seed, "steps": session.steps, "state_file": str(args.state),
                        "profile": session.controller.config.balance_profile}
        _save(args.state, session)
        if args.command not in ("observe", "help"):
            _log(args.state, command, reply, session.steps)
        _emit(reply, brief=args.brief, compact=args.compact)
        return 0 if reply.get("ok") else 1
    except (FileNotFoundError, ValueError, KeyError, LlmUnavailable) as e:
        _emit({"ok": False, "error": {"code": "usage", "message": str(e)}}, brief=False, compact=args.compact)
        return 2


if __name__ == "__main__":
    sys.exit(main())
