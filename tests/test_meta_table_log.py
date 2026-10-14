"""Table logs: a player's run writes its table notices to data/table_logs/run-<id>.jsonl beside the database."""

import json

from chaos_blackjack.data.db import MEMORY, connect
from chaos_blackjack.meta.service import MetaService


def _lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_a_run_in_a_database_file_writes_its_table_log(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "game.db"))
    svc = MetaService()
    player = svc.create_player(1, "Dev")
    run = svc.start_run(player.id, "chaos", seed=5)
    c = run.controller
    c.choose(c.choice.options[0].id)
    c.place_bet(c.view().bet_min)
    path = tmp_path / "table_logs" / f"run-{run.run_id}.jsonl"
    lines = _lines(path)
    assert lines[0]["event"] == "attached" and lines[0]["mode"] == "chaos"
    kinds = {x.get("kind") for x in lines}
    assert "round_started" in kinds and all("round" in x and "money" in x for x in lines)
    assert all("net_assets" in x for x in lines[1:])

    svc.abandon_run(run.run_id)
    size = path.stat().st_size
    c.drain_notices()
    assert path.stat().st_size == size  # detached: nothing more is written


def test_in_memory_services_write_no_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc = MetaService(connect(MEMORY))
    player = svc.create_player(1, "Dev")
    run = svc.start_run(player.id, "normal", seed=5)
    run.controller.place_bet(10)
    assert not any(tmp_path.rglob("*.jsonl"))
