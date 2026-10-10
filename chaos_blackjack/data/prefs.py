"""Player preferences in the `preference` table (JSON values).

    get_pref("gui.enable_chaos", False)
    set_pref("gui.enable_chaos", True)

Reads fall back to the default when the database cannot be opened, so a
read-only or broken data folder never stops the game from starting.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from chaos_blackjack.data.db import connect


def get_pref(key: str, default: Any = None, *, conn: sqlite3.Connection | None = None) -> Any:
    try:
        c = conn or connect()
    except (sqlite3.Error, OSError):
        return default
    try:
        row = c.execute("SELECT value FROM preference WHERE key = ?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])
    except (sqlite3.Error, ValueError):
        return default
    finally:
        if conn is None:
            c.close()


def set_pref(key: str, value: Any, *, conn: sqlite3.Connection | None = None) -> None:
    c = conn or connect()
    try:
        with c:
            c.execute(
                "INSERT INTO preference (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
    finally:
        if conn is None:
            c.close()
