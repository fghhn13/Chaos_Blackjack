"""Central event dispatch — handlers stay pluggable."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from chaos_blackjack.events.event import Event, EventType


class EventDispatcher:
    """Registers per-event handlers; unknown types are ignored or delegated to default."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, Callable[[Event], Any]] = {}
        self._default: Callable[[Event], Any] | None = None

    def register(
        self,
        event_type: EventType,
        handler: Callable[[Event], Any],
    ) -> None:
        self._handlers[event_type] = handler

    def set_default(self, handler: Callable[[Event], Any] | None) -> None:
        self._default = handler

    def dispatch(self, event: Event) -> Any:
        handler = self._handlers.get(event.type, self._default)
        if handler is None:
            return None
        return handler(event)

    def dispatch_many(self, events: tuple[Event, ...]) -> list[Any]:
        return [self.dispatch(e) for e in events]
