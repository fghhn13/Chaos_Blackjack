"""Run saves and preferences in SQLite (data/game.db)."""

from __future__ import annotations

import json

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.data import (
    SaveNotFound, clone_profile, connect, delete_run, get_pref, import_json_saves, list_runs, load_balance,
    load_run, save_run, set_pref,
)
from chaos_blackjack.data.__main__ import main as data_cli


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "game.db"
    monkeypatch.setenv("CHAOS_DB", str(path))
    return path


def _saved(c: GameController, name: str = "slot"):
    c.save(name)
    return load_run(name)


def test_controller_saves_into_the_database(db) -> None:
    c = GameController(RunConfig(seed=2))
    c.place_bet(10)
    c.save("my run.json")
    path = [n for n in c.drain_notices() if n.kind == NoticeKind.GAME_SAVED][0].data["path"]
    assert path.endswith("#my run") and str(db) in path
    data = load_run("my run")
    assert data.round == 1 and data.game_state is not None
    assert data.config["balance_profile"] == "default"
    (info,) = list_runs()
    assert (info.name, info.profile, info.round, info.money) == ("my run", "default", 1, 100)


def test_overwrite_delete_and_missing(db) -> None:
    c = GameController(RunConfig(seed=2))
    save_run(_saved(c), "a")
    c.run.money = 77
    c.save("a")
    assert load_run("a.json").money == 77 and [s.name for s in list_runs()] == ["a", "slot"]
    assert delete_run("a") and not delete_run("a")
    with pytest.raises(SaveNotFound):
        load_run("a")


def test_a_save_keeps_its_numbers_after_the_profile_changes(db) -> None:
    conn = connect(db)
    clone_profile(conn, "default", "tight")
    with conn:
        conn.execute("UPDATE setting SET value = '0.25' WHERE key = 'bet.max_fraction' AND profile_id = "
                     "(SELECT id FROM balance_profile WHERE name = 'tight')")
    c = GameController(RunConfig.from_balance(load_balance("tight", conn), seed=4))
    data = _saved(c)
    with conn:
        conn.execute("UPDATE setting SET value = '0.5' WHERE key = 'bet.max_fraction'")
    conn.close()
    loaded = GameController.from_save(data, RunConfig())
    assert loaded.view().bet_max == 25 and loaded.config.balance_profile == "tight"
    row = connect(db).execute("SELECT profile_name, balance_hash FROM run_save").fetchone()
    assert row[0] == "tight" and row[1] == c.config.balance_hash != RunConfig().balance_hash


def test_loading_can_switch_chaos_on(db) -> None:
    data = _saved(GameController(RunConfig(seed=4)))
    assert GameController.from_save(data, RunConfig(enable_chaos=True)).config.enable_chaos


def test_sqlite_save_restores_profile_and_memory_after_settings_change(db) -> None:
    from chaos_blackjack.contracts.chaos_interaction import PokeReply

    conn = connect(db)
    try:
        pid = clone_profile(conn, "default", "memory-tight")
        with conn:
            for key, value in (("bet.min", "5"), ("bet.max_fraction", "0.25"),
                               ("run.start_money", "40"), ("chaos.guidance_probability", "0.75"),
                               ("chaos.memory_enabled", "1"), ("chaos.memory_limit", "2")):
                conn.execute("UPDATE setting SET value = ? WHERE profile_id = ? AND key = ?", (value, pid, key))
        cfg = RunConfig.from_balance(load_balance("memory-tight", conn), seed=3, enable_chaos=True,
                                     shop_prices={"peek": 10})
        c = GameController(cfg)
        c.buy("peek")
        assert c.accept_poke_reply(c.prepare_poke(), PokeReply("Save your peek for the next hand."))
        data = _saved(c, "memory-run")
        with conn:
            conn.execute("UPDATE setting SET value = '0' WHERE profile_id = ? AND key = 'chaos.memory_enabled'", (pid,))
        loaded = GameController.from_save(data, RunConfig.from_balance(load_balance("memory-tight", conn)))
        assert loaded.config == cfg and loaded.bet_limits() == (5, 7)
        assert loaded.chaos_memory.export() == c.chaos_memory.export()
        assert len(loaded.chaos_memory.export()) == 2
    finally:
        conn.close()


def test_old_saves_without_config_use_the_given_config(db) -> None:
    data = _saved(GameController(RunConfig(seed=4)))
    payload = data.to_dict()
    payload.pop("config")
    save_run(type(data).from_dict(payload), "old")
    loaded = GameController.from_save(load_run("old"), RunConfig(min_bet=3))
    assert loaded.view().bet_min == 3


def test_import_json_saves(db, tmp_path) -> None:
    folder = tmp_path / "legacy"
    folder.mkdir()
    good = _saved(GameController(RunConfig(seed=4))).to_dict()
    good.pop("config")
    (folder / "first.json").write_text(json.dumps(good), encoding="utf-8")
    (folder / "broken.json").write_text("[1, 2]", encoding="utf-8")
    result = import_json_saves(folder)
    assert result["first"] == "imported" and result["broken"].startswith("error")
    assert load_run("first").money == 100
    assert import_json_saves(folder)["first"] == "skipped (exists)"
    assert import_json_saves(folder, overwrite=True)["first"] == "imported"
    assert import_json_saves(tmp_path / "missing") == {}


def test_data_cli(db, tmp_path, capsys) -> None:
    folder = tmp_path / "legacy"
    folder.mkdir()
    payload = _saved(GameController(RunConfig(seed=4))).to_dict()
    (folder / "cli.json").write_text(json.dumps(payload), encoding="utf-8")
    assert data_cli(["import-saves", str(folder)]) == 0
    assert data_cli(["saves"]) == 0
    out = capsys.readouterr().out
    assert "cli: imported" in out and "cli " in out


def test_preferences_round_trip(db) -> None:
    assert get_pref("gui.enable_chaos", False) is False
    set_pref("gui.enable_chaos", True)
    set_pref("gui.volume", {"master": 0.5})
    assert get_pref("gui.enable_chaos") is True and get_pref("gui.volume") == {"master": 0.5}


def test_preferences_fall_back_when_the_database_is_unusable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAOS_DB", str(tmp_path))  # a folder, not a database file
    assert get_pref("gui.enable_chaos", "fallback") == "fallback"


def test_gui_preferences_persist(db) -> None:
    pytest.importorskip("pygame")
    from chaos_blackjack.gui.app import Preferences

    assert Preferences.load().enable_chaos is False
    Preferences(enable_chaos=True).save()
    assert Preferences.load().enable_chaos is True
