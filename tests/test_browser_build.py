"""Browser packaging and startup errors must be checked outside the checkout."""
import runpy
import importlib.util
import platform
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "blackjack_browser_builder", Path(__file__).resolve().parents[1] / "scripts/build_browser.py")
build_browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_browser)


def test_new_database_resources_are_packaged_without_manual_manifest_update(tmp_path, monkeypatch):
    (tmp_path / "browser").mkdir()
    (tmp_path / "browser/package-files.txt").write_text("assets/card.png\n")
    for name in ("migrations/0001_init.sql", "migrations/0006_new_feature.sql", "seed/default.sql"):
        target = tmp_path / "chaos_blackjack/data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("-- shipped database resource\n")
    (tmp_path / "chaos_blackjack/data/local.db").write_text("private database")
    (tmp_path / ".env").write_text("private configuration")
    monkeypatch.setattr(build_browser, "ROOT", tmp_path)
    selected = build_browser.package_files()
    assert "chaos_blackjack/data/migrations/0006_new_feature.sql" in selected
    assert "chaos_blackjack/data/seed/default.sql" in selected
    assert "assets/card.png" in selected
    assert not any(name.endswith(".db") or name == ".env" for name in selected)


def test_browser_import_failure_notifies_host_and_closes(monkeypatch):
    events = []
    window = SimpleNamespace(chaosFailed=lambda: events.append("failed"),
                             chaosClosed=lambda: events.append("closed"))
    monkeypatch.setattr(platform, "window", window, raising=False)
    monkeypatch.setitem(sys.modules, "chaos_blackjack.gui.app", None)
    monkeypatch.setattr(sqlite3, "__path__", list(sqlite3.__path__))
    monkeypatch.setenv("CHAOS_DB", ":memory:")
    monkeypatch.setenv("CHAOS_USE_LLM", "0")
    entry = Path(__file__).resolve().parents[1] / "browser/main.py"
    with pytest.raises(ModuleNotFoundError):
        runpy.run_path(str(entry))
    assert events == ["failed", "closed"]
