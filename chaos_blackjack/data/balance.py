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
_NOT_BALANCE = frozenset({"enable_chaos", "seed", "balance_profile", "use_llm", "ai_id", "content_packs"})


def config_fingerprint(config: dict[str, Any]) -> str:
    """Short hash of a RunConfig.to_dict(): equal numbers -> equal hash."""
    data = {k: v for k, v in config.items() if k not in _NOT_BALANCE}
    blob = json.dumps(data, sort_keys=True, default=list).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


class BalanceError(ValueError):
    """A profile is missing, incomplete or holds an invalid value."""


PRICE_MODES = ("fixed", "bankroll_pct")


@dataclass(frozen=True)
class ShopItemBalance:
    item_id: str
    price: int                 # chips (fixed) or percent of the bankroll (bankroll_pct)
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
class MetaUpgradeBalance:
    """One meta-shop upgrade: an effect (code, chaos_blackjack/meta/effects.py) plus its numbers."""

    upgrade_id: str
    kind: str                  # permanent | consumable
    effect: str
    params: Params = ()
    cost: int = 0
    cost_step: int = 0         # permanent: each further level costs this much more
    max_level: int = 1         # permanent: levels; consumable: most copies held
    requires: str | None = None

    def cost_of_level(self, level: int) -> int:
        """Cost of level `level` (1-based) of a permanent upgrade; consumables always cost `cost`."""
        if self.kind != "permanent":
            return self.cost
        return self.cost + (max(1, level) - 1) * self.cost_step


@dataclass(frozen=True)
class CosmeticPriceBalance:
    """A cosmetic sold in the wardrobe (catalog: chaos_blackjack/cosmetics)."""

    cosmetic_id: str
    cost: int


@dataclass(frozen=True)
class AchievementRewardBalance:
    """What unlocking an achievement pays (catalog: chaos_blackjack/achievements)."""

    achievement_id: str
    tokens: int = 0
    cosmetic_id: str | None = None


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
    chaos_guidance_probability: float
    chaos_memory_enabled: bool
    chaos_memory_limit: int
    meta_win_tokens: int
    meta_loss_per_round: float
    meta_loss_per_peak_gain: float
    meta_loss_cap: int
    # Added after the first profiles were cloned; optional with these defaults.
    shop_reroll_price: int = 10
    chaos_stub_calm_weight: float = 0.0
    meta_chaos_win_bonus: int = 0
    meta_bring_kinds: int = 99
    shop_items: tuple[ShopItemBalance, ...] = field(default=())
    item_tuning: tuple[tuple[str, Params], ...] = field(default=())  # every item, sold or not
    chaos_rules: tuple[ChaosRuleBalance, ...] = field(default=())
    meta_upgrades: tuple[MetaUpgradeBalance, ...] = field(default=())  # enabled ones only
    cosmetic_prices: tuple[CosmeticPriceBalance, ...] = field(default=())  # enabled ones only
    achievement_rewards: tuple[AchievementRewardBalance, ...] = field(default=())

    @property
    def shop_prices(self) -> dict[str, int]:
        return {i.item_id: i.price for i in self.shop_items}

    @property
    def shop_bankroll_pct(self) -> tuple[str, ...]:
        """Items priced as a percentage of the bankroll."""
        return tuple(i.item_id for i in self.shop_items if i.price_mode == "bankroll_pct")

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
        """(rule_id, params, weight) for the offline Chaos AI; enabled rules only.
        A calm round (no rule) is the entry with rule_id ""."""
        rules = tuple((r.rule_id, dict(r.stub_params), r.stub_weight)
                      for r in self.chaos_rules if r.enabled and r.stub_weight > 0)
        calm = (("", {}, self.chaos_stub_calm_weight),) if self.chaos_stub_calm_weight > 0 and rules else ()
        return rules + calm

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
    "chaos.guidance_probability": "chaos_guidance_probability",
    "chaos.memory_enabled": "chaos_memory_enabled",
    "chaos.memory_limit": "chaos_memory_limit",
    "meta.win_tokens": "meta_win_tokens",
    "meta.loss_per_round": "meta_loss_per_round",
    "meta.loss_per_peak_gain": "meta_loss_per_peak_gain",
    "meta.loss_cap": "meta_loss_cap",
}
# Settings added later: profiles cloned before them load with the field default.
_OPTIONAL_SETTINGS: dict[str, str] = {
    "shop.reroll_price": "shop_reroll_price",
    "chaos.stub_calm_weight": "chaos_stub_calm_weight",
    "meta.chaos_win_bonus": "meta_chaos_win_bonus",
    "meta.bring_kinds": "meta_bring_kinds",
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
        field_name = _SETTINGS.get(key) or _OPTIONAL_SETTINGS.get(key)
        if field_name is None:
            raise BalanceError(f"Profile {name!r}: unknown setting {key!r}")
        values[field_name] = _parse(key, raw, typ, lo, hi)
    missing = sorted(k for k, f in _SETTINGS.items() if f not in values)
    if missing:
        raise BalanceError(f"Profile {name!r} is missing settings: {', '.join(missing)}")

    items = []
    for item_id, mode, price, weight, params in conn.execute(
        "SELECT item_id, price_mode, price, weight, params FROM shop_item "
        "WHERE profile_id = ? AND enabled = 1 ORDER BY item_id", (pid,)
    ):
        if mode not in PRICE_MODES:
            raise BalanceError(f"Profile {name!r}: price mode {mode!r} for {item_id} is not supported")
        if price != int(price):
            raise BalanceError(f"Profile {name!r}: price of {item_id} must be a whole number")
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
    upgrades = tuple(
        MetaUpgradeBalance(
            upgrade_id, kind, effect, _params(f"Profile {name!r}, upgrade {upgrade_id}", params),
            int(cost), int(cost_step), int(max_level), requires or None,
        )
        for upgrade_id, kind, effect, params, cost, cost_step, max_level, requires in conn.execute(
            "SELECT upgrade_id, kind, effect, params, cost, cost_step, max_level, requires FROM meta_upgrade "
            "WHERE profile_id = ? AND enabled = 1 ORDER BY upgrade_id", (pid,))
    )
    known_upgrades = {u.upgrade_id for u in upgrades}
    for u in upgrades:
        if u.requires and u.requires not in known_upgrades:
            raise BalanceError(f"Profile {name!r}: upgrade {u.upgrade_id} requires unknown upgrade {u.requires!r}")

    prices = tuple(
        CosmeticPriceBalance(cosmetic_id, int(cost))
        for cosmetic_id, cost in conn.execute(
            "SELECT cosmetic_id, cost FROM cosmetic_price WHERE profile_id = ? AND enabled = 1 ORDER BY cosmetic_id",
            (pid,))
    )
    rewards = tuple(
        AchievementRewardBalance(achievement_id, int(tokens), cosmetic_id or None)
        for achievement_id, tokens, cosmetic_id in conn.execute(
            "SELECT achievement_id, tokens, cosmetic_id FROM achievement_reward WHERE profile_id = ? "
            "ORDER BY achievement_id", (pid,))
    )

    if values["target_money"] <= values["start_money"]:
        raise BalanceError(f"Profile {name!r}: run.target_money must be above run.start_money")
    num, den = values.pop("_bj_num"), values.pop("_bj_den")
    return Balance(profile=name, blackjack_pays=(num, den), shop_items=tuple(items),
                   item_tuning=tuning, chaos_rules=rules, meta_upgrades=upgrades, cosmetic_prices=prices,
                   achievement_rewards=rewards, **values)


def clone_profile(conn: sqlite3.Connection, source: str, name: str, description: str = "") -> int:
    """Copy a profile (settings, shop items, chaos rules, meta upgrades, cosmetic prices,
    achievement rewards) to a new, editable one."""
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
        conn.execute(
            "INSERT INTO meta_upgrade (profile_id, upgrade_id, kind, effect, params, cost, cost_step, max_level, "
            "enabled, requires) SELECT ?, upgrade_id, kind, effect, params, cost, cost_step, max_level, enabled, "
            "requires FROM meta_upgrade WHERE profile_id = ?", (pid, src[0]))
        conn.execute(
            "INSERT INTO cosmetic_price (profile_id, cosmetic_id, cost, enabled) "
            "SELECT ?, cosmetic_id, cost, enabled FROM cosmetic_price WHERE profile_id = ?", (pid, src[0]))
        conn.execute(
            "INSERT INTO achievement_reward (profile_id, achievement_id, tokens, cosmetic_id) "
            "SELECT ?, achievement_id, tokens, cosmetic_id FROM achievement_reward WHERE profile_id = ?",
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
