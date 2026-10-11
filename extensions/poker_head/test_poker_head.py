"""Poker Head pack: offline decisions, advice, and the persona's assets and lines."""

import json

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.ai.interaction import ask_chaos
from chaos_blackjack.content.ai_profile import PERSONA_EVENTS, persona_image
from chaos_blackjack.content.loader import load_content_packs

PERMISSIONS = {"modify_card_value", "suit_power", "odd_even_chaos", "tiebreaker_shift", "fragile_bust", "great_crash"}


def profile():
    return load_content_packs(("poker_head",)).registry.resolve_ai("poker_head")


def controller(seed: int = 3) -> GameController:
    return GameController(RunConfig(seed=seed, enable_chaos=True, content_packs=("poker_head",),
                                    ai_id="poker_head", use_llm=False))


def test_persona_has_every_portrait_and_only_known_events():
    p = profile().persona
    assert p.name == "Poker Head" and p.default == "neutral"
    assert len(p.portraits) == 8 and all(path.is_file() for path in p.portraits.values())
    assert set(p.moods) | set(p.lines) <= set(PERSONA_EVENTS)
    assert persona_image("poker_head_present_card") == p.portraits["present_card"]
    assert all("{rule}" in line for line in p.lines["rule_applied"])


def test_offline_rounds_use_allowed_rules_or_stay_calm_and_always_narrate():
    seen = set()
    for seed in range(12):
        c = controller(seed)
        c.place_bet(5)
        if c.phase.value != "chaos":
            continue
        c.resolve_chaos()
        rules = {r.id for r in c.view().active_rules}
        assert rules <= PERMISSIONS and len(rules) <= 1
        assert c.view().narration
        seen |= rules or {"calm"}
    assert "calm" in seen and len(seen) >= 3


def test_same_request_same_answer_and_disabled_rules_are_respected():
    backend = profile().offline_backend()
    system = 'x\nAuthoritative run-specific action constraints:\n{"allowed_rules": ["suit_power"]}\nmore'
    answers = {backend.complete(system, json.dumps({"round": n})) for n in range(40)}
    actions = [json.loads(a) for a in answers]
    assert {a.get("rule_id") for a in actions} <= {None, "suit_power"}
    assert backend.complete(system, "{}") == backend.complete(system, "{}")


def test_never_uses_the_players_items():
    assert profile().permissions["allowed_items"] == []


@pytest.mark.parametrize("intent", ["guide", "mislead"])
def test_advice_is_a_short_reply_in_every_phase(intent):
    c = controller()
    llm = c.loop.pipeline.llm
    request = c.prepare_poke()
    reply = ask_chaos(llm, type(request)(request.context_json, intent))
    assert reply.ok and 0 < len(reply.text) <= 320 and "{" not in reply.text
