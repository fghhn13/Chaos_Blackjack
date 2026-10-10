"""Game database tools.

  python -m chaos_blackjack.data saves                      list saves in data/game.db
  python -m chaos_blackjack.data import-saves [DIR] [--overwrite]
                                                            copy old JSON saves (default: chaos_blackjack/saves/)
"""

from __future__ import annotations

import argparse
import sys

from chaos_blackjack.data.db import db_path
from chaos_blackjack.data.saves import LEGACY_SAVE_DIR, import_json_saves, list_runs


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m chaos_blackjack.data", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("saves", help="list saves")
    imp = sub.add_parser("import-saves", help="import old JSON save files")
    imp.add_argument("folder", nargs="?", default=str(LEGACY_SAVE_DIR))
    imp.add_argument("--overwrite", action="store_true", help="replace saves that already exist")
    a = p.parse_args(argv)

    print(f"database: {db_path()}")
    if a.cmd == "saves":
        runs = list_runs()
        for s in runs:
            print(f"  {s.name:24s} round {s.round:<4d} money {s.money:<6d} profile {s.profile or '-':12s} {s.updated_at}")
        if not runs:
            print("  (no saves)")
        return 0
    results = import_json_saves(a.folder, overwrite=a.overwrite)
    for name, status in results.items():
        print(f"  {name}: {status}")
    if not results:
        print(f"  no .json files in {a.folder}")
    return 1 if any(s.startswith("error") for s in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
