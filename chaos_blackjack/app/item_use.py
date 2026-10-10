"""Resolve a player item use against GameState (no I/O)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import GameState
from chaos_blackjack.registry import get_registry


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


# Item `extra` flags -> state transform. Add an entry here when a new item
# needs to change the table (items themselves never mutate state). Flags that
# touch the loop (`dispel_chaos_rules`) are handled in `use_item`; flags that
# only change what the player sees (`reveal_hole_card`) in the controller.
ItemEffect = Callable[[GameState, Any], GameState]


def _swap_top_into_first_player_card(state: GameState, _value: Any) -> GameState:
    if not state.player_hand or not state.deck:
        return state
    top, *rest = state.deck
    swapped = (top,) + state.player_hand[1:]
    return state.with_player_hand(swapped).with_deck(tuple(rest))


ITEM_EFFECTS: dict[str, ItemEffect] = {
    "swap_top_into_first_player_card": _swap_top_into_first_player_card,
}


def apply_item_effects(state: GameState, result: ItemResult) -> GameState:
    extra = result.extra if isinstance(result.extra, dict) else {}
    s = state
    for key, value in extra.items():
        effect = ITEM_EFFECTS.get(key)
        if effect is not None and value:
            s = effect(s, value)
    return s


def use_item(
    loop: GameLoop,
    state: GameState,
    item_id: str,
    params: dict[str, Any] | None = None,
) -> tuple[GameState, ItemResult]:
    """Run an item; on success apply its effects and consume one copy.
    `params` is the item's tuning from the balance profile."""
    cls = get_registry().resolve_item(item_id)
    if cls is None:
        return state, ItemResult(ok=False, message=f"Unknown item: {item_id}")
    if item_id not in state.inventory:
        return state, ItemResult(ok=False, message="You don't have that item.")

    ctx = ItemContext(
        state,
        emit_event=loop.emit_event,
        peek_next_card_rank=lambda: state.deck[0].rank if state.deck else None,
        active_rule_ids=tuple(str(getattr(m, "id", "?")) for m in loop.modifiers.items),
        params=params,
    )
    result = cls().use(ctx)
    if not result.ok:
        return state, result
    after = apply_item_effects(state, result)
    if (result.extra or {}).get("dispel_chaos_rules"):
        loop.modifiers = loop.modifiers.with_cleared()
    return after.with_inventory(remove_one(after.inventory, item_id)), result
