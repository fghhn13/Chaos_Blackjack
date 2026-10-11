"""Browser bridge for account-scoped SQLite snapshots and frame diagnostics."""
import json
import sqlite3
import time
from contextlib import closing

from chaos_blackjack.data.db import db_path


class BrowserStore:
    def __init__(self, window):
        self.window = window
        self.previous = str(window.chaosInitialSave or "")
        self.next_save = 0.0
        if self.previous:
            with closing(sqlite3.connect(db_path())) as conn:
                conn.executescript(self.previous)

    def snapshot(self):
        with closing(sqlite3.connect(db_path())) as conn:
            return "\n".join(conn.iterdump())

    def frame(self, app):
        top = app.scenes.top
        # Visible state only: useful for diagnosing startup without inspecting a deck.
        state = {"scene": type(top).__name__, "running": app.running}
        if type(top).__name__ == "NameDialog":
            state.update(text=top.value, message=top.message)
        view = getattr(top, "view", None)
        if view is not None:
            state.update(phase=view.phase.value, money=view.money, round=view.round)
        self.window.chaosState = json.dumps(state)
        if time.monotonic() >= self.next_save:
            self.next_save = time.monotonic() + 1
            self.flush()

    def flush(self):
        snapshot = self.snapshot()
        if snapshot != self.previous:
            self.window.chaosSave(snapshot)
            self.previous = snapshot
