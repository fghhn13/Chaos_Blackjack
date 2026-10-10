"""Scenes and the scene stack.

A scene is one screen (menu, table, gallery, a modal dialog...). Scenes are
registered by name with `@register_scene("name")` and opened by name, so
scenes never import each other:

    self.app.scenes.push("gallery")
    self.app.scenes.replace("table", enable_chaos=True)

Stack changes are queued and applied between frames, so it is safe to call
them from inside event handlers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    from chaos_blackjack.gui.app import App


class Scene:
    # True for overlays / dialogs: the scene below is drawn first.
    transparent = False

    def __init__(self, app: "App") -> None:
        self.app = app

    def on_enter(self, **params: Any) -> None:
        """Called once when the scene is pushed / replaced in."""

    def on_exit(self) -> None:
        """Called when the scene leaves the stack."""

    def on_resume(self, result: Any = None) -> None:
        """Called when the scene above was popped. `result` is what it returned."""

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


SceneFactory = Callable[["App"], Scene]
SCENES: dict[str, SceneFactory] = {}


def register_scene(name: str) -> Callable[[type[Scene]], type[Scene]]:
    def deco(cls: type[Scene]) -> type[Scene]:
        SCENES[name] = cls
        return cls

    return deco


class SceneManager:
    def __init__(self, app: "App", registry: dict[str, SceneFactory] | None = None) -> None:
        self.app = app
        self.registry = SCENES if registry is None else registry
        self.stack: list[Scene] = []
        self._pending: list[tuple[str, Any, Any]] = []

    @property
    def top(self) -> Scene | None:
        return self.stack[-1] if self.stack else None

    # Queued operations ---------------------------------------------------
    def push(self, name: str, **params: Any) -> None:
        self._pending.append(("push", name, params))

    def replace(self, name: str, **params: Any) -> None:
        self._pending.append(("replace", name, params))

    def pop(self, result: Any = None) -> None:
        self._pending.append(("pop", None, result))

    def reset(self, name: str, **params: Any) -> None:
        """Clear the whole stack and open `name` (e.g. back to main menu)."""
        self._pending.append(("reset", name, params))

    def apply_pending(self) -> None:
        while self._pending:
            op, name, arg = self._pending.pop(0)
            if op == "push":
                self._open(name, arg)
            elif op == "replace":
                if self.stack:
                    self.stack.pop().on_exit()
                self._open(name, arg)
            elif op == "reset":
                while self.stack:
                    self.stack.pop().on_exit()
                self._open(name, arg)
            elif op == "pop" and self.stack:
                self.stack.pop().on_exit()
                if self.stack:
                    self.stack[-1].on_resume(arg)

    def _open(self, name: str, params: dict[str, Any]) -> None:
        factory = self.registry.get(name)
        if factory is None:
            raise KeyError(f"Unknown scene: {name!r} (registered: {sorted(self.registry)})")
        scene = factory(self.app)
        self.stack.append(scene)
        scene.on_enter(**params)

    # Frame -----------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.top is not None:
            self.top.handle_event(event)

    def update(self, dt: float) -> None:
        if self.top is not None:
            self.top.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        start = len(self.stack) - 1
        while start > 0 and self.stack[start].transparent:
            start -= 1
        for scene in self.stack[max(0, start):]:
            scene.draw(surface)
