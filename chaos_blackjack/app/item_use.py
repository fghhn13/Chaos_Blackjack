"""Resolve a player item use against GameState (no I/O)."""

from __future__ import annotations

from typing import Any

from chaos_blackjack.contracts.items import ItemResult
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import GameState
from chaos_blackjack.registry import get_registry
from chaos_blackjack.items.runtime import ITEM_EFFECTS, apply_item_effects, execute_item


def inventory_counts(inventory: tuple[str, ...]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for x in inventory:
        counts[x] = counts.get(x, 0) + 1
    return sorted(counts.items())


def remove_one(inv: tuple[str, ...], item_id: str) -> tuple[str, ...]:
    lst = list(inv)
    if item_id in lst:
        lst.remove(item_id)
    return tuple(lst)


def use_item(loop: GameLoop, state: GameState, item_id: str,
             params: dict[str, Any] | None = None) -> tuple[GameState, ItemResult]:
    after, result = execute_item(
        loop.pipeline.registry or get_registry(), state, item_id,
        emit=loop.emit_event,
        peek_next_card_rank=lambda: state.deck[0].rank if state.deck else None,
        active_rule_ids=tuple(str(m.id) for m in loop.modifiers.items), params=params,
    )
    if result.ok and (result.extra or {}).get("dispel_chaos_rules"):
        loop.modifiers = loop.modifiers.with_cleared()
    return after, result
