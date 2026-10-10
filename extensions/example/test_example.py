"""Run explicitly: python -m pytest extensions/example/test_example.py"""

from chaos_blackjack.content.loader import load_content_packs
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.items.runtime import execute_item
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.rules.modifiers import ActiveModifiers


def state():
    return GameState(
        player_hand=tuple(Card(Rank(r)) for r in ("5", "6", "4")),
        dealer_hand=(Card(Rank("9")), Card(Rank("7"))),
        deck=(Card(Rank("2")),), phase=GamePhase.PLAYER_TURN,
        inventory=("example_trim",), chaos_budget_remaining=5,
    )


def test_item_discards_one_card_and_consumes_one_copy():
    registry = load_content_packs(("example",)).registry
    before = state()
    after, result = execute_item(registry, before, "example_trim",
                                 emit=lambda event: None, peek_next_card_rank=lambda: "2")
    assert result.ok
    assert [str(card.rank) for card in after.player_hand] == ["5", "6"]
    assert after.deck == before.deck
    assert after.inventory == ()
    assert len(before.player_hand) == 3


def test_ai_uses_the_same_item_effect():
    registry = load_content_packs(("example",)).registry
    pipeline = registry.resolve_ai("example_dealer").build(registry)
    effect = pipeline.run(
        ChaosObservation(state(), ActiveModifiers(), 5, 0),
        emit=lambda event: None, peek_next_card_rank=lambda: "2",
    )
    assert effect.state_after is not None
    assert len(effect.state_after.player_hand) == 2
    assert effect.state_after.inventory == ()
