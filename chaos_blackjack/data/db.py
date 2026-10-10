"""SQLite storage: where the database lives, migrations and the seeded profiles.

    conn = connect()            # data/game.db (or $CHAOS_DB), migrated and seeded
    conn = connect(":memory:")  # tests and built-in defaults

Migrations are `migrations/NNNN_*.sql`, applied in order and recorded in
`schema_version`. Seed files `seed/<profile>.sql` define locked profiles
(`default`); a locked profile is re-imported whenever its seed file changes,
so the repository stays the source of truth for shipped values.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from importlib import resources
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "game.db"
MEMORY = ":memory:"


def db_path() -> str:
    """$CHAOS_DB if set, else data/game.db in the project."""
    return os.environ.get("CHAOS_DB") or str(DEFAULT_DB_PATH)


def connect(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    target = str(path) if path is not None else db_path()
    if target != MEMORY:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if target != MEMORY:
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    sync_seeds(conn)
    return conn


# --------------------------------------------------------------- migrations


def _package_files(folder: str) -> list[tuple[str, str]]:
    """(name, text) of every .sql file in a package folder, sorted by name."""
    root = resources.files("chaos_blackjack.data").joinpath(folder)
    return sorted((f.name, f.read_text(encoding="utf-8")) for f in root.iterdir() if f.name.endswith(".sql"))


def schema_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations; returns the schema version."""
    current = schema_version(conn)
    for name, sql in _package_files("migrations"):
        version = int(name.split("_", 1)[0])
        if version <= current:
            continue
        with conn:
            for statement in _statements(sql):
                conn.execute(statement)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        current = version
    return current


# --------------------------------------------------------------------- seeds


def _statements(sql: str) -> list[str]:
    """Split a script into complete statements (keeps `;` inside strings)."""
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        if not buf and line.strip().startswith("--"):
            continue
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def sync_seeds(conn: sqlite3.Connection) -> None:
    """(Re-)import every seed/<profile>.sql whose content changed."""
    for name, sql in _package_files("seed"):
        profile = name[:-4]
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]
        row = conn.execute(
            "SELECT id, source_hash FROM balance_profile WHERE name = ?", (profile,)
        ).fetchone()
        if row is not None and row["source_hash"] == digest:
            continue
        with conn:
            if row is None:
                pid = conn.execute(
                    "INSERT INTO balance_profile (name, description, locked, source_hash) VALUES (?, ?, 1, ?)",
                    (profile, f"Shipped values from seed/{name}", digest),
                ).lastrowid
            else:
                pid = row["id"]
                for table in ("setting", "shop_item", "chaos_rule"):
                    conn.execute(f"DELETE FROM {table} WHERE profile_id = ?", (pid,))
                conn.execute("UPDATE balance_profile SET source_hash = ?, locked = 1 WHERE id = ?", (digest, pid))
            for statement in _statements(sql):
                conn.execute(statement, {"profile": pid})
