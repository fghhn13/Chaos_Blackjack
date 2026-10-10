"""Item plugins — use() never mutates state; returns events / messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

from chaos_blackjack.core.game_state import GameState


@dataclass(frozen=True)
class ItemResult:
    ok: bool
    message: str = ""
    extra: dict[str, Any] | None = None


class ItemContext:
    """Narrow API for items — no raw mutable deck references."""

    def __init__(
        self,
        state: GameState,
        emit_event: Callable[..., None],
        peek_next_card_rank: Callable[[], str | None],
        active_rule_ids: tuple[str, ...] = (),
    ) -> None:
        self.state = state
        self.emit_event = emit_event
        self.peek_next_card_rank = peek_next_card_rank
        self.active_rule_ids = active_rule_ids  # chaos rules in force this round


@runtime_checkable
class ItemProtocol(Protocol):
    name: str

    def use(self, ctx: ItemContext) -> ItemResult:
        ...
