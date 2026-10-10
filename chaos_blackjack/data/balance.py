"""Balance — every tunable number of a run, loaded from a database profile.

`Balance` is plain immutable data: game logic receives it (through
`RunConfig.from_balance`) and never touches the database itself.

    b = load_balance()                  # profile from $CHAOS_PROFILE, else "default"
    b = load_balance("tune-a", conn)
    b = default_balance()               # seed/default.sql via an in-memory database
    b.fingerprint                       # short hash; equal numbers -> equal hash
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from chaos_blackjack.data.db import MEMORY, connect

DEFAULT_PROFILE = "default"


class BalanceError(ValueError):
    """A profile is missing, incomplete or holds an invalid value."""


@dataclass(frozen=True)
class ShopItemBalance:
    item_id: str
    price: int
    price_mode: str = "fixed"
    weight: float = 1.0
    params: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Balance:
    profile: str
    start_money: int
    target_money: int
    objective: str
    dealer_stand_on: int
    blackjack_pays: tuple[int, int]
    allow_double: bool
    allow_surrender: bool
    shop_slots: int
    shop_refresh_rounds: int
    shop_items: tuple[ShopItemBalance, ...] = field(default=())

    @property
    def shop_prices(self) -> dict[str, int]:
        return {i.item_id: i.price for i in self.shop_items}

    @property
    def fingerprint(self) -> str:
        """Hash of the numbers only (not the profile name)."""
        data = asdict(self)
        data.pop("profile")
        blob = json.dumps(data, sort_keys=True, default=list).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:12]


# Setting key -> Balance field. Every key is required; unknown keys are errors
# so a typo in a profile cannot be silently ignored.
_SETTINGS: dict[str, str] = {
    "run.start_money": "start_money",
    "run.target_money": "target_money",
    "run.objective": "objective",
    "table.dealer_stand_on": "dealer_stand_on",
    "table.blackjack_pays_num": "_bj_num",
    "table.blackjack_pays_den": "_bj_den",
    "table.allow_double": "allow_double",
    "table.allow_surrender": "allow_surrender",
    "shop.slots": "shop_slots",
    "shop.refresh_rounds": "shop_refresh_rounds",
}


def _parse(key: str, raw: str, typ: str, lo: float | None, hi: float | None) -> Any:
    try:
        if typ == "int":
            value: Any = int(raw)
        elif typ == "float":
            value = float(raw)
        elif typ == "bool":
            if raw.strip().lower() not in ("0", "1", "true", "false"):
                raise ValueError(raw)
            value = raw.strip().lower() in ("1", "true")
        else:
            value = raw
    except ValueError:
        raise BalanceError(f"{key}: {raw!r} is not a valid {typ}") from None
    if typ in ("int", "float"):
        if lo is not None and value < lo:
            raise BalanceError(f"{key}: {value} is below the minimum {lo:g}")
        if hi is not None and value > hi:
            raise BalanceError(f"{key}: {value} is above the maximum {hi:g}")
    return value


def active_profile() -> str:
    return os.environ.get("CHAOS_PROFILE") or DEFAULT_PROFILE


def load_balance(profile: str | None = None, conn: sqlite3.Connection | None = None) -> Balance:
    """Read one profile. Opens data/game.db (or $CHAOS_DB) when `conn` is None."""
    name = profile or active_profile()
    own = conn is None
    conn = conn or connect()
    try:
        return _load(conn, name)
    finally:
        if own:
            conn.close()


def _load(conn: sqlite3.Connection, name: str) -> Balance:
    row = conn.execute("SELECT id FROM balance_profile WHERE name = ?", (name,)).fetchone()
    if row is None:
        known = [r[0] for r in conn.execute("SELECT name FROM balance_profile ORDER BY name")]
        raise BalanceError(f"Unknown balance profile {name!r}; known: {', '.join(known)}")
    pid = row[0]

    values: dict[str, Any] = {}
    for key, raw, typ, lo, hi in conn.execute(
        "SELECT key, value, type, min, max FROM setting WHERE profile_id = ?", (pid,)
    ):
        if key not in _SETTINGS:
            raise BalanceError(f"Profile {name!r}: unknown setting {key!r}")
        values[_SETTINGS[key]] = _parse(key, raw, typ, lo, hi)
    missing = sorted(k for k, f in _SETTINGS.items() if f not in values)
    if missing:
        raise BalanceError(f"Profile {name!r} is missing settings: {', '.join(missing)}")

    items = []
    for item_id, mode, price, weight, params in conn.execute(
        "SELECT item_id, price_mode, price, weight, params FROM shop_item "
        "WHERE profile_id = ? AND enabled = 1 ORDER BY item_id", (pid,)
    ):
        if mode != "fixed":
            raise BalanceError(f"Profile {name!r}: price mode {mode!r} for {item_id} is not supported yet")
        if price != int(price):
            raise BalanceError(f"Profile {name!r}: fixed price of {item_id} must be a whole number")
        p = json.loads(params) if params else {}
        items.append(ShopItemBalance(item_id, int(price), mode, float(weight), tuple(sorted(p.items()))))

    if values["target_money"] <= values["start_money"]:
        raise BalanceError(f"Profile {name!r}: run.target_money must be above run.start_money")
    num, den = values.pop("_bj_num"), values.pop("_bj_den")
    return Balance(profile=name, blackjack_pays=(num, den), shop_items=tuple(items), **values)


def clone_profile(conn: sqlite3.Connection, source: str, name: str, description: str = "") -> int:
    """Copy a profile (all settings, shop items, chaos rules) to a new, editable one."""
    src = conn.execute("SELECT id FROM balance_profile WHERE name = ?", (source,)).fetchone()
    if src is None:
        raise BalanceError(f"Unknown balance profile {source!r}")
    with conn:
        try:
            pid = conn.execute(
                "INSERT INTO balance_profile (name, parent_id, description) VALUES (?, ?, ?)",
                (name, src[0], description or f"Copy of {source}"),
            ).lastrowid
        except sqlite3.IntegrityError:
            raise BalanceError(f"Balance profile {name!r} already exists") from None
        conn.execute(
            "INSERT INTO setting (profile_id, key, value, type, min, max, description) "
            "SELECT ?, key, value, type, min, max, description FROM setting WHERE profile_id = ?", (pid, src[0]))
        conn.execute(
            "INSERT INTO shop_item (profile_id, item_id, enabled, price_mode, price, weight, params) "
            "SELECT ?, item_id, enabled, price_mode, price, weight, params FROM shop_item WHERE profile_id = ?",
            (pid, src[0]))
        conn.execute(
            "INSERT INTO chaos_rule (profile_id, rule_id, enabled, params, stub_weight) "
            "SELECT ?, rule_id, enabled, params, stub_weight FROM chaos_rule WHERE profile_id = ?", (pid, src[0]))
    return int(pid)


@lru_cache(maxsize=1)
def default_balance() -> Balance:
    """The shipped values (seed/default.sql), without touching data/game.db."""
    conn = connect(MEMORY)
    try:
        return _load(conn, DEFAULT_PROFILE)
    finally:
        conn.close()
