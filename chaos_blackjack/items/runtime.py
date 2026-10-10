"""One item executor for player commands and Chaos AI actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.core.game_state import GameState
from chaos_blackjack.events.event import Event
from chaos_blackjack.registry.registry import Registry


def _swap_top_into_first_player_card(state: GameState, _value: Any) -> GameState:
    if not state.player_hand or not state.deck:
        return state
    top, *rest = state.deck
    return state.with_player_hand((top,) + state.player_hand[1:]).with_deck(tuple(rest))


# Compatibility for existing ItemResult.extra effects. New packs use effects.
ITEM_EFFECTS = {"swap_top_into_first_player_card": _swap_top_into_first_player_card}


def apply_item_effects(state: GameState, result: ItemResult) -> GameState:
    after = state
    for key, value in (result.extra or {}).items():
        effect = ITEM_EFFECTS.get(key)
        if effect is not None and value:
            after = effect(after, value)
    for effect in result.effects:
        after = effect.apply(after)
        if not isinstance(after, GameState):
            raise ValueError("Item effects must return GameState")
    return after


def execute_item(
    registry: Registry,
    state: GameState,
    item_id: str,
    *,
    emit: Callable[[Event], None],
    peek_next_card_rank: Callable[[], str | None],
) -> tuple[GameState, ItemResult]:
    cls = registry.resolve_item(item_id)
    if cls is None:
        return state, ItemResult(ok=False, message=f"Unknown item: {item_id}")
    if item_id not in state.inventory:
        return state, ItemResult(ok=False, message="You don't have that item.")
    # Publish item events only after the item and its effects succeed.
    pending: list[Event] = []
    ctx = ItemContext(state, pending.append, peek_next_card_rank)
    result = cls().use(ctx)
    if not result.ok:
        return state, result
    after = apply_item_effects(state, result)
    inventory = list(after.inventory)
    if item_id in inventory:
        inventory.remove(item_id)
    after = after.with_inventory(tuple(inventory))
    for event in pending:
        emit(event)
    return after, result
