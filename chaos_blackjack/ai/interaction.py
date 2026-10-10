"""Read-only advice. The worker receives a snapshot, never a controller."""

import json

from chaos_blackjack.ai.pipeline import StubLLM, _strip_json_fence
from chaos_blackjack.ai.prompts_loader import load_prompt
from chaos_blackjack.contracts.chaos_interaction import PokeReply, PokeRequest
from chaos_blackjack.contracts.llm import LLMBackend

UNAVAILABLE_REPLY = "I'm keeping my thoughts to myself. Try again later."
MAX_REPLY_LENGTH = 320


def _offline_reply(request: PokeRequest) -> PokeReply:
    context = json.loads(request.context_json)
    guide = request.intent == "guide"
    if context["phase"] == "betting":
        offers = [o for o in context["shop"]["offers"]
                  if not o["sold"] and context["bankroll"] - o["price"] >= 2]
        if offers:
            item = (min if guide else max)(offers, key=lambda offer: offer["price"])["item"]
            return PokeReply(f"Consider {item.replace('_', ' ')}. " + (
                "Keep enough chips for your next bet." if guide else "Spending more always improves your luck."))
        return PokeReply("Keep your bet modest." if guide else "Bet the maximum. The house owes you a win.")
    if context["phase"] == "player_turn":
        next_hit = context["next_hit"]
        should_stand = context["player"]["total"] >= 17 or not next_hit or next_hit["bust"]
        action = "stand" if should_stand == guide else "hit"
        return PokeReply(f"I'd {action} here. But then, would you trust the house?")
    return PokeReply("Watch the new shop stock before betting again." if guide
                     else "A loss means your next win is guaranteed. Raise your next bet.")


def ask_chaos(llm: LLMBackend, request: PokeRequest) -> PokeReply:
    if isinstance(llm, StubLLM):
        return _offline_reply(request)
    user = json.dumps({"intent": request.intent, "context": json.loads(request.context_json)},
                      ensure_ascii=False)
    try:
        raw = llm.complete(load_prompt("poke"), user)
        data = json.loads(_strip_json_fence(raw))
        # No gameplay actions can pass through this reply contract.
        if not isinstance(data, dict) or set(data) != {"reply"}:
            raise ValueError("Unexpected interaction reply")
        text = data["reply"]
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_REPLY_LENGTH:
            raise ValueError("Invalid interaction reply text")
        return PokeReply(" ".join(text.split()))
    except (RuntimeError, ValueError, TypeError):
        # One attempt only: no automatic extra billed completion for a poke.
        return PokeReply(UNAVAILABLE_REPLY, ok=False)
