"""Generate a complete, runnable pack without overwriting existing files."""

from __future__ import annotations

import json
from pathlib import Path

from chaos_blackjack.content.loader import PACK_ROOT, validate_id

PLUGIN = '''"""Items and offline Chaos AI. Register only through the supplied registry."""

import json
from dataclasses import dataclass
from pathlib import Path

from chaos_blackjack.contracts.items import ItemContext, ItemResult
from chaos_blackjack.content.ai_profile import AIProfile


@dataclass(frozen=True)
class RemoveLastCard:
    def apply(self, state):
        return state.with_player_hand(state.player_hand[:-1])


class TrimHand:
    name = "__PACK___trim"

    def use(self, ctx: ItemContext) -> ItemResult:
        if len(ctx.state.player_hand) <= 2:
            return ItemResult(ok=False, message="You need at least three cards.")
        return ItemResult(
            ok=True, message="Your last card was discarded.",
            effects=(RemoveLastCard(),),
        )


class OfflineDealer:
    """Stateless and deterministic; JSON observation -> JSON action."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        obs = json.loads(user_prompt)
        if "__PACK___trim" in obs["inventory"] and len(obs["player_cards"]) >= 3:
            return json.dumps({"action": "use_item", "item_id": "__PACK___trim",
                               "narration": "Let me give you a second chance."})
        return json.dumps({"action": "apply_rule", "rule_id": "tiebreaker_shift",
                           "params": {"ties_to": "player"},
                           "narration": "This round, ties are yours."})


def register(registry):
    folder = Path(__file__).parent
    registry.register_item(
        TrimHand.name, TrimHand,
        description="Discard your last card when you have at least three cards.",
    )
    registry.register_ai("__PACK___dealer", AIProfile(
        description="A helpful dealer who gives ties to the player.",
        prompt=(folder / "prompt.txt").read_text(encoding="utf-8"),
        permissions=json.loads((folder / "permissions.json").read_text(encoding="utf-8")),
        offline_backend=OfflineDealer,
    ))
'''

PACK_TEST = '''"""Run explicitly: python -m pytest extensions/__PACK__/test___PACK__.py"""

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
        inventory=("__PACK___trim",), chaos_budget_remaining=5,
    )


def test_item_discards_one_card_and_consumes_one_copy():
    registry = load_content_packs(("__PACK__",)).registry
    before = state()
    after, result = execute_item(registry, before, "__PACK___trim",
                                 emit=lambda event: None, peek_next_card_rank=lambda: "2")
    assert result.ok
    assert [str(card.rank) for card in after.player_hand] == ["5", "6"]
    assert after.deck == before.deck
    assert after.inventory == ()
    assert len(before.player_hand) == 3


def test_ai_uses_the_same_item_effect():
    registry = load_content_packs(("__PACK__",)).registry
    pipeline = registry.resolve_ai("__PACK___dealer").build(registry)
    effect = pipeline.run(
        ChaosObservation(state(), ActiveModifiers(), 5, 0),
        emit=lambda event: None, peek_next_card_rank=lambda: "2",
    )
    assert effect.state_after is not None
    assert len(effect.state_after.player_hand) == 2
    assert effect.state_after.inventory == ()
'''


def scaffold(pack_id: str, *, root: Path = PACK_ROOT) -> Path:
    validate_id(pack_id)
    folder = root / pack_id
    # mkdir(exist_ok=False) fails before writing anything if the pack exists.
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": 1, "id": pack_id,
        "starting_items": [f"{pack_id}_trim"],
        "reward_items": [f"{pack_id}_trim"],
        "default_ai": f"{pack_id}_dealer",
    }
    permissions = {
        "allowed_rules": ["tiebreaker_shift"],
        "allowed_items": [f"{pack_id}_trim"],
        "attempt_limits": {"max_actions_per_turn": 1, "max_active_effects": 1},
        "budget": {"chaos_budget": 5, "charge_per_effect": 1},
    }
    prompt = (
        "You are a helpful Chaos Blackjack dealer. Give ties to the player with "
        "tiebreaker_shift (params: {\"ties_to\": \"player\"}), or discard their last "
        f"card with item {pack_id}_trim when they have at least three cards.\n"
        "Return ONLY one JSON object with action: noop | apply_rule | use_item, "
        "optional rule_id, params, item_id and narration. Follow the allowed ids "
        "in the observation. Never invent actions.\n"
    )
    for filename, value in (("pack.json", manifest), ("permissions.json", permissions)):
        (folder / filename).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    (folder / "plugin.py").write_text(PLUGIN.replace("__PACK__", pack_id), encoding="utf-8")
    (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
    (folder / f"test_{pack_id}.py").write_text(PACK_TEST.replace("__PACK__", pack_id), encoding="utf-8")
    return folder
