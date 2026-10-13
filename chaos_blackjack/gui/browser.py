"""Browser bridge for account-scoped SQLite snapshots and frame diagnostics."""
import json
import sqlite3
import time
from contextlib import closing

from chaos_blackjack.data.db import db_path


class BrowserStore:
    def __init__(self, window):
        self.window = window
        reader = getattr(window, "chaosReadSave", None)
        self.previous = json.loads(str(reader())) if reader else str(window.chaosInitialSave or "")
        self.next_save = 0.0
        self.name_scene = None
        self.name_sequence = 0
        self.name_ack = 0
        self.name_state = "null"
        if self.previous:
            with closing(sqlite3.connect(db_path())) as conn:
                conn.executescript(self.previous)

    def snapshot(self):
        with closing(sqlite3.connect(db_path())) as conn:
            return "\n".join(conn.iterdump())

    def frame(self, app):
        top = app.scenes.top
        self.name_input(top)
        # Visible state only: useful for diagnosing startup without inspecting a deck.
        state = {"scene": type(top).__name__, "running": app.running}
        for name in ("scroll", "text_offset", "detail_scroll"):
            value = getattr(top, name, None)
            if isinstance(value, (int, float)):
                state[name] = value
        # Positions and offsets are visible UI state, not hidden game data.
        from chaos_blackjack.gui.widgets import ScrollColumn
        state["scroll_regions"] = [
            {"rect": list(widget.rect), "offset": widget.scroll, "max": widget.max_scroll}
            for widget in getattr(getattr(top, "ui", None), "widgets", ())
            if isinstance(widget, ScrollColumn)]
        if type(top).__name__ == "RunPanelScene":
            state["tab"] = top.tab.id
            state["scroll_regions"].append({"rect": list(top.content), "offset": top.scroll,
                                             "max": max(0, top.view.measure() - top.content.h)})
        elif type(top).__name__ == "ShopScene" and top.grid:
            state["scroll_regions"].append({"rect": list(top.area), "offset": top.scroll,
                                             "max": max(0, top.content_h - top.area.h)})
        elif type(top).__name__ == "ChoiceScene" and top.choice is not None:
            state["scroll_regions"].append({"rect": list(top.area), "offset": top.scroll, "max": top.max_scroll})
        if type(top).__name__ == "NameDialog":
            state.update(text=top.value, message=top.message)
        from chaos_blackjack.app.view import GameView
        view = getattr(top, "view", None)
        if not isinstance(view, GameView):
            controller = getattr(top, "controller", None)
            view = controller.view() if controller is not None else None
        if isinstance(view, GameView):
            state.update(phase=view.phase.value, money=view.money, round=view.round)
        self.window.chaosState = json.dumps(state)
        if time.monotonic() >= self.next_save:
            self.next_save = time.monotonic() + 1
            self.flush()

    def name_input(self, scene):
        """Route touch-device HTML editing through the original name dialog."""
        if not getattr(self.window, "chaosTouchInput", False):
            return
        from chaos_blackjack.meta.models import MAX_NAME_LENGTH

        active = type(scene).__name__ == "NameDialog" and not scene.submitted
        state = "null"
        if active:
            if scene is not self.name_scene:
                self.name_scene = scene
                self.name_sequence += 1
                self.name_ack = 0
            request_id = f"{self.window.chaosInputId}:{self.name_sequence}"
            raw = str(self.window.chaosNameNext() or "")
            try:
                command = json.loads(raw) if raw else {}
            except (ValueError, TypeError):
                command = {}
            if (isinstance(command, dict) and command.get("id") == request_id
                    and type(command.get("seq")) is int and command["seq"] > self.name_ack
                    and command.get("action") in ("input", "submit", "cancel")
                    and isinstance(command.get("value"), str)):
                self.name_ack = command["seq"]
                scene.value = command["value"][:MAX_NAME_LENGTH]
                scene.replace_value = False
                scene.message = ""
                if command["action"] == "submit":
                    scene.submit()
                elif command["action"] == "cancel":
                    scene.app.scenes.pop()
                    active = False
            if active and not scene.submitted:
                state = json.dumps({"id": request_id, "ack": self.name_ack,
                                    "title": scene.title, "value": scene.value,
                                    "message": scene.message, "maxLength": MAX_NAME_LENGTH})
        else:
            self.name_scene = None
        if state != self.name_state:
            self.window.chaosNameInput(state)
            self.name_state = state

    def flush(self):
        snapshot = self.snapshot()
        if snapshot != self.previous:
            sender = getattr(self.window, "chaosSaveJSON", None)
            if sender:
                sender(json.dumps(snapshot))
            else:
                self.window.chaosSave(snapshot)
            self.previous = snapshot
