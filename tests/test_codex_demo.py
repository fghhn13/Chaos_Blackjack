"""Replay semantics, determinism, live tuning and isolation from billed models."""

import copy
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.codex import DemoScript, DemoStep as Step, codex_entries, run_demo
from chaos_blackjack.codex.scripts import ITEM_DEMOS, RULE_DEMOS


@pytest.mark.parametrize("entry", codex_entries("rule") + codex_entries("item"), ids=lambda e: e.id)
def test_every_builtin_demo_is_deterministic_and_settles(entry):
    cfg = RunConfig(seed=None)
    before = copy.deepcopy(cfg.to_dict())
    frames = run_demo(entry.demo, cfg)
    assert frames == run_demo(entry.demo, cfg)
    assert cfg.to_dict() == before
    assert frames[-1].view.last_result is not None
    assert frames[0].view.dealer_cards[1].face_up is False
    assert frames[0].view.player_cards == frames[1].view.player_cards or entry.id == "swap"
    assert frames[0].view.items != frames[-1].view.items or entry.kind == "rule"
    notices = [n for f in frames for n in f.notices]
    assert sum(n.kind == NoticeKind.ROUND_SETTLED for n in notices) == 1
    if entry.kind == "rule":
        assert any(n.kind == NoticeKind.RULE_MODIFIER_APPLIED and n.data["rule_id"] == entry.id for n in notices)
    else:
        assert any(n.kind == NoticeKind.ITEM_RESULT and n.data == {"item": entry.id, "ok": True} for n in notices)
        assert frames[-1].view.items == ()


@pytest.mark.parametrize("rule_id,total,outcome", [
    ("modify_card_value", 16, "dealer"), ("great_crash", 16, "dealer"),
    ("odd_even_chaos", 20, "player"), ("suit_power", 18, "player"),
    ("fragile_bust", 20, "dealer"), ("reverse_bust", 24, "push"),
    ("tiebreaker_shift", 18, "dealer"),
])
def test_rule_examples_show_real_valuation_and_settlement(rule_id, total, outcome):
    result = run_demo(RULE_DEMOS[rule_id], RunConfig())[-1].view.last_result
    assert (result.player_total, result.outcome) == (total, outcome)
    if rule_id == "reverse_bust":
        assert result.player_bust


def test_profile_tuning_changes_demo_and_not_just_text():
    cfg = replace(RunConfig(), chaos_rule_params={"great_crash": {"ten_value": 8}}, min_bet=7)
    frames = run_demo(RULE_DEMOS["great_crash"], cfg)
    assert frames[1].view.player_total == 16
    assert frames[0].view.current_bet == 7
    assert frames[-1].view.last_result.bet == 7
    assert frames[-1].view.last_result.player_total == 16
    oracle = run_demo(ITEM_DEMOS["fate_oracle"], replace(cfg, item_params={"fate_oracle": {"cards": 5}}))
    used = next(n for frame in oracle for n in frame.notices if n.kind == NoticeKind.ITEM_USED)
    assert used.data["peeked_ranks"] == ["5", "K", "2", "9", "3"]


def test_fixed_rule_params_override_explicit_script_proposals():
    script = DemoScript(("5♠", "6♥"), ("10♣", "7♦"), (), True, (
        Step("deal"), Step("apply_rule", {"rule_id": "modify_card_value", "params": {"delta": 9}}),
    ))
    cfg = RunConfig(chaos_rule_params={"modify_card_value": {"delta": 3}})
    frames = run_demo(script, cfg)
    assert frames[-1].view.player_total == 17
    applied = next(n for n in frames[-1].notices if n.kind == NoticeKind.RULE_MODIFIER_APPLIED)
    assert applied.data["params"] == {"delta": 3}


def test_shield_clears_real_modifiers_and_restores_total():
    frames = run_demo(ITEM_DEMOS["shield"], RunConfig())
    assert frames[1].view.player_total == 12 and frames[1].view.active_rules
    assert frames[2].view.player_total == 14 and frames[2].view.active_rules == ()
    assert frames[2].view.items == ()
    assert frames[1].view.items  # preceding snapshots stay unchanged


def test_hole_card_and_swap_effects_are_visible():
    hacker = run_demo(ITEM_DEMOS["hole_card_hacker"], RunConfig())
    assert hacker[0].view.dealer_total is None
    assert hacker[1].view.hole_revealed and hacker[1].view.dealer_total == 17
    assert hacker[1].view.dealer_cards[1].face_up
    swap = run_demo(ITEM_DEMOS["swap"], RunConfig())
    assert swap[0].view.player_cards[0].rank == "8"
    assert swap[1].view.player_cards[0].rank == "5"
    assert swap[1].view.deck_count == swap[0].view.deck_count - 1


def test_dealer_draws_are_separate_frames_and_follow_config():
    script = DemoScript(("K♠", "9♥"), ("10♣", "6♦"), ("2♣", "3♠"), False,
                        (Step("deal"), Step("stand"), Step("dealer")))
    frames = run_demo(script, RunConfig(dealer_stand_on=20))
    assert [f.view.dealer_total for f in frames[2:]] == [18, 21, 21]
    assert [len(f.view.dealer_cards) for f in frames[2:]] == [3, 4, 4]
    assert frames[-1].view.last_result.outcome == "dealer"


def test_natural_payout_and_early_terminal_stop():
    script = DemoScript(("A♠", "K♥"), ("10♣", "7♦"), ("2♣",), False,
                        (Step("deal", 8), Step("hit"), Step("stand"), Step("dealer")))
    frames = run_demo(script, RunConfig(blackjack_pays=(5, 2)))
    assert len(frames) == 1
    assert frames[0].view.last_result.outcome == "blackjack"
    assert frames[0].view.last_result.delta == 20


def test_profile_can_end_a_rule_demo_early():
    frames = run_demo(RULE_DEMOS["odd_even_chaos"], RunConfig(chaos_rule_params={
        "odd_even_chaos": {"even_delta": 6, "odd_delta": 0},
    }))
    assert frames[-1].view.last_result.outcome == "blackjack"
    assert len(frames) == 2


@pytest.mark.parametrize("action,expected", [("double", "player"), ("surrender", "surrender")])
def test_double_and_surrender_use_controller(action, expected):
    script = DemoScript(("5♠", "6♥"), ("10♣", "7♦"), ("K♣",), False,
                        (Step("deal", 9), Step(action), *((Step("dealer"),) if action == "double" else ())))
    view = run_demo(script, RunConfig())[-1].view
    assert view.last_result.outcome == expected
    assert view.last_result.delta == (18 if action == "double" else -5)
    assert view.last_result.doubled == (action == "double")


def test_captions_and_pauses_do_not_sleep_or_duplicate_notices():
    script = DemoScript(("5♠", "6♥"), ("10♣", "7♦"), (), False,
                        (Step("deal", caption="Dealt."), Step("caption", caption="Consider the hand."),
                         Step("pause"), Step("stand"), Step("dealer")))
    frames = run_demo(script, RunConfig())
    assert frames[0].view == frames[1].view == frames[2].view
    assert frames[1].caption == frames[2].caption == "Consider the hand."
    assert frames[1].notices == frames[2].notices == ()


def test_demos_never_instantiate_a_billed_backend_or_save(monkeypatch):
    from chaos_blackjack.core import game_loop

    def forbidden():
        raise AssertionError("The default LLM must never be constructed by a codex demo")
    monkeypatch.setenv("CHAOS_USE_LLM", "1")
    monkeypatch.setattr(game_loop, "_default_llm", forbidden)
    for entry in codex_entries():
        entry.detail(RunConfig())
        if entry.demo:
            run_demo(entry.demo, RunConfig())


def test_headless_import_and_demo_do_not_import_pygame():
    code = """
import sys
class NoGUI:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'pygame' or fullname.startswith('chaos_blackjack.gui'):
            raise AssertionError('Codex imported the GUI: ' + fullname)
sys.meta_path.insert(0, NoGUI())
from chaos_blackjack.codex import codex_entries, run_demo
from chaos_blackjack.app.config import RunConfig
for entry in codex_entries():
    entry.detail(RunConfig())
    if entry.demo:
        run_demo(entry.demo, RunConfig())
"""
    env = {**os.environ, "CHAOS_USE_LLM": "1", "CHAOS_DB": ":memory:"}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("steps,chaos,error", [
    ((Step("deal"), Step("unknown")), False, ValueError),
    ((Step("hit"),), False, ValueError),
    ((Step("hit"), Step("deal")), False, ValueError),
    ((Step("deal"), Step("deal")), False, ValueError),
    ((Step("deal", True),), False, ValueError),
    ((Step("deal"), Step("apply_rule", "missing")), True, ValueError),
    ((Step("deal"), Step("apply_rule", "great_crash")), False, ValueError),
    ((Step("deal"), Step("dealer")), False, ActionError),
    ((Step("deal"), Step("use_item", "missing")), False, ActionError),
    ((Step("deal"), Step("use_item", "shield")), False, ActionError),
])
def test_invalid_demos_fail_explicitly(steps, chaos, error):
    with pytest.raises(error):
        run_demo(DemoScript(("5♠", "6♥"), ("10♣", "7♦"), ("2♣",), chaos, steps), RunConfig())


@pytest.mark.parametrize("card", ["K", "??", "1♠", "k♠", "Kx"])
def test_malformed_cards_are_rejected(card):
    with pytest.raises(ValueError, match="Invalid demo card"):
        run_demo(DemoScript((card, "6♥"), ("10♣", "7♦"), (), False, (Step("deal"),)), RunConfig())


def test_disabled_rules_remain_visible_and_demonstrable():
    cfg = RunConfig(disabled_rules=("great_crash",))
    entry = next(e for e in codex_entries("rule", cfg) if e.id == "great_crash")
    assert "Disabled" in entry.detail(cfg)
    assert run_demo(entry.demo, cfg)[1].view.player_total == 16
