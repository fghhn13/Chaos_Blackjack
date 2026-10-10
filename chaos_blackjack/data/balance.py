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


# RunConfig keys that describe a run rather than the balance.
_NOT_BALANCE = frozenset({"enable_chaos", "seed", "balance_profile"})


def config_fingerprint(config: dict[str, Any]) -> str:
    """Short hash of a RunConfig.to_dict(): equal numbers -> equal hash."""
    data = {k: v for k, v in config.items() if k not in _NOT_BALANCE}
    blob = json.dumps(data, sort_keys=True, default=list).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


class BalanceError(ValueError):
    """A profile is missing, incomplete or holds an invalid value."""


@dataclass(frozen=True)
class ShopItemBalance:
    item_id: str
    price: int
    price_mode: str = "fixed"
    weight: float = 1.0
    params: tuple[tuple[str, Any], ...] = ()


Params = tuple[tuple[str, Any], ...]  # a JSON object as sorted (key, value) pairs


@dataclass(frozen=True)
class ChaosRuleBalance:
    rule_id: str
    enabled: bool = True
    params: Params = ()        # fixed tuning; wins over the AI's params
    stub_weight: float = 0.0   # how often the offline Chaos AI picks it
    stub_params: Params = ()   # what the offline Chaos AI sends with it


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
    min_bet: int
    max_bet_fraction: float
    shop_items: tuple[ShopItemBalance, ...] = field(default=())
    item_tuning: tuple[tuple[str, Params], ...] = field(default=())  # every item, sold or not
    chaos_rules: tuple[ChaosRuleBalance, ...] = field(default=())

    @property
    def shop_prices(self) -> dict[str, int]:
        return {i.item_id: i.price for i in self.shop_items}

    @property
    def item_params(self) -> dict[str, dict[str, Any]]:
        return {item: dict(p) for item, p in self.item_tuning if p}

    @property
    def chaos_rule_params(self) -> dict[str, dict[str, Any]]:
        return {r.rule_id: dict(r.params) for r in self.chaos_rules if r.params}

    @property
    def disabled_rules(self) -> tuple[str, ...]:
        return tuple(r.rule_id for r in self.chaos_rules if not r.enabled)

    @property
    def chaos_stub(self) -> tuple[tuple[str, dict[str, Any], float], ...]:
        """(rule_id, params, weight) for the offline Chaos AI; enabled rules only."""
        return tuple((r.rule_id, dict(r.stub_params), r.stub_weight)
                     for r in self.chaos_rules if r.enabled and r.stub_weight > 0)

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
    "bet.min": "min_bet",
    "bet.max_fraction": "max_bet_fraction",
}


def _params(where: str, raw: str | None) -> Params:
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise BalanceError(f"{where}: params are not valid JSON ({e.msg})") from None
    if not isinstance(value, dict):
        raise BalanceError(f"{where}: params must be a JSON object")
    return tuple(sorted(value.items()))


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
        items.append(ShopItemBalance(item_id, int(price), mode, float(weight),
                                     _params(f"Profile {name!r}, item {item_id}", params)))
    tuning = tuple(
        (item_id, _params(f"Profile {name!r}, item {item_id}", params))
        for item_id, params in conn.execute(
            "SELECT item_id, params FROM shop_item WHERE profile_id = ? ORDER BY item_id", (pid,))
    )
    rules = tuple(
        ChaosRuleBalance(
            rule_id, bool(enabled), _params(f"Profile {name!r}, rule {rule_id}", params),
            float(weight), _params(f"Profile {name!r}, rule {rule_id} stub", stub_params),
        )
        for rule_id, enabled, params, weight, stub_params in conn.execute(
            "SELECT rule_id, enabled, params, stub_weight, stub_params FROM chaos_rule "
            "WHERE profile_id = ? ORDER BY rule_id", (pid,))
    )

    if values["target_money"] <= values["start_money"]:
        raise BalanceError(f"Profile {name!r}: run.target_money must be above run.start_money")
    num, den = values.pop("_bj_num"), values.pop("_bj_den")
    return Balance(profile=name, blackjack_pays=(num, den), shop_items=tuple(items),
                   item_tuning=tuning, chaos_rules=rules, **values)


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
            "INSERT INTO chaos_rule (profile_id, rule_id, enabled, params, stub_weight, stub_params) "
            "SELECT ?, rule_id, enabled, params, stub_weight, stub_params FROM chaos_rule WHERE profile_id = ?",
            (pid, src[0]))
    return int(pid)


@lru_cache(maxsize=1)
def default_balance() -> Balance:
    """The shipped values (seed/default.sql), without touching data/game.db."""
    conn = connect(MEMORY)
    try:
        return _load(conn, DEFAULT_PROFILE)
    finally:
        conn.close()
