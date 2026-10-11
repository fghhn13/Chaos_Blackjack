"""Real SQLite restore and the asynchronous native scene lifecycle."""
import asyncio
from types import SimpleNamespace

import pytest

from chaos_blackjack.data.db import connect
from chaos_blackjack.gui.browser import BrowserStore


def test_browser_store_restores_and_tracks_account_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "before.db"))
    db = connect()
    with db:
        db.execute("INSERT INTO preference(key,value) VALUES ('test','42')")
    db.close()
    saved = []
    window = SimpleNamespace(chaosInitialSave="", chaosSave=saved.append)
    store = BrowserStore(window)
    store.flush()
    store.flush()
    assert len(saved) == 1
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "restored.db"))
    BrowserStore(SimpleNamespace(chaosInitialSave=saved[0]))
    db = connect()
    assert db.execute("SELECT value FROM preference WHERE key='test'").fetchone()[0] == "42"
    db.close()


def test_browser_worker_completes_without_threads(monkeypatch):
    from chaos_blackjack.gui import worker
    monkeypatch.setattr(worker.sys, "platform", "emscripten")
    monkeypatch.setattr(worker, "Thread", lambda **kwargs: pytest.fail("WASM cannot create threads"))
    result = []
    worker.start_worker(result.append, ("done",), name="offline")
    assert result == ["done"]


def test_async_loop_renders_existing_home_and_yields(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pytest.importorskip("pygame")
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings, PROJECT_ROOT
    app = App(GuiSettings(asset_dirs=(PROJECT_ROOT / "assets",)))
    scenes = []
    asyncio.run(app.run_async(max_frames=3, on_frame=lambda a: scenes.append(type(a.scenes.top).__name__)))
    assert scenes == ["HomeScene"] * 3
