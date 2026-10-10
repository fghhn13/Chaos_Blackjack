"""Private advice snapshots, probability, read-only replies and dormant memory."""

import json

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.ai.interaction import UNAVAILABLE_REPLY, ask_chaos
from chaos_blackjack.ai.memory import ChaosMemory
from chaos_blackjack.app.chaos_context import build_chaos_context
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.contracts.chaos_interaction import PokeReply, PokeRequest
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.registry import get_registry


class FakeLLM:
    def __init__(self, response='{"reply":"Keep enough chips to bet."}'):
        self.response = response
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def controller(**kwargs):
    return GameController(RunConfig(seed=3, enable_chaos=True,
                                   shop_prices={"peek": 10, "shield": 30}, **kwargs),
                          save_fn=lambda data, name: name)


def rig(c, phase=TablePhase.PLAYER_TURN):
    card = lambda rank: Card(Rank(rank), "♠")
    c.state = GameState(tuple(map(card, ["9", "7"])), tuple(map(card, ["K", "8"])),
                        tuple(map(card, ["K", "2"])), GamePhase.PLAYER_TURN,
                        inventory=c.run.items)
    c.phase = phase


def test_full_private_snapshot_includes_shop_and_effective_rules():
    c = controller()
    c.buy("peek")
    rig(c)
    c.loop.modifiers = c.loop.modifiers.with_added(
        get_registry().build_chaos_rule("modify_card_value", {"delta": -1}))
    data = json.loads(c.prepare_poke().context_json)
    assert data["dealer"]["cards"] == ["K♠", "8♠"]
    assert data["deck"] == ["K♠", "2♠"]
    assert data["player"]["total"] == 14 and data["next_hit"]["bust"]
    assert data["bankroll"] == 90 and data["inventory"][0]["id"] == "peek"
    assert next(o for o in data["shop"]["offers"] if o["item"] == "peek")["sold"]
    assert data["chaos"]["rules"][0]["params"] == {"delta": -1}
    assert data["item_catalog"]["shield"] and data["chaos"]["permission_profile"]
    # The public view still hides the dealer's second card and total.
    assert not c.view().dealer_cards[1].face_up and c.view().dealer_total is None


def test_regular_chaos_receives_the_same_full_snapshot(monkeypatch):
    c = controller()
    c.buy("peek")
    rig(c, TablePhase.CHAOS)
    llm = FakeLLM('{"action":"noop"}')
    c.loop.pipeline.llm = llm
    monkeypatch.setattr(c.loop.pipeline.scheduler, "should_attempt", lambda obs: True)
    c.resolve_chaos()
    user = llm.calls[0][1]
    data = json.loads(user.split("\n")[1])
    assert data["bankroll"] == 90 and data["dealer"]["cards"] == ["K♠", "8♠"]
    assert data["shop"]["offers"] and data["deck"] == ["K♠", "2♠"]


@pytest.mark.parametrize("sample,intent", [(0, "guide"), (.499999, "guide"),
                                          (.5, "mislead"), (.999999, "mislead")])
def test_fifty_percent_intent_boundary(monkeypatch, sample, intent):
    c = controller()
    assert c.config.chaos_guidance_probability == .5
    monkeypatch.setattr(c._poke_rng, "random", lambda: sample)
    assert c.prepare_poke().intent == intent


def test_pokes_do_not_change_deal_randomness():
    c, control = controller(), controller()
    for _ in range(20):
        c.prepare_poke()
    c.place_bet(10)
    control.place_bet(10)
    assert c.state == control.state and c.rng.getstate() == control.rng.getstate()


@pytest.mark.parametrize("phase", [TablePhase.CHAOS, TablePhase.DEALER_TURN, TablePhase.RUN_OVER])
def test_poke_rejected_outside_player_decisions(phase):
    c = controller()
    c.phase = phase
    with pytest.raises(ActionError):
        c.prepare_poke()


def test_poke_rejected_with_chaos_off():
    with pytest.raises(ActionError):
        GameController().prepare_poke()


@pytest.mark.parametrize("raw", ["not JSON", '[]', '{"reply":"hit","action":"apply_rule"}',
                               '{"reply":" "}', '{"reply":2}',
                               json.dumps({"reply": "x" * 321}), RuntimeError("private error")])
def test_invalid_or_failed_reply_uses_one_request(raw):
    llm = FakeLLM(raw)
    reply = ask_chaos(llm, controller().prepare_poke())
    assert reply == PokeReply(UNAVAILABLE_REPLY, ok=False)
    assert len(llm.calls) == 1


@pytest.mark.parametrize("intent", ["guide", "mislead"])
def test_backend_receives_intent_and_context_without_mutating_game(intent):
    c = controller()
    before = c.view()
    request = PokeRequest(build_chaos_context(c), intent)
    llm = FakeLLM('```json\n{"reply":"  Keep  enough chips.  "}\n```')
    reply = ask_chaos(llm, request)
    assert reply == PokeReply("Keep enough chips.")
    sent = json.loads(llm.calls[0][1])
    assert sent["intent"] == intent and sent["context"]["shop"]["offers"]
    assert c.accept_poke_reply(request, reply)
    assert c.view() == before
    notices = c.drain_notices()
    assert notices[-1].kind == NoticeKind.CHAOS_POKE_REPLY
    assert notices[-1].data == {"text": "Keep enough chips."}


def test_stale_reply_is_discarded():
    c = controller()
    request = c.prepare_poke()
    c.buy("peek")
    assert not c.accept_poke_reply(request, PokeReply("Bet 50."))
    assert NoticeKind.CHAOS_POKE_REPLY not in [n.kind for n in c.drain_notices()]


def test_offline_suggestions_react_to_imminent_bust():
    c = controller()
    rig(c)
    snapshot = build_chaos_context(c)
    assert "stand" in ask_chaos(c.loop.pipeline.llm, PokeRequest(snapshot, "guide")).text
    assert "hit" in ask_chaos(c.loop.pipeline.llm, PokeRequest(snapshot, "mislead")).text


def test_memory_default_does_not_record_or_persist():
    c = controller()
    c.buy("peek")
    request = c.prepare_poke()
    c.accept_poke_reply(request, PokeReply("Keep some chips."))
    assert c.chaos_memory.export() is None
    assert "memory" not in json.loads(build_chaos_context(c))
    assert "chaos_memory" not in c.save("unused").to_dict()
    memory = ChaosMemory()
    memory.record(1, "ignored", {"unserializable": object()})
    assert memory.export() is None


def test_opt_in_memory_is_bounded_detached_and_loadable():
    c = controller(chaos_memory_enabled=True, chaos_memory_limit=2)
    c.buy("peek")
    for text in ("First reply.", "Second reply.", "Last reply."):
        request = c.prepare_poke()
        assert c.accept_poke_reply(request, PokeReply(text))
    entries = c.chaos_memory.export()
    assert len(entries) == 2 and entries[-1]["details"]["text"] == "Last reply."
    entries[-1]["details"]["text"] = "Changed outside memory."
    data = RunSaveData.from_dict(c.save("unused").to_dict())
    loaded = GameController.from_save(data, c.config)
    assert loaded.chaos_memory.export() == c.chaos_memory.export()
    assert json.loads(build_chaos_context(loaded))["memory"][-1]["details"]["text"] == "Last reply."
    assert GameController.from_save(data).chaos_memory.export() is None


def test_agent_state_preserves_memory_configuration_and_history():
    s = AgentSession.new(seed=3, chaos=True, chaos_memory_enabled=True, chaos_memory_limit=2)
    s.execute({"cmd": "buy", "item": s.observe()["shop"]["offers"][0]["item"]})
    restored = AgentSession.from_state(s.to_state())
    assert restored.controller.config.chaos_memory_enabled
    assert restored.controller.config.chaos_memory_limit == 2
    assert restored.controller.chaos_memory.export() == s.controller.chaos_memory.export()


@pytest.mark.parametrize("config", [{"chaos_guidance_probability": -.1},
                                   {"chaos_guidance_probability": 1.1},
                                   {"chaos_memory_limit": 0}])
def test_invalid_interaction_configuration_is_rejected(config):
    with pytest.raises(ValueError):
        RunConfig(**config)
