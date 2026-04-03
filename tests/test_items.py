"""Item plugins — validate outputs are correct and registry resolves them."""

from __future__ import annotations

from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.events.event import EventType
from chaos_blackjack.registry.registry import get_registry
from chaos_blackjack.contracts.items import ItemContext
from chaos_blackjack.events.event import Event


def _make_ctx(state: GameState, *, peek_rank: str | None = None) -> ItemContext:
    emitted: list[Event] = []

    def emit_event(e: Event) -> None:
        emitted.append(e)

    def peek_next_card_rank() -> str | None:
        return peek_rank

    ctx = ItemContext(
        state=state,
        emit_event=emit_event,
        peek_next_card_rank=peek_next_card_rank,
    )
    # Attach for assertions.
    ctx._emitted_for_test = emitted  # type: ignore[attr-defined]
    return ctx


def test_hole_card_hacker_reveals_dealer_second_card() -> None:
    reg = get_registry()
    cls = reg.resolve_item("hole_card_hacker")
    assert cls is not None
    item = cls()

    st = GameState(
        player_hand=(Card(Rank("9"), ""),),
        dealer_hand=(Card(Rank("7"), ""), Card(Rank("K"), "")),
        deck=(),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=(),
    )
    ctx = _make_ctx(st)
    res = item.use(ctx)
    assert res.ok is True
    assert "K" in res.message
    emitted = ctx._emitted_for_test  # type: ignore[attr-defined]
    assert any(e.type == EventType.ITEM_USED and e.payload.get("hole_rank") == "K" for e in emitted)


def test_fate_oracle_peeks_top_three_cards() -> None:
    reg = get_registry()
    cls = reg.resolve_item("fate_oracle")
    assert cls is not None
    item = cls()

    st = GameState(
        player_hand=(Card(Rank("9"), ""),),
        dealer_hand=(Card(Rank("7"), ""), Card(Rank("2"), "")),
        deck=(
            Card(Rank("2"), ""),
            Card(Rank("J"), ""),
            Card(Rank("K"), ""),
            Card(Rank("A"), ""),
        ),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=(),
    )
    ctx = _make_ctx(st)
    res = item.use(ctx)
    assert res.ok is True
    emitted = ctx._emitted_for_test  # type: ignore[attr-defined]
    item_events = [e for e in emitted if e.type == EventType.ITEM_USED]
    assert item_events
    payload = item_events[-1].payload
    assert payload.get("peeked_ranks") == ["2", "J", "K"]


def test_danger_radar_counts_high_cards() -> None:
    reg = get_registry()
    cls = reg.resolve_item("danger_radar")
    assert cls is not None
    item = cls()

    st = GameState(
        player_hand=(Card(Rank("9"), ""),),
        dealer_hand=(Card(Rank("7"), ""), Card(Rank("2"), "")),
        deck=(
            Card(Rank("10"), ""),
            Card(Rank("Q"), ""),
            Card(Rank("9"), ""),
            Card(Rank("K"), ""),
        ),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=(),
    )
    ctx = _make_ctx(st)
    res = item.use(ctx)
    assert res.ok is True
    assert "3/4" in res.message

    emitted = ctx._emitted_for_test  # type: ignore[attr-defined]
    item_events = [e for e in emitted if e.type == EventType.ITEM_USED]
    assert item_events
    payload = item_events[-1].payload
    assert payload.get("danger_high_count") == 3
    assert payload.get("danger_total") == 4


def test_shield_item_registered_and_usable() -> None:
    reg = get_registry()
    cls = reg.resolve_item("shield")
    assert cls is not None
    item = cls()
    st = GameState(
        player_hand=(Card(Rank("9"), ""),),
        dealer_hand=(Card(Rank("7"), ""), Card(Rank("2"), "")),
        deck=(Card(Rank("10"), ""),),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=(),
    )
    ctx = _make_ctx(st)
    res = item.use(ctx)
    assert res.ok is True
    assert "Shield" in res.message


def test_swap_item_returns_swap_effect_extra() -> None:
    reg = get_registry()
    cls = reg.resolve_item("swap")
    assert cls is not None
    item = cls()
    st = GameState(
        player_hand=(Card(Rank("9"), ""), Card(Rank("3"), "")),
        dealer_hand=(Card(Rank("7"), ""), Card(Rank("2"), "")),
        deck=(Card(Rank("K"), ""), Card(Rank("10"), "")),
        phase=GamePhase.PLAYER_TURN,
        chaos_budget_remaining=3,
        inventory=(),
    )
    ctx = _make_ctx(st)
    res = item.use(ctx)
    assert res.ok is True
    assert isinstance(res.extra, dict)
    assert res.extra.get("swap_top_into_first_player_card") is True

