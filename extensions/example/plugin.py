"""Items and offline Chaos AI. Register only through the supplied registry."""

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
    name = "example_trim"

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
        if "example_trim" in obs["inventory"] and len(obs["player_cards"]) >= 3:
            return json.dumps({"action": "use_item", "item_id": "example_trim",
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
    registry.register_ai("example_dealer", AIProfile(
        description="A helpful dealer who gives ties to the player.",
        prompt=(folder / "prompt.txt").read_text(encoding="utf-8"),
        permissions=json.loads((folder / "permissions.json").read_text(encoding="utf-8")),
        offline_backend=OfflineDealer,
    ))
