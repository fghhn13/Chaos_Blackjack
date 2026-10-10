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
    assert schema_version(db) == 2
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


# ------------------------------------------------- phase 2: tuning in data


def _profile(db, name: str) -> int:
    clone_profile(db, "default", name)
    return db.execute("SELECT id FROM balance_profile WHERE name = ?", (name,)).fetchone()[0]


def _rule(db, pid: int, rule_id: str, **cols) -> None:
    sets = ", ".join(f"{k} = ?" for k in cols)
    with db:
        db.execute(f"UPDATE chaos_rule SET {sets} WHERE profile_id = ? AND rule_id = ?",
                   (*cols.values(), pid, rule_id))


def _only_stub(db, pid: int, rule_id: str, stub_params: str | None = None) -> None:
    with db:
        db.execute("UPDATE chaos_rule SET stub_weight = 0 WHERE profile_id = ?", (pid,))
    _rule(db, pid, rule_id, stub_weight=1, stub_params=stub_params)


def _chaos_ctrl(balance, seed: int = 5) -> GameController:
    return GameController(RunConfig.from_balance(balance, enable_chaos=True, seed=seed))


def test_old_databases_are_migrated(tmp_path) -> None:
    import sqlite3
    from importlib import resources

    path = tmp_path / "v1.db"
    raw = sqlite3.connect(path)
    raw.executescript(resources.files("chaos_blackjack.data").joinpath("migrations/0001_init.sql")
                      .read_text(encoding="utf-8"))
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version VALUES (1)")
    raw.commit()
    raw.close()
    conn = connect(path)
    assert schema_version(conn) == 2
    assert load_balance("default", conn).chaos_stub == (("modify_card_value", {"delta": -1}, 1.0),)
    conn.close()


def test_shipped_phase_two_values() -> None:
    b = default_balance()
    assert (b.min_bet, b.max_bet_fraction) == (1, 0.5)
    assert b.chaos_rule_params == {
        "fragile_bust": {"bust_limit": 18}, "great_crash": {"ten_value": 1},
        "odd_even_chaos": {"even_delta": 2, "odd_delta": -1}, "suit_power": {"red_delta": 1, "black_delta": -1},
    }
    assert b.disabled_rules == () and b.item_params == {"fate_oracle": {"cards": 3}}


def test_bet_limits_come_from_the_profile(db) -> None:
    from chaos_blackjack.app.economy import bet_limits

    assert bet_limits(100, max_fraction=0.29) == (1, 29)  # exact, no float rounding
    _profile(db, "tight")
    _set(db, "tight", "bet.min", "5")
    _set(db, "tight", "bet.max_fraction", "0.25")
    v = GameController(RunConfig.from_balance(load_balance("tight", db))).view()
    assert (v.bet_min, v.bet_max) == (5, 25)
    s = AgentSession.new(seed=1, profile="tight")
    assert s.observe()["bet_range"] == [5, 25]


def test_rule_params_override_the_ai(db) -> None:
    pid = _profile(db, "crash5")
    _only_stub(db, pid, "great_crash")
    _rule(db, pid, "great_crash", params='{"ten_value": 5}')
    c = _chaos_ctrl(load_balance("crash5", db))
    c.place_bet(5)
    c.resolve_chaos()
    mod = c.loop.modifiers.items[0]
    assert mod.id == "great_crash" and mod.ten_value == 5


def test_fragile_bust_limit_is_tunable() -> None:
    from chaos_blackjack.registry import get_registry
    from chaos_blackjack.rules.modifiers import ActiveModifiers
    from chaos_blackjack.rules.rule_engine import DefaultBlackjackRules, RuleContext

    mod = get_registry().build_chaos_rule("fragile_bust", {"bust_limit": 19})
    ctx = RuleContext(ActiveModifiers((mod,)))
    rules = DefaultBlackjackRules()
    assert not rules.is_bust(19, ctx) and rules.is_bust(20, ctx)


def test_disabled_rules_are_refused(db) -> None:
    from chaos_blackjack.ai.pipeline import StubLLM
    from chaos_blackjack.app.notices import NoticeKind

    pid = _profile(db, "nocrash")
    _only_stub(db, pid, "great_crash")
    _rule(db, pid, "great_crash", enabled=0)
    b = load_balance("nocrash", db)
    assert b.disabled_rules == ("great_crash",) and b.chaos_stub == ()  # never picked offline
    c = _chaos_ctrl(b)
    # A real model may still ask for it: the pipeline refuses.
    c.loop.pipeline.llm = StubLLM('{"action":"apply_rule","rule_id":"great_crash","params":{}}')
    c.place_bet(5)
    c.resolve_chaos()
    assert c.loop.modifiers.items == ()
    rejected = [n for n in c.drain_notices() if n.kind == NoticeKind.CHAOS_ACTION_REJECTED]
    assert rejected and rejected[0].data["reason"] == "rule_disabled"


def test_offline_stub_draws_by_weight_and_replays(db) -> None:
    pid = _profile(db, "mixed")
    with db:
        db.execute("UPDATE chaos_rule SET stub_weight = 1 WHERE profile_id = ? AND rule_id IN "
                   "('great_crash', 'suit_power', 'reverse_bust')", (pid,))
    b = load_balance("mixed", db)

    def picks(seed: int) -> list[str]:
        c = _chaos_ctrl(b, seed)
        out = []
        for _ in range(12):
            c.place_bet(2)
            if c.phase.value == "chaos":
                c.resolve_chaos()
            out.append(c.loop.modifiers.items[0].id if c.loop.modifiers.items else "-")
            if c.phase.value == "player_turn":
                c.stand()
            c.finish_dealer()
            if c.phase.value == "round_over":
                c.next_round()
        return out

    first = picks(11)
    assert first == picks(11)
    assert len(set(first) - {"-"}) >= 3


def test_offline_stub_without_weights_does_nothing(db) -> None:
    pid = _profile(db, "calm")
    with db:
        db.execute("UPDATE chaos_rule SET stub_weight = 0 WHERE profile_id = ?", (pid,))
    c = _chaos_ctrl(load_balance("calm", db))
    c.place_bet(5)
    c.resolve_chaos()
    assert c.loop.modifiers.items == ()


def test_item_params_reach_the_item(db) -> None:
    pid = _profile(db, "oracle2")
    with db:
        db.execute("UPDATE shop_item SET params = '{\"cards\": 2}' WHERE profile_id = ? AND item_id = 'fate_oracle'",
                   (pid,))
    c = GameController(RunConfig.from_balance(load_balance("oracle2", db), seed=3))
    c.run.items = ("fate_oracle",)
    c.place_bet(5)
    if c.phase.value != "player_turn":
        pytest.skip("seed dealt a natural")
    assert c.use_item("fate_oracle").message.startswith("Top 2 cards")


def test_bad_params_are_rejected(db) -> None:
    pid = _profile(db, "badjson")
    _rule(db, pid, "great_crash", params="{ten_value: 5}")
    with pytest.raises(BalanceError, match="not valid JSON"):
        load_balance("badjson", db)
    _rule(db, pid, "great_crash", params="[5]")
    with pytest.raises(BalanceError, match="JSON object"):
        load_balance("badjson", db)


def test_rule_params_survive_save_and_agent_reload(db) -> None:
    pid = _profile(db, "crash7")
    _only_stub(db, pid, "great_crash")
    _rule(db, pid, "great_crash", params='{"ten_value": 7}')
    s = AgentSession.new(seed=4, chaos=True, profile="crash7")
    s.execute({"cmd": "bet", "amount": 5})
    if s.controller.phase.value != "player_turn":
        pytest.skip("seed dealt a natural")
    again = AgentSession.from_state(s.to_state())
    mod = again.controller.loop.modifiers.items[0]
    assert mod.id == "great_crash" and mod.ten_value == 7
    assert again.controller.config.chaos_stub == (("great_crash", {}, 1.0),)


def test_rule_descriptions_show_tuned_numbers() -> None:
    from chaos_blackjack.registry import get_registry
    from chaos_blackjack.ui.descriptions import describe_modifier

    reg = get_registry()
    assert "value 5" in describe_modifier(reg.build_chaos_rule("great_crash", {"ten_value": 5}))
    assert "reduced to 19" in describe_modifier(reg.build_chaos_rule("fragile_bust", {"bust_limit": 19}))
    assert "+3, odd ranks -2" in describe_modifier(
        reg.build_chaos_rule("odd_even_chaos", {"even_delta": 3, "odd_delta": -2}))
    assert "red suits +2, black suits +0" in describe_modifier(
        reg.build_chaos_rule("suit_power", {"red_delta": 2, "black_delta": 0}))
    assert "value 1" in describe_modifier(reg.build_chaos_rule("great_crash", {}))


def test_public_bet_helpers_follow_the_profile() -> None:
    c = GameController(RunConfig(min_bet=5, max_bet_fraction=0.25, start_money=40))
    assert c.bet_limits() == (5, 10) and c.bet_limits(100) == (5, 25)
    assert c.can_bet() and c.can_bet(20) and not c.can_bet(19)
