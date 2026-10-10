"""Run saves in the `run_save` table (data/game.db).

A save row holds the `RunSaveData` JSON plus the balance profile name and
fingerprint the run was played with, so a save restores its own numbers even
after the profile changes. Old JSON save files can be imported once with
`import_json_saves()` (or `python -m chaos_blackjack.data import-saves`).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.balance import config_fingerprint
from chaos_blackjack.data.db import PROJECT_ROOT, connect, db_path

DEFAULT_SAVE_NAME = "save_1"
LEGACY_SAVE_DIR = PROJECT_ROOT / "chaos_blackjack" / "saves"


class SaveNotFound(LookupError):
    pass


@dataclass(frozen=True)
class SaveInfo:
    name: str
    updated_at: str
    profile: str | None
    round: int
    money: int


def normalize_save_name(name: str) -> str:
    """Trimmed name without a `.json` suffix; empty -> "save_1"."""
    n = name.strip()
    if n.lower().endswith(".json"):
        n = n[:-5].strip()
    return n or DEFAULT_SAVE_NAME


@contextmanager
def _conn(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    if conn is not None:
        yield conn
        return
    own = connect()
    try:
        yield own
    finally:
        own.close()


def save_run(data: RunSaveData, name: str = DEFAULT_SAVE_NAME, *, conn: sqlite3.Connection | None = None) -> str:
    """Insert or overwrite a save; returns a locator like "data/game.db#save_1"."""
    key = normalize_save_name(name)
    config = data.config or {}
    profile = config.get("balance_profile")
    digest = config_fingerprint(config) if config else None
    payload = json.dumps(data.to_dict(), ensure_ascii=False)
    with _conn(conn) as c, c:
        c.execute(
            """INSERT INTO run_save (name, profile_name, balance_hash, save_version, data)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   profile_name = excluded.profile_name, balance_hash = excluded.balance_hash,
                   save_version = excluded.save_version, data = excluded.data,
                   updated_at = datetime('now')""",
            (key, profile, digest, int(data.version), payload),
        )
    return f"{db_path() if conn is None else 'db'}#{key}"


def load_run(name: str, *, conn: sqlite3.Connection | None = None) -> RunSaveData:
    key = normalize_save_name(name)
    with _conn(conn) as c:
        row = c.execute("SELECT data FROM run_save WHERE name = ?", (key,)).fetchone()
    if row is None:
        raise SaveNotFound(f"No save named {key!r}")
    payload = json.loads(row[0])
    if not isinstance(payload, dict):
        raise ValueError(f"Save {key!r} is not a JSON object")
    return RunSaveData.from_dict(payload)


def list_runs(*, conn: sqlite3.Connection | None = None) -> list[SaveInfo]:
    with _conn(conn) as c:
        rows = c.execute(
            "SELECT name, updated_at, profile_name, json_extract(data, '$.round'), "
            "json_extract(data, '$.money') FROM run_save ORDER BY name"
        ).fetchall()
    return [SaveInfo(r[0], r[1], r[2], int(r[3] or 0), int(r[4] or 0)) for r in rows]


def delete_run(name: str, *, conn: sqlite3.Connection | None = None) -> bool:
    with _conn(conn) as c, c:
        return c.execute("DELETE FROM run_save WHERE name = ?", (normalize_save_name(name),)).rowcount > 0


def import_json_saves(
    folder: str | Path = LEGACY_SAVE_DIR,
    *,
    overwrite: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, str]:
    """Copy `<name>.json` save files into the database. Files are left in place.
    Returns {name: "imported" | "skipped (exists)" | "error: ..."}."""
    results: dict[str, str] = {}
    folder = Path(folder)
    if not folder.is_dir():
        return results
    with _conn(conn) as c:
        existing = {r[0] for r in c.execute("SELECT name FROM run_save")}
        for path in sorted(folder.glob("*.json")):
            name = normalize_save_name(path.name)
            if name in existing and not overwrite:
                results[name] = "skipped (exists)"
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("not a JSON object")
                save_run(RunSaveData.from_dict(payload), name, conn=c)
                results[name] = "imported"
            except (ValueError, KeyError, TypeError) as e:
                results[name] = f"error: {e}"
    return results
