"""Content isolation, shared effects, permission failures and resumable runs."""

from __future__ import annotations

import json
import io

import pytest

from chaos_blackjack.agent import AgentSession
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.content.loader import load_content_packs
from chaos_blackjack.content.scaffold import scaffold
from chaos_blackjack.content.validation import validate_packs
from chaos_blackjack.contracts.observation import ChaosObservation
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.items.runtime import execute_item
from chaos_blackjack.registry import get_registry
from chaos_blackjack.rules.modifiers import ActiveModifiers


def table(inventory=("example_trim",)):
    return GameState(
        player_hand=tuple(Card(Rank(r)) for r in ("5", "6", "4")),
        dealer_hand=(Card(Rank("9")), Card(Rank("7"))),
        deck=(Card(Rank("2")), Card(Rank("K"))),
        phase=GamePhase.PLAYER_TURN, chaos_budget_remaining=5, inventory=inventory,
    )


def test_pack_is_scoped_and_help_is_visible():
    catalog = load_content_packs(("example",))
    assert catalog.registry.resolve_item("example_trim") is not None
    assert get_registry().resolve_item("example_trim") is None
    assert load_content_packs(()).registry.resolve_ai("example_dealer") is None
    s = AgentSession.new(seed=7, content_packs=("example",))
    item = s.observe()["items"][0]
    assert item["id"] == "example_trim" and "Discard" in item["help"]
    assert s.controller.config.shop_prices["example_trim"] == 20
    assert catalog.shop_items == ("example_trim",)


def test_player_and_ai_share_effect_and_consume_only_one():
    registry = load_content_packs(("example",)).registry
    before = table(("example_trim", "example_trim"))
    after, result = execute_item(registry, before, "example_trim",
                                 emit=lambda event: None, peek_next_card_rank=lambda: "2")
    pipeline = registry.resolve_ai("example_dealer").build(registry)
    effect = pipeline.run(ChaosObservation(before, ActiveModifiers(), 5, 0),
                          emit=lambda event: None, peek_next_card_rank=lambda: "2")
    assert result.ok and after == effect.state_after
    assert len(after.player_hand) == 2 and after.inventory == ("example_trim",)
    assert after.deck == before.deck and len(before.player_hand) == 3


def test_failed_item_keeps_state_and_inventory():
    registry = load_content_packs(("example",)).registry
    before = table().with_player_hand(table().player_hand[:2])
    after, result = execute_item(registry, before, "example_trim",
                                 emit=lambda event: None, peek_next_card_rank=lambda: "2")
    assert not result.ok and after == before


def test_game_loop_applies_ai_item_once_and_charges_budget():
    controller = GameController(RunConfig(content_packs=("example",), ai_id="example_dealer", use_llm=False))
    after = controller.loop.maybe_apply_chaos_phase(table(("example_trim", "example_trim")))
    assert len(after.player_hand) == 2
    assert after.inventory == ("example_trim",)
    assert after.chaos_budget_remaining == 4
    assert controller.loop._chaos_actions_this_turn == 1


def test_agent_resume_keeps_pack_ai_and_identical_next_action():
    s = AgentSession.new(seed=7, chaos=True, content_packs=("example",), ai_id="example_dealer")
    assert s.execute({"cmd": "bet", "amount": 10})["ok"]
    resumed = AgentSession.from_state(s.to_state())
    assert resumed.observe() == s.observe()
    assert resumed.controller.config.content_packs == ("example",)
    assert resumed.controller.config.ai_id == "example_dealer"
    assert resumed.execute({"cmd": "act", "action": "stand"}) == s.execute({"cmd": "act", "action": "stand"})


def test_regular_save_keeps_pack_ai_and_rule_settings():
    controller = GameController(RunConfig(content_packs=("example",), ai_id="example_dealer",
                                          allow_double=False, blackjack_pays=(2, 1)), save_fn=lambda d, n: n)
    restored = GameController.from_save(controller.save("test"))
    assert restored.config.content_packs == ("example",)
    assert restored.config.ai_id == "example_dealer"
    assert not restored.config.allow_double and restored.config.blackjack_pays == (2, 1)
    assert restored.run.items == controller.run.items


def test_scaffold_validation_and_no_overwrite(tmp_path):
    folder = scaffold("custom", root=tmp_path)
    assert validate_packs(("custom",), root=tmp_path)["ais"] == ["custom_dealer"]
    original = (folder / "plugin.py").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        scaffold("custom", root=tmp_path)
    assert (folder / "plugin.py").read_text(encoding="utf-8") == original


def test_pack_shop_uses_balance_prices_and_resume_keeps_them():
    s = AgentSession.new(seed=7, content_packs=("example",),
                         shop_prices={"example_trim": 17}, starting_items=())
    assert s.observe()["shop"]["offers"][0]["price"] == 17
    assert s.execute({"cmd": "buy", "item": "example_trim"})["ok"]
    restored = AgentSession.from_state(s.to_state())
    assert restored.observe() == s.observe()
    assert restored.controller.run.money == 83
    assert restored.controller.run.items.count("example_trim") == 2
    plain = GameController()
    assert "example_trim" not in {offer.item for offer in plain.shop.offers}
    assert plain.config == RunConfig()


def test_generated_shop_install_is_profile_scoped(tmp_path):
    from chaos_blackjack.content.shop import install_shop
    from chaos_blackjack.data import connect, clone_profile, load_balance, BalanceError

    scaffold("custom", root=tmp_path)
    conn = connect(":memory:")
    try:
        clone_profile(conn, "default", "custom")
        with pytest.raises(BalanceError, match="editable"):
            install_shop(conn, ("custom",), "default", root=tmp_path)
        install_shop(conn, ("custom",), "custom", root=tmp_path)
        assert load_balance("custom", conn).shop_prices["custom_trim"] == 20
        assert "custom_trim" not in load_balance("default", conn).shop_prices
    finally:
        conn.close()


def test_legacy_reward_manifest_has_actionable_error(tmp_path):
    folder = scaffold("legacy", root=tmp_path)
    path = folder / "pack.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["reward_items"] = manifest.pop("shop_items")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="replace reward_items with shop_items"):
        load_content_packs(("legacy",), root=tmp_path)


@pytest.mark.parametrize("pack_id", ["../escape", "BadName", "x/y", ""])
def test_reject_bad_pack_ids(pack_id, tmp_path):
    with pytest.raises(ValueError):
        load_content_packs((pack_id,), root=tmp_path)


def test_duplicate_registration_is_rejected_without_global_leak(tmp_path):
    folder = scaffold("conflict", root=tmp_path)
    (folder / "plugin.py").write_text(
        "def register(registry):\n    registry.register_item('peek', object)\n", encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate item id"):
        load_content_packs(("conflict",), root=tmp_path)
    assert get_registry().resolve_item("peek").name == "peek"


def test_unknown_permission_id_rejected_on_load(tmp_path):
    folder = scaffold("bad_ai", root=tmp_path)
    path = folder / "permissions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["allowed_rules"] = ["invented_rule"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="allowed_rules"):
        load_content_packs(("bad_ai",), root=tmp_path)


def test_ai_observation_hides_hole_card_and_deck_order():
    registry = load_content_packs(("example",)).registry
    pipeline = registry.resolve_ai("example_dealer").build(registry)
    payload = json.loads(pipeline._build_user_prompt(ChaosObservation(table(), ActiveModifiers(), 5, 0)))
    assert payload["dealer_up_card"]["rank"] == "9"
    assert "dealer_hand" not in payload and "deck" not in payload
    assert payload["deck_remaining"] == 2


def test_agent_cli_selects_and_restores_pack(tmp_path, capsys):
    from chaos_blackjack.agent.__main__ import main

    path = str(tmp_path / "pack-run.json")
    assert main(["--state", path, "new", "--pack", "example", "--ai", "example_dealer", "--chaos", "--seed", "7"]) == 0
    initial = json.loads(capsys.readouterr().out)
    assert initial["obs"]["items"][0]["id"] == "example_trim"
    assert main(["--state", path, "bet", "10"]) == 0
    reply = json.loads(capsys.readouterr().out)
    assert reply["ok"] and reply["obs"]["chaos"]["active_rules"][0]["id"] == "tiebreaker_shift"


def test_shortcut_stream_uses_pack_default_ai_without_real_model(monkeypatch, capsys):
    from chaos_blackjack.content.__main__ import main
    import chaos_blackjack.ai.gptsapi_llm as relay

    def unexpected_relay():
        pytest.fail("Offline content play must not construct the real relay")

    monkeypatch.setattr(relay, "try_create_gptsapi_llm", unexpected_relay)
    monkeypatch.setenv("CHAOS_USE_LLM", "1")
    monkeypatch.setattr("sys.stdin", io.StringIO('{"cmd":"bet","amount":10}\n{"cmd":"quit"}\n'))
    assert main(["play", "example", "--agent", "--seed", "7"]) == 0
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(replies) == 2
    assert replies[1]["obs"]["chaos"]["active_rules"][0]["id"] == "tiebreaker_shift"
