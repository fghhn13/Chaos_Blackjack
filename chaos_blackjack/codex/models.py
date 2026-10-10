"""Headless codex contracts shared by providers and front-ends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.notices import Notice
from chaos_blackjack.app.view import GameView


@dataclass(frozen=True)
class DemoStep:
    action: str
    arg: Any = None
    caption: str = ""


@dataclass(frozen=True)
class DemoScript:
    player: tuple[str, ...]
    dealer: tuple[str, ...]
    deck: tuple[str, ...]
    chaos: bool
    steps: tuple[DemoStep, ...]


@dataclass(frozen=True)
class DemoFrame:
    view: GameView
    caption: str
    notices: tuple[Notice, ...]


@dataclass(frozen=True)
class CodexEntry:
    kind: str
    id: str
    name: str
    icon: str
    summary: str
    detail: Callable[[RunConfig], str]
    demo: DemoScript | None
    order: int = 0


@dataclass(frozen=True)
class CodexKind:
    id: str
    label: str
    order: int = 0
