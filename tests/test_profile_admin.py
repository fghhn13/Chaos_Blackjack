"""Balance profile management (python -m chaos_blackjack.data ...)."""

from __future__ import annotations

import pytest

from chaos_blackjack.data import BalanceError, admin, clone_profile, connect, default_balance, load_balance
from chaos_blackjack.data.__main__ import main as data_cli
from chaos_blackjack.data.db import _statements


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    path = tmp_path / "game.db"
    monkeypatch.setenv("CHAOS_DB", str(path))
    c = connect(path)
    clone_profile(c, "default", "tune")
    yield c
    c.close()


def test_set_edits_every_kind_of_value(conn) -> None:
    admin.set_value(conn, "tune", "run.start_money", "150")
    admin.set_value(conn, "tune", "item.peek.price", "6")
    admin.set_value(conn, "tune", "item.swap.enabled", "off")
    admin.set_value(conn, "tune", "rule.great_crash.params", '{"ten_value": 5}')
    admin.set_value(conn, "tune", "rule.great_crash.stub_weight", "2")
    b = load_balance("tune", conn)
    assert b.start_money == 150 and b.shop_prices["peek"] == 6 and "swap" not in b.shop_prices
    assert b.chaos_rule_params["great_crash"] == {"ten_value": 5}
    assert ("great_crash", {}, 2.0) in b.chaos_stub


@pytest.mark.parametrize("key, value, message", [
    ("run.start_money", "1", "below the minimum"),
    ("run.start_mony", "5", "has no value"),
    ("item.peek.colour", "red", "field must be one of"),
    ("item.nothing.price", "5", "has no value"),
    ("item.peek.price", "-1", "CHECK"),
    ("item.peek.price", "cheap", "not a number"),
    ("rule.great_crash.params", "[1]", "JSON object"),
    ("rule.great_crash.enabled", "maybe", "on/off"),
    ("item.peek.price_mode", "percent", "use one of fixed, bankroll_pct"),
])
def test_invalid_edits_change_nothing(conn, key, value, message) -> None:
    before = admin.profile_values(conn, "tune")
    with pytest.raises(BalanceError, match=message):
        admin.set_value(conn, "tune", key, value)
    assert admin.profile_values(conn, "tune") == before


def test_locked_profiles_refuse_edits_and_deletion(conn) -> None:
    with pytest.raises(BalanceError, match="locked"):
        admin.set_value(conn, "default", "run.start_money", "50")
    with pytest.raises(BalanceError, match="locked"):
        admin.delete_profile(conn, "default")


def test_diff_and_delete(conn) -> None:
    assert admin.diff_profiles(conn, "default", "tune") == []
    admin.set_value(conn, "tune", "bet.max_fraction", "0.4")
    admin.set_value(conn, "tune", "rule.odd_even_chaos.params", '{"odd_delta": -1, "even_delta": 3}')
    assert admin.diff_profiles(conn, "default", "tune") == [
        ("bet.max_fraction", "0.5", "0.4"),
        ("rule.odd_even_chaos.params", '{"even_delta": 2, "odd_delta": -1}', '{"even_delta": 3, "odd_delta": -1}'),
    ]
    admin.delete_profile(conn, "tune")
    assert [p.name for p in admin.list_profiles(conn)] == ["default"]


def test_export_round_trips_through_a_seed(conn) -> None:
    admin.set_value(conn, "tune", "item.fate_oracle.params", '{"cards": 2}')
    admin.set_value(conn, "tune", "table.allow_surrender", "0")
    text = admin.export_seed(conn, "tune")
    fresh = connect(":memory:")
    with fresh:
        pid = fresh.execute("INSERT INTO balance_profile (name) VALUES ('imported')").lastrowid
        for statement in _statements(text):
            fresh.execute(statement, {"profile": pid})
    assert load_balance("imported", fresh).fingerprint == load_balance("tune", conn).fingerprint
    assert admin.export_seed(connect(":memory:"), "default").count("INSERT") == 6


def test_default_export_matches_the_shipped_values(conn) -> None:
    assert load_balance("default", conn).fingerprint == default_balance().fingerprint


def test_cli_controls_chaos_memory_and_advice_probability(conn) -> None:
    from chaos_blackjack.app.config import RunConfig

    assert data_cli(["set", "tune", "chaos.guidance_probability", "0.75"]) == 0
    assert data_cli(["set", "tune", "chaos.memory_enabled", "1"]) == 0
    assert data_cli(["set", "tune", "chaos.memory_limit", "7"]) == 0
    cfg = RunConfig.from_balance(load_balance("tune", conn))
    assert (cfg.chaos_guidance_probability, cfg.chaos_memory_enabled, cfg.chaos_memory_limit) == (.75, True, 7)
    before = admin.profile_values(conn, "tune")
    assert data_cli(["set", "tune", "chaos.guidance_probability", "1.1"]) == 1
    assert admin.profile_values(conn, "tune") == before


def test_cli(conn, tmp_path, capsys) -> None:
    assert data_cli(["clone", "tune", "tune2", "-d", "test"]) == 0
    assert data_cli(["set", "tune2", "item.peek.price", "7"]) == 0
    assert data_cli(["set", "default", "item.peek.price", "7"]) == 1
    assert data_cli(["diff", "tune", "tune2"]) == 0
    assert data_cli(["show", "tune2"]) == 0
    assert data_cli(["profiles"]) == 0
    out = tmp_path / "seed.sql"
    assert data_cli(["export", "tune2", "-o", str(out)]) == 0 and "'peek', 1, 'bankroll_pct', 7" in out.read_text("utf-8")
    assert data_cli(["delete", "tune2"]) == 0
    text = capsys.readouterr()
    assert "item.peek.price 4 -> 7" in text.out and "locked" in text.err
    assert "item.peek.price  4  ->  7" in text.out and "valid; fingerprint" in text.out
