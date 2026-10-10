"""Scaffold, validate, inspect and launch local content packs."""

from __future__ import annotations

import argparse
import json
import sys

from chaos_blackjack.content.loader import PACK_ROOT, load_content_packs
from chaos_blackjack.content.scaffold import scaffold
from chaos_blackjack.content.validation import validate_packs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chaos_blackjack.content")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="generate an item + AI pack").add_argument("pack")
    sub.add_parser("list", help="list available local pack folders")
    for name in ("validate", "inspect", "play"):
        command = sub.add_parser(name)
        command.add_argument("packs", nargs="+")
        if name == "play":
            command.add_argument("--ai", default=None)
            command.add_argument("--seed", type=int, default=None)
            command.add_argument("--agent", action="store_true", help="start streaming JSON play instead of GUI")
            command.add_argument("--llm", action="store_true", help="explicitly enable the billed real model")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = {"ok": True, "path": str(scaffold(args.pack))}
        elif args.command == "list":
            result = {"packs": sorted(p.name for p in PACK_ROOT.iterdir()
                                      if p.is_dir() and (p / "pack.json").is_file()) if PACK_ROOT.exists() else []}
        elif args.command == "validate":
            result = validate_packs(tuple(args.packs))
        else:
            catalog = load_content_packs(tuple(args.packs))
            if args.command == "inspect":
                result = {"packs": args.packs, "items": list(catalog.registry.item_ids()),
                          "ais": list(catalog.registry.ai_ids()), "default_ai": catalog.default_ai,
                          "starting_items": list(catalog.starting_items), "reward_items": list(catalog.reward_items)}
            else:
                ai_id = args.ai or catalog.default_ai
                if ai_id not in catalog.registry.ai_ids():
                    raise ValueError(f"Unknown AI id: {ai_id}")
                if args.agent:
                    from chaos_blackjack.agent.__main__ import main as agent_main

                    options = ["play", "--chaos", "--ai", ai_id]
                    for pack in args.packs:
                        options.extend(("--pack", pack))
                    if args.seed is not None:
                        options.extend(("--seed", str(args.seed)))
                    if args.llm:
                        options.append("--llm")
                    return agent_main(options)
                from chaos_blackjack.app.config import RunConfig
                from chaos_blackjack.gui.app import App

                config = RunConfig(content_packs=tuple(args.packs), ai_id=ai_id,
                                   enable_chaos=True, seed=args.seed, use_llm=args.llm)
                App(run_config=config).run("table")
                return 0
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
