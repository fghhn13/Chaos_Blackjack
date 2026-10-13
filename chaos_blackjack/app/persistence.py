"""Live objects <-> JSON-ready save snapshots."""

from __future__ import annotations

from chaos_blackjack.app.economy import RunState
from chaos_blackjack.app.shop import ShopState
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.core.run_state import (
    CardSnapshot,
    GameStateSnapshot,
    ModifierSnapshot,
    RunSaveData,
)
from chaos_blackjack.rules.modifiers import ActiveModifiers


def card_to_snapshot(card: Card) -> CardSnapshot:
    return CardSnapshot(rank=str(card.rank), suit=str(card.suit or ""))


def snapshot_to_card(s: CardSnapshot) -> Card:
    return Card(Rank(s.rank), s.suit)


def game_state_to_snapshot(state: GameState) -> GameStateSnapshot:
    return GameStateSnapshot(
        player_hand=[card_to_snapshot(c) for c in state.player_hand],
        dealer_hand=[card_to_snapshot(c) for c in state.dealer_hand],
        deck=[card_to_snapshot(c) for c in state.deck],
        phase=state.phase.name,
        chaos_budget_remaining=int(state.chaos_budget_remaining),
        inventory=list(state.inventory),
    )


def snapshot_to_game_state(s: GameStateSnapshot) -> GameState:
    return GameState(
        player_hand=tuple(snapshot_to_card(c) for c in s.player_hand),
        dealer_hand=tuple(snapshot_to_card(c) for c in s.dealer_hand),
        deck=tuple(snapshot_to_card(c) for c in s.deck),
        phase=GamePhase[s.phase],
        chaos_budget_remaining=int(s.chaos_budget_remaining),
        inventory=tuple(s.inventory),
    )


def serialize_modifier_params(mod: object) -> dict[str, object]:
    # Generic heuristics for current modifier plugins.
    params: dict[str, object] = {}
    if hasattr(mod, "delta"):
        try:
            params["delta"] = int(getattr(mod, "delta"))
        except Exception:
            pass

    for key in ("count", "rank"):  # J-54 deck rules
        value = getattr(mod, key, None)
        if value is not None:
            params[key] = value

    mid = getattr(mod, "id", None)
    if mid == "tiebreaker_shift" and hasattr(mod, "chaos_flags"):
        flags = getattr(mod, "chaos_flags") or frozenset()
        ties_to = "dealer" if "dealer_wins_ties" in flags else "player"
        params["ties_to"] = ties_to

    return params


def serialize_active_modifiers(loop: GameLoop) -> list[ModifierSnapshot]:
    out: list[ModifierSnapshot] = []
    for m in loop.modifiers.items:
        mid = getattr(m, "id", None)
        if not mid:
            continue
        params = serialize_modifier_params(m)
        out.append(ModifierSnapshot(id=str(mid), params=params))
    return out


def deserialize_active_modifiers(
    mods: list[ModifierSnapshot],
    *,
    registry,
    rule_params: dict[str, dict] | None = None,
) -> ActiveModifiers:
    """`rule_params` are the balance profile's fixed params per rule."""
    built: list[object] = []
    for m in mods:
        inst = registry.build_chaos_rule(m.id, {**m.params, **(rule_params or {}).get(m.id, {})})
        if inst is None:
            raise ValueError(f"Unknown chaos rule id in save: {m.id}")
        built.append(inst)
    return ActiveModifiers(items=tuple(built))


def build_save_data(
    *,
    run: RunState,
    state: GameState | None,
    loop: GameLoop,
    enable_chaos: bool,
    shop: ShopState | None = None,
    shop_seed: int | None = None,
    hole_revealed: bool = False,
    chaos_memory: list[dict] | None = None,
    config: dict | None = None,
    table: dict | None = None,
) -> RunSaveData:
    """`state=None` saves between rounds (resume starts at the bet prompt)."""
    active = serialize_active_modifiers(loop) if state is not None else []
    chaos_actions_this_turn = int(getattr(loop, "_chaos_actions_this_turn", 0))

    return RunSaveData(
        version=1,
        money=run.money,
        start_money=run.start_money,
        round=run.round,
        items=list(state.inventory) if state is not None else list(run.items),
        objective=run.objective,
        win_streak=run.win_streak,
        target_money=run.target_money,
        current_bet=run.current_bet,
        enable_chaos=bool(enable_chaos),
        game_state=game_state_to_snapshot(state) if state is not None else None,
        active_modifiers=active,
        chaos_actions_this_turn=chaos_actions_this_turn,
        shop=shop.to_dict() if shop is not None else None,
        shop_seed=shop_seed,
        hole_revealed=bool(hole_revealed and state is not None),
        chaos_memory=chaos_memory,
        config=config,
        table=table,
    )
