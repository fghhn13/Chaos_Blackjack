"""Balance profile management: list, show, edit, compare, export, delete.

Keys address one value of a profile:
  <setting key>              run.start_money, bet.max_fraction, shop.slots, ...
  item.<item_id>.<field>     price, enabled, weight, params (JSON), price_mode
  rule.<rule_id>.<field>     enabled, params (JSON), stub_weight, stub_params (JSON)
  upgrade.<upgrade_id>.<field>  cost, cost_step, max_level, enabled, params (JSON), requires

Every edit is validated by loading the profile inside the same transaction;
an invalid value is rolled back. Locked (seeded) profiles cannot be edited:
clone them first, or change seed/<name>.sql.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from chaos_blackjack.data.balance import PRICE_MODES, BalanceError, load_balance

ITEM_FIELDS = ("price", "enabled", "weight", "params", "price_mode")
RULE_FIELDS = ("enabled", "params", "stub_weight", "stub_params")
UPGRADE_FIELDS = ("cost", "cost_step", "max_level", "enabled", "params", "requires")
# key prefix -> (table, id column, editable fields)
_TABLES = {
    "item": ("shop_item", "item_id", ITEM_FIELDS),
    "rule": ("chaos_rule", "rule_id", RULE_FIELDS),
    "upgrade": ("meta_upgrade", "upgrade_id", UPGRADE_FIELDS),
}
_JSON_FIELDS = {"params", "stub_params"}


@dataclass(frozen=True)
class ProfileInfo:
    name: str
    locked: bool
    parent: str | None
    description: str
    created_at: str


def _profile(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM balance_profile WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise BalanceError(f"Unknown balance profile {name!r}")
    return row


def list_profiles(conn: sqlite3.Connection) -> list[ProfileInfo]:
    rows = conn.execute(
        "SELECT p.name, p.locked, q.name AS parent, p.description, p.created_at "
        "FROM balance_profile p LEFT JOIN balance_profile q ON q.id = p.parent_id ORDER BY p.name"
    ).fetchall()
    return [ProfileInfo(r["name"], bool(r["locked"]), r["parent"], r["description"], r["created_at"]) for r in rows]


def profile_values(conn: sqlite3.Connection, name: str) -> dict[str, str]:
    """Every value of a profile as {key: text}, using the key forms above."""
    pid = _profile(conn, name)["id"]
    out: dict[str, str] = {}
    for key, value in conn.execute("SELECT key, value FROM setting WHERE profile_id = ?", (pid,)):
        out[key] = value
    for row in conn.execute("SELECT * FROM shop_item WHERE profile_id = ?", (pid,)):
        for f in ITEM_FIELDS:
            out[f"item.{row['item_id']}.{f}"] = _text(row[f], f)
    for row in conn.execute("SELECT * FROM chaos_rule WHERE profile_id = ?", (pid,)):
        for f in RULE_FIELDS:
            out[f"rule.{row['rule_id']}.{f}"] = _text(row[f], f)
    for row in conn.execute("SELECT * FROM meta_upgrade WHERE profile_id = ?", (pid,)):
        for f in UPGRADE_FIELDS:
            out[f"upgrade.{row['upgrade_id']}.{f}"] = _text(row[f], f)
    return dict(sorted(out.items()))


def _text(v: object, field: str = "") -> str:
    if v is None:
        return ""
    if field in _JSON_FIELDS:
        try:
            return json.dumps(json.loads(str(v)), sort_keys=True)  # key order never shows as a diff
        except json.JSONDecodeError:
            return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _value(field: str, raw: str) -> object:
    if field in _JSON_FIELDS:
        if raw.strip() in ("", "null", "{}"):
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise BalanceError(f"{field}: not valid JSON ({e.msg})") from None
        if not isinstance(parsed, dict):
            raise BalanceError(f"{field}: must be a JSON object")
        return json.dumps(parsed, sort_keys=True)
    if field == "enabled":
        low = raw.strip().lower()
        if low not in ("0", "1", "true", "false", "on", "off"):
            raise BalanceError("enabled: use 1/0, true/false or on/off")
        return int(low in ("1", "true", "on"))
    if field == "price_mode":
        mode = raw.strip()
        if mode not in PRICE_MODES:
            raise BalanceError(f"price_mode: use one of {', '.join(PRICE_MODES)}")
        return mode
    if field == "requires":
        return raw.strip() or None
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except ValueError:
        raise BalanceError(f"{field}: {raw!r} is not a number") from None


def set_value(conn: sqlite3.Connection, profile: str, key: str, raw: str) -> None:
    """Change one value; raises BalanceError (and changes nothing) if invalid."""
    row = _profile(conn, profile)
    if row["locked"]:
        raise BalanceError(f"Profile {profile!r} is locked (seeded); clone it first")
    pid = row["id"]
    parts = key.split(".")
    try:
        with conn:
            if parts[0] in _TABLES and len(parts) == 3:
                table, id_col, fields = _TABLES[parts[0]]
                if parts[2] not in fields:
                    raise BalanceError(f"{key}: field must be one of {', '.join(fields)}")
                cur = conn.execute(f"UPDATE {table} SET {parts[2]} = ? WHERE profile_id = ? AND {id_col} = ?",
                                   (_value(parts[2], raw), pid, parts[1]))
            else:
                cur = conn.execute("UPDATE setting SET value = ? WHERE profile_id = ? AND key = ?",
                                   (raw.strip(), pid, key))
            if cur.rowcount == 0:
                raise BalanceError(f"Profile {profile!r} has no value {key!r}")
            load_balance(profile, conn)  # validate before commit
    except sqlite3.IntegrityError as e:
        raise BalanceError(f"{key}: {e}") from None


def diff_profiles(conn: sqlite3.Connection, a: str, b: str) -> list[tuple[str, str, str]]:
    """(key, value in a, value in b) for every key that differs."""
    va, vb = profile_values(conn, a), profile_values(conn, b)
    return [(k, va.get(k, "—"), vb.get(k, "—")) for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)]


def delete_profile(conn: sqlite3.Connection, name: str) -> None:
    row = _profile(conn, name)
    if row["locked"]:
        raise BalanceError(f"Profile {name!r} is locked (seeded) and cannot be deleted")
    with conn:
        conn.execute("DELETE FROM balance_profile WHERE id = ?", (row["id"],))


def _sql(v: object) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return _text(v)
    return "'" + str(v).replace("'", "''") + "'"


def export_seed(conn: sqlite3.Connection, name: str) -> str:
    """A profile as a seed file (same format as seed/default.sql). Saving it as
    seed/default.sql makes it the shipped default."""
    pid = _profile(conn, name)["id"]
    out = [
        f"-- Balance profile exported from {name!r}. To ship it, save as",
        "-- chaos_blackjack/data/seed/default.sql and update black-jack-sim/bands.json.",
        "-- `:profile` is the id of the profile row, bound by the loader.",
        "",
        "INSERT INTO setting (profile_id, key, value, type, min, max, description) VALUES",
    ]
    rows = conn.execute("SELECT * FROM setting WHERE profile_id = ? ORDER BY key", (pid,)).fetchall()
    out.append(",\n".join(
        f"    (:profile, {_sql(r['key'])}, {_sql(r['value'])}, {_sql(r['type'])}, {_sql(r['min'])}, "
        f"{_sql(r['max'])}, {_sql(r['description'])})" for r in rows) + ";")
    rows = conn.execute("SELECT * FROM shop_item WHERE profile_id = ? ORDER BY item_id", (pid,)).fetchall()
    if rows:
        out += ["", "INSERT INTO shop_item (profile_id, item_id, enabled, price_mode, price, weight, params) VALUES"]
        out.append(",\n".join(
            f"    (:profile, {_sql(r['item_id'])}, {_sql(r['enabled'])}, {_sql(r['price_mode'])}, "
            f"{_sql(r['price'])}, {_sql(r['weight'])}, {_sql(r['params'])})" for r in rows) + ";")
    rows = conn.execute("SELECT * FROM chaos_rule WHERE profile_id = ? ORDER BY rule_id", (pid,)).fetchall()
    if rows:
        out += ["", "INSERT INTO chaos_rule (profile_id, rule_id, enabled, params, stub_weight, stub_params) VALUES"]
        out.append(",\n".join(
            f"    (:profile, {_sql(r['rule_id'])}, {_sql(r['enabled'])}, {_sql(r['params'])}, "
            f"{_sql(r['stub_weight'])}, {_sql(r['stub_params'])})" for r in rows) + ";")
    rows = conn.execute("SELECT * FROM meta_upgrade WHERE profile_id = ? ORDER BY upgrade_id", (pid,)).fetchall()
    if rows:
        out += ["", "INSERT INTO meta_upgrade (profile_id, upgrade_id, kind, effect, params, cost, cost_step, "
                    "max_level, enabled, requires) VALUES"]
        out.append(",\n".join(
            f"    (:profile, {_sql(r['upgrade_id'])}, {_sql(r['kind'])}, {_sql(r['effect'])}, {_sql(r['params'])}, "
            f"{_sql(r['cost'])}, {_sql(r['cost_step'])}, {_sql(r['max_level'])}, {_sql(r['enabled'])}, "
            f"{_sql(r['requires'])})" for r in rows) + ";")
    return "\n".join(out) + "\n"
