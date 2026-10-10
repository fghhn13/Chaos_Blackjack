"""Offline contract checks and a sample turn; no model relay is constructed."""

from __future__ import annotations

from pathlib import Path

from chaos_blackjack.content.loader import PACK_ROOT, load_content_packs
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.items.runtime import execute_item
from chaos_blackjack.rules.modifiers import ActiveModifiers


def validate_packs(pack_ids: tuple[str, ...], *, root: Path = PACK_ROOT) -> dict:
    catalog = load_content_packs(pack_ids, root=root)
    registry = catalog.registry
    state = GameState(
        player_hand=tuple(Card(Rank(r)) for r in ("5", "6", "4")),
        dealer_hand=(Card(Rank("9")), Card(Rank("7"))),
        deck=(Card(Rank("2")), Card(Rank("K"))),
        phase=GamePhase.PLAYER_TURN, chaos_budget_remaining=5,
        inventory=registry.item_ids(),
    )
    checked_items: list[str] = []
    for item_id in registry.item_ids():
        after, result = execute_item(registry, state, item_id,
                                     emit=lambda event: None, peek_next_card_rank=lambda: "2")
        if not result.ok:
            if after != state:
                raise ValueError(f"Item {item_id} mutated state on failure")
        elif after.inventory.count(item_id) != state.inventory.count(item_id) - 1:
            raise ValueError(f"Item {item_id} must consume exactly one copy")
        checked_items.append(item_id)
    checked_ais: list[str] = []
    for ai_id in registry.ai_ids():
        if ai_id == "default":
            continue
        pipeline = registry.resolve_ai(ai_id).build(registry)
        events = []
        pipeline.run(ChaosObservation(state, ActiveModifiers(), 5, 0),
                     emit=events.append, peek_next_card_rank=lambda: "2")
        if any(event.type.name == "CHAOS_ACTION_REJECTED" for event in events):
            raise ValueError(f"AI {ai_id}: sample offline action was rejected")
        checked_ais.append(ai_id)
    return {"ok": True, "packs": list(pack_ids), "items": checked_items,
            "ais": checked_ais, "default_ai": catalog.default_ai,
            "starting_items": list(catalog.starting_items), "shop_items": list(catalog.shop_items)}
