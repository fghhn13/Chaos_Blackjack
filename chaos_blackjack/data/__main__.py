"""Game database tools (data/game.db, or $CHAOS_DB).

Balance profiles
  profiles                          list profiles
  show PROFILE                      every value (and check that the profile loads)
  clone SOURCE NAME [-d TEXT]       copy a profile to a new, editable one
  set PROFILE KEY VALUE             change one value (validated; locked profiles refuse)
  diff A B                          values that differ
  export PROFILE [-o FILE]          the profile as a seed file (seed/default.sql format)
  delete PROFILE                    remove an unlocked profile

  KEY is a setting (run.start_money, bet.max_fraction, ...), item.<id>.<field>
  (price, enabled, weight, params, price_mode) or rule.<id>.<field>
  (enabled, params, stub_weight, stub_params). JSON values: '{"ten_value": 5}'.

Saves
  saves                             list saves
  import-saves [DIR] [--overwrite]  copy old JSON saves (default: chaos_blackjack/saves/)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chaos_blackjack.data import admin
from chaos_blackjack.data.balance import BalanceError, clone_profile, load_balance
from chaos_blackjack.data.db import connect, db_path
from chaos_blackjack.data.saves import LEGACY_SAVE_DIR, import_json_saves, list_runs


def _profiles(conn, a) -> int:
    for p in admin.list_profiles(conn):
        try:
            tag = load_balance(p.name, conn).fingerprint
        except BalanceError as e:
            tag = f"INVALID: {e}"
        lock = "locked" if p.locked else "      "
        parent = f" (from {p.parent})" if p.parent else ""
        print(f"  {p.name:20s} {lock} {tag}{parent}  {p.description}")
    return 0


def _show(conn, a) -> int:
    values = admin.profile_values(conn, a.profile)
    width = max(len(k) for k in values)
    for k, v in values.items():
        print(f"  {k:{width}s}  {v}")
    b = load_balance(a.profile, conn)
    print(f"\n  valid; fingerprint {b.fingerprint}")
    return 0


def _clone(conn, a) -> int:
    clone_profile(conn, a.source, a.name, a.description or "")
    print(f"  created {a.name!r} from {a.source!r}")
    return 0


def _set(conn, a) -> int:
    before = admin.profile_values(conn, a.profile).get(a.key, "")
    admin.set_value(conn, a.profile, a.key, a.value)
    after = admin.profile_values(conn, a.profile).get(a.key, "")
    print(f"  {a.profile}: {a.key} {before or '—'} -> {after or '—'}")
    return 0


def _diff(conn, a) -> int:
    rows = admin.diff_profiles(conn, a.a, a.b)
    if not rows:
        print("  identical")
        return 0
    width = max(len(k) for k, _, _ in rows)
    print(f"  {'key':{width}s}  {a.a}  ->  {a.b}")
    for k, va, vb in rows:
        print(f"  {k:{width}s}  {va or '—'}  ->  {vb or '—'}")
    return 0


def _export(conn, a) -> int:
    text = admin.export_seed(conn, a.profile)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"  wrote {a.out}")
    else:
        sys.stdout.write(text)
    return 0


def _delete(conn, a) -> int:
    admin.delete_profile(conn, a.profile)
    print(f"  deleted {a.profile!r}")
    return 0


def _saves(conn, a) -> int:
    runs = list_runs(conn=conn)
    for s in runs:
        print(f"  {s.name:24s} round {s.round:<4d} money {s.money:<6d} profile {s.profile or '-':12s} {s.updated_at}")
    if not runs:
        print("  (no saves)")
    return 0


def _import(conn, a) -> int:
    results = import_json_saves(a.folder, overwrite=a.overwrite, conn=conn)
    for name, status in results.items():
        print(f"  {name}: {status}")
    if not results:
        print(f"  no .json files in {a.folder}")
    return 1 if any(s.startswith("error") for s in results.values()) else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m chaos_blackjack.data", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("profiles").set_defaults(fn=_profiles)
    s = sub.add_parser("show")
    s.add_argument("profile")
    s.set_defaults(fn=_show)
    s = sub.add_parser("clone")
    s.add_argument("source")
    s.add_argument("name")
    s.add_argument("-d", "--description", default="")
    s.set_defaults(fn=_clone)
    s = sub.add_parser("set")
    s.add_argument("profile")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(fn=_set)
    s = sub.add_parser("diff")
    s.add_argument("a")
    s.add_argument("b")
    s.set_defaults(fn=_diff)
    s = sub.add_parser("export")
    s.add_argument("profile")
    s.add_argument("-o", "--out", default=None)
    s.set_defaults(fn=_export)
    s = sub.add_parser("delete")
    s.add_argument("profile")
    s.set_defaults(fn=_delete)
    sub.add_parser("saves").set_defaults(fn=_saves)
    s = sub.add_parser("import-saves")
    s.add_argument("folder", nargs="?", default=str(LEGACY_SAVE_DIR))
    s.add_argument("--overwrite", action="store_true", help="replace saves that already exist")
    s.set_defaults(fn=_import)
    a = p.parse_args(argv)

    if a.cmd != "export" or a.out:
        print(f"database: {db_path()}")
    conn = connect()
    try:
        return a.fn(conn, a)
    except BalanceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
