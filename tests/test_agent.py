"""Agent-player interface: AgentSession, observations, CLI."""

from __future__ import annotations

import io
import json

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.agent.__main__ import main
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _rig(session: AgentSession, player, dealer, deck=()) -> None:
    """Make the next deal fixed."""
    ctrl = session.controller

    def fixed_round(seed=None, *, inventory_override=None):
        ctrl.loop.modifiers = ctrl.loop.modifiers.with_cleared()
        return GameState(tuple(player), tuple(dealer), tuple(deck), GamePhase.PLAYER_TURN,
                         inventory=inventory_override or ())

    ctrl.loop.new_round = fixed_round  # type: ignore[method-assign]


def test_new_run_starts_at_betting() -> None:
    r = AgentSession.new(seed=7).execute({"cmd": "observe"})
    obs = r["obs"]
    assert r["ok"] and obs["schema"] == 3
    assert obs["phase"] == "betting" and obs["legal_actions"] == ["bet", "buy", "reroll"]
    assert obs["shop"]["reroll_price"] == 3
    assert len(obs["shop"]["offers"]) == 3 and obs["shop"]["restock_in"] == 2
    assert obs["bet_range"] == [5, 50] and obs["you"] is None
    assert "bet <amount>" in obs["hint"]


def test_hole_card_and_deck_never_leak() -> None:
    s = AgentSession.new(seed=7)
    _rig(s, [_c("8"), _c("3")], [_c("K"), _c("7", "♦")], deck=[_c("Q", "♥")])
    obs = s.execute({"cmd": "bet", "amount": 10})["obs"]
    assert obs["dealer"] == {"cards": ["K♠", "??"], "total": None}
    text = json.dumps(obs, ensure_ascii=False)
    assert "7♦" not in text and "Q♥" not in text
    assert "7♦" not in json.dumps(s.to_state(), ensure_ascii=False)


def test_round_auto_advances_to_next_bet_with_result() -> None:
    s = AgentSession.new(seed=1)
    _rig(s, [_c("10"), _c("9")], [_c("10"), _c("6")], deck=[_c("K")])
    s.execute({"cmd": "bet", "amount": 10})
    r = s.execute({"cmd": "act", "action": "stand"})
    obs = r["obs"]
    assert r["ok"] and obs["phase"] == "betting" and obs["round"] == 2
    lr = obs["last_round"]
    assert lr["outcome"] == "player" and lr["delta"] == 10
    assert lr["dealer_cards"] == ["10♠", "6♠", "K♠"] and lr["your_cards"] == ["10♠", "9♠"]
    assert any("Dealer busts" in e for e in r["events"])
    s.execute({"cmd": "bet", "amount": 5})
    assert s.observe()["last_round"] is None


def test_illegal_action_is_structured_and_changes_nothing() -> None:
    s = AgentSession.new(seed=7)
    r = s.execute({"cmd": "act", "action": "hit"})
    assert not r["ok"]
    assert r["error"]["code"] == "illegal_action" and r["error"]["legal_actions"] == ["bet", "buy", "reroll"]
    assert s.steps == 0 and r["obs"]["phase"] == "betting"


@pytest.mark.parametrize(
    "command, code",
    [
        ({"cmd": "bet"}, "invalid_argument"),
        ({"cmd": "bet", "amount": True}, "invalid_argument"),
        ({"cmd": "bet", "amount": "lots"}, "invalid_argument"),
        ({"cmd": "bet", "amount": 999}, "illegal_action"),
        ({"cmd": "dance"}, "unknown_command"),
    ],
)
def test_bad_commands(command, code) -> None:
    r = AgentSession.new(seed=7).execute(command)
    assert not r["ok"] and r["error"]["code"] == code


def test_actions_and_items() -> None:
    s = AgentSession.new(seed=7)
    s.controller.run.items = ("peek",)
    _rig(s, [_c("5"), _c("6")], [_c("10"), _c("7")], deck=[_c("9"), _c("K")])
    obs = s.execute({"cmd": "bet", "amount": 10})["obs"]
    assert set(obs["legal_actions"]) == {"hit", "stand", "double", "surrender", "use_item"}
    assert obs["items"][0]["help"]
    r = s.execute({"cmd": "act", "action": "use_item", "item": "peek"})
    assert r["ok"] and any("9" in e for e in r["events"])
    bad = s.execute({"cmd": "act", "action": "use_item", "item": "peek"})
    assert bad["error"]["code"] == "illegal_action"
    assert s.execute({"cmd": "act", "action": "use_item"})["error"]["code"] == "invalid_argument"
    r = s.execute({"cmd": "act", "action": "double"})
    assert r["obs"]["last_round"]["doubled"] and r["obs"]["last_round"]["delta"] == 20


def _play(session_steps, commands):
    """Run commands either in one session or via a to_state/from_state hop each step."""
    s = AgentSession.new(seed=42, chaos=True)
    out = []
    for cmd in commands:
        if session_steps:
            s = AgentSession.from_state(json.loads(json.dumps(s.to_state())))
        out.append(s.execute(cmd)["obs"])
    return out


def test_state_roundtrip_is_deterministic() -> None:
    commands = []
    for _ in range(6):
        commands += [{"cmd": "bet", "amount": 5}, {"cmd": "act", "action": "hit"},
                     {"cmd": "act", "action": "stand"}]
    assert _play(False, commands) == _play(True, commands)


def test_same_seed_same_game() -> None:
    a = AgentSession.new(seed=5).execute({"cmd": "bet", "amount": 10})["obs"]
    b = AgentSession.new(seed=5).execute({"cmd": "bet", "amount": 10})["obs"]
    assert a == b


def test_run_over_and_step_limit() -> None:
    s = AgentSession.new(seed=1, target_money=105)
    _rig(s, [_c("10"), _c("9")], [_c("10"), _c("7")])
    s.execute({"cmd": "bet", "amount": 10})
    obs = s.execute({"cmd": "act", "action": "stand"})["obs"]
    assert obs["phase"] == "run_over" and obs["run_end"]["kind"] == "victory"
    assert obs["last_round"]["outcome"] == "player"
    assert s.execute({"cmd": "bet", "amount": 1})["error"]["code"] == "run_over"
    restored = AgentSession.from_state(s.to_state())
    assert restored.observe()["phase"] == "run_over"

    limited = AgentSession.new(seed=1, max_steps=1)
    limited.execute({"cmd": "bet", "amount": 5})
    assert limited.execute({"cmd": "act", "action": "stand"})["error"]["code"] == "step_limit"


# --- CLI -------------------------------------------------------------------

def _cli(capsys, tmp_path, *args):
    code = main(["--state", str(tmp_path / "run.json"), "--compact", *args])
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_cli_one_shot_flow_logs_and_exit_codes(capsys, tmp_path) -> None:
    code, r = _cli(capsys, tmp_path, "new", "--seed", "7")
    assert code == 0 and r["run"]["seed"] == 7
    code, r = _cli(capsys, tmp_path, "act", "hit")
    assert code == 1 and r["error"]["code"] == "illegal_action"
    code, r = _cli(capsys, tmp_path, "bet", "20")
    assert code == 0 and r["obs"]["phase"] == "player_turn"
    code, r = _cli(capsys, tmp_path, "--brief", "act", "stand")
    assert code == 0 and set(r["obs"]) <= {"phase", "summary", "hint", "legal_actions", "bet_range",
                                            "shop", "last_round", "run_end"}
    log = (tmp_path / "run.log.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["command"]["cmd"] for x in log] == ["new", "act", "bet", "act"]
    assert [json.loads(x)["ok"] for x in log] == [True, False, True, True]


def test_cli_missing_run_and_llm_without_key(capsys, tmp_path, monkeypatch) -> None:
    code, r = _cli(capsys, tmp_path, "observe")
    assert code == 2 and r["error"]["code"] == "usage"
    monkeypatch.setenv("GPTSAPI_API_KEY", "")
    code, r = _cli(capsys, tmp_path, "new", "--llm")
    assert code == 2 and "GPTSAPI_API_KEY" in r["error"]["message"]


def test_cli_streaming_mode(capsys, monkeypatch) -> None:
    lines = [
        json.dumps({"cmd": "bet", "amount": 10}),
        "not json",
        json.dumps({"cmd": "act", "action": "stand"}),
        json.dumps({"cmd": "new", "seed": 3}),
        json.dumps({"cmd": "quit"}),
        json.dumps({"cmd": "observe"}),  # after quit: ignored
    ]
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines) + "\n"))
    assert main(["play", "--seed", "7"]) == 0
    replies = [json.loads(x) for x in capsys.readouterr().out.strip().splitlines()]
    assert len(replies) == 5
    assert replies[0]["obs"]["phase"] == "betting"
    assert replies[1]["obs"]["phase"] == "player_turn"
    assert replies[2]["error"]["code"] == "invalid_json"
    assert replies[3]["obs"]["phase"] == "betting" and replies[3]["obs"]["last_round"]
    assert replies[4]["obs"]["round"] == 1
