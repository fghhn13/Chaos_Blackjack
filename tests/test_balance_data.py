"""SQLite balance profiles: schema, seeding, loading, validation and wiring."""

from __future__ import annotations

from dataclasses import fields

import pytest

from chaos_blackjack.agent.session import AgentSession
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.persistence import build_save_data
from chaos_blackjack.data import BalanceError, clone_profile, connect, default_balance, load_balance
from chaos_blackjack.data.db import schema_version


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "game.db"
    monkeypatch.setenv("CHAOS_DB", str(path))
    conn = connect(path)
    yield conn
    conn.close()


def _set(conn, profile: str, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "UPDATE setting SET value = ? WHERE key = ? AND profile_id = "
            "(SELECT id FROM balance_profile WHERE name = ?)", (value, key, profile))


# ------------------------------------------------------------- defaults


def test_shipped_values_are_unchanged() -> None:
    b = default_balance()
    assert (b.start_money, b.target_money, b.objective) == (100, 400, "double_money")
    assert (b.dealer_stand_on, b.blackjack_pays, b.allow_double, b.allow_surrender) == (17, (3, 2), True, True)
    assert (b.shop_slots, b.shop_refresh_rounds) == (3, 2)
    assert b.shop_prices == {"peek": 10, "danger_radar": 10, "swap": 20, "hole_card_hacker": 25,
                             "fate_oracle": 25, "shield": 30}


def test_run_config_defaults_come_from_the_seed() -> None:
    a, b = RunConfig(), RunConfig.from_balance(default_balance())
    assert all(getattr(a, f.name) == getattr(b, f.name) for f in fields(RunConfig))


# ------------------------------------------------------------ database


def test_database_is_created_migrated_and_seeded(db, tmp_path) -> None:
    assert (tmp_path / "game.db").is_file()
    assert schema_version(db) == 1
    row = db.execute("SELECT locked, source_hash FROM balance_profile WHERE name = 'default'").fetchone()
    assert row["locked"] == 1 and row["source_hash"]
    again = connect(tmp_path / "game.db")  # idempotent
    assert again.execute("SELECT COUNT(*) FROM balance_profile").fetchone()[0] == 1
    again.close()


def test_default_profile_is_restored_from_the_seed(db, tmp_path) -> None:
    _set(db, "default", "run.start_money", "999")
    with db:
        db.execute("UPDATE balance_profile SET source_hash = 'stale' WHERE name = 'default'")
    conn = connect(tmp_path / "game.db")
    assert load_balance("default", conn).start_money == 100
    conn.close()


def test_cloned_profile_is_independent(db, tmp_path) -> None:
    clone_profile(db, "default", "tune-a")
    _set(db, "tune-a", "run.start_money", "150")
    with db:
        db.execute("UPDATE shop_item SET price = 12 WHERE item_id = 'peek' AND profile_id = "
                   "(SELECT id FROM balance_profile WHERE name = 'tune-a')")
    tuned = load_balance("tune-a", db)
    assert tuned.start_money == 150 and tuned.shop_prices["peek"] == 12
    assert tuned.fingerprint != default_balance().fingerprint
    assert load_balance("default", db) == default_balance()
    with pytest.raises(BalanceError):
        clone_profile(db, "default", "tune-a")


def test_fingerprint_ignores_the_profile_name(db) -> None:
    clone_profile(db, "default", "same")
    assert load_balance("same", db).fingerprint == default_balance().fingerprint


def test_active_profile_from_environment(db, monkeypatch) -> None:
    clone_profile(db, "default", "env-pick")
    monkeypatch.setenv("CHAOS_PROFILE", "env-pick")
    assert load_balance().profile == "env-pick"


# ----------------------------------------------------------- validation


@pytest.mark.parametrize("key, value, message", [
    ("run.start_money", "1", "below the minimum"),
    ("run.start_money", "lots", "not a valid int"),
    ("table.allow_double", "maybe", "not a valid bool"),
    ("table.dealer_stand_on", "31", "above the maximum"),
    ("run.target_money", "50", "must be above"),
])
def test_invalid_values_are_rejected(db, key, value, message) -> None:
    clone_profile(db, "default", "bad")
    _set(db, "bad", key, value)
    with pytest.raises(BalanceError, match=message):
        load_balance("bad", db)


def test_unknown_and_missing_settings_are_rejected(db) -> None:
    clone_profile(db, "default", "typo")
    with db:
        db.execute("UPDATE setting SET key = 'run.start_mony' WHERE key = 'run.start_money' AND profile_id = "
                   "(SELECT id FROM balance_profile WHERE name = 'typo')")
    with pytest.raises(BalanceError, match="unknown setting"):
        load_balance("typo", db)
    with db:
        db.execute("DELETE FROM setting WHERE key = 'run.start_mony'")
    with pytest.raises(BalanceError, match="missing settings"):
        load_balance("typo", db)


def test_unknown_profile_and_unsupported_price_mode(db) -> None:
    with pytest.raises(BalanceError, match="Unknown balance profile"):
        load_balance("nope", db)
    clone_profile(db, "default", "pct")
    with db:
        db.execute("UPDATE shop_item SET price_mode = 'bankroll_pct' WHERE item_id = 'peek'")
    with pytest.raises(BalanceError, match="not supported yet"):
        load_balance("pct", db)


# --------------------------------------------------------------- wiring


def test_agent_runs_use_a_profile_and_keep_it(db) -> None:
    clone_profile(db, "default", "rich")
    _set(db, "rich", "run.start_money", "200")
    _set(db, "rich", "table.allow_surrender", "0")
    s = AgentSession.new(seed=3, profile="rich")
    assert s.observe()["bankroll"] == 200
    _set(db, "rich", "run.start_money", "300")  # later edits do not touch a running run
    again = AgentSession.from_state(s.to_state())
    assert again.observe()["bankroll"] == 200
    assert again.controller.config.balance_profile == "rich"
    assert again.controller.config.allow_surrender is False


def test_loading_a_save_keeps_table_rules() -> None:
    cfg = RunConfig(blackjack_pays=(6, 5), allow_double=False, shop_slots=2)
    c = GameController(cfg)
    data = build_save_data(run=c.run, state=None, loop=c.loop, enable_chaos=False)
    loaded = GameController.from_save(data, cfg)
    assert loaded.config.blackjack_pays == (6, 5)
    assert loaded.config.allow_double is False and loaded.config.shop_slots == 2
