"""Meta progression: players, meta shop, upgrades applied to runs, rewards, history."""

from __future__ import annotations

import pytest

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.data import clone_profile, connect, default_balance
from chaos_blackjack.data.admin import set_value
from chaos_blackjack.data.__main__ import main as data_cli
from chaos_blackjack.meta import MetaError, MetaService
from chaos_blackjack.meta.effects import get_effect
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.modes import GameMode, get_mode, modes, register_mode


@pytest.fixture()
def svc():
    s = install_fake(demo=False)
    yield s
    meta.use_service(None)


def _play_out(c: GameController, bet: str = "max") -> None:
    """Stand on everything with a big or small bet until the run ends."""
    while c.phase != TablePhase.RUN_OVER:
        v = c.view()
        if c.phase == TablePhase.BETTING:
            c.place_bet(v.bet_max if bet == "max" else v.bet_min)
        if c.phase == TablePhase.CHAOS:
            c.resolve_chaos()
        if c.phase == TablePhase.PLAYER_TURN:
            c.stand()
        c.finish_dealer()
        if c.phase == TablePhase.ROUND_OVER:
            c.next_round()


def _rich(svc: MetaService, slot: int = 1, tokens: int = 500):
    p = meta.create_player(slot, f"P{slot}")
    return svc.grant_tokens(p.id, tokens)


# ------------------------------------------------------------- players


def test_three_slots(svc) -> None:
    assert [s.slot for s in meta.list_slots()] == [1, 2, 3]
    assert all(s.player is None for s in meta.list_slots())
    p = meta.create_player(2, "  Lucky   Lou ")
    assert p.name == "Lucky Lou" and p.tokens == 0 and p.upgrades == {}
    assert meta.list_slots()[1].player == p
    with pytest.raises(MetaError, match="already used"):
        meta.create_player(2, "Other")
    with pytest.raises(MetaError, match="Slot must be"):
        meta.create_player(4, "Nope")
    with pytest.raises(MetaError, match="empty"):
        meta.create_player(1, "   ")
    with pytest.raises(MetaError, match="at most"):
        meta.create_player(1, "x" * 25)
    assert meta.rename_player(p.id, "Lou").name == "Lou"
    meta.delete_player(p.id)
    assert meta.list_slots()[1].player is None
    with pytest.raises(MetaError, match="Unknown player"):
        meta.get_player(p.id)


# ---------------------------------------------------------------- shop


def test_buying_permanent_levels_and_consumables(svc) -> None:
    p = meta.create_player(1, "A")
    offer = {o.upgrade_id: o for o in meta.meta_shop(p.id)}["start_money"]
    assert (offer.next_cost, offer.can_buy, offer.reason) == (15, False, "Needs 15 tokens")
    svc.grant_tokens(p.id, 100)
    p = meta.buy_upgrade(p.id, "start_money")
    assert p.tokens == 85 and p.upgrades["start_money"] == 1
    offer = {o.upgrade_id: o for o in meta.meta_shop(p.id)}["start_money"]
    assert offer.owned == 1 and offer.next_cost == 25  # cost + step
    meta.buy_upgrade(p.id, "start_money")
    p = meta.buy_upgrade(p.id, "start_money")
    assert p.tokens == 100 - 15 - 25 - 35 and p.upgrades["start_money"] == 3
    offer = {o.upgrade_id: o for o in meta.meta_shop(p.id)}["start_money"]
    assert offer.next_cost is None and offer.reason == "Maximum level"
    with pytest.raises(MetaError, match="Maximum level"):
        meta.buy_upgrade(p.id, "start_money")
    p = meta.buy_upgrade(p.id, "start_peek")
    assert p.upgrades["start_peek"] == 1
    with pytest.raises(MetaError, match="no upgrade"):
        meta.buy_upgrade(p.id, "nothing")


def test_every_catalog_upgrade_has_a_known_effect_and_text(svc) -> None:
    p = _rich(svc)
    for o in meta.meta_shop(p.id):
        assert o.can_buy and o.name and o.description, o
    for u in default_balance().meta_upgrades:
        get_effect(u.effect)


def test_requirements(svc, tmp_path, monkeypatch) -> None:
    db = tmp_path / "game.db"
    monkeypatch.setenv("CHAOS_DB", str(db))
    conn = connect(db)
    clone_profile(conn, "default", "req")
    set_value(conn, "req", "upgrade.shop_discount.requires", "shop_slot")
    real = MetaService(conn)
    p = real.grant_tokens(real.create_player(1, "R").id, 500).id
    offer = {o.upgrade_id: o for o in real.meta_shop(p, "req")}["shop_discount"]
    assert not offer.can_buy and offer.reason == "Requires shop_slot"
    real.buy_upgrade(p, "shop_slot", "req")
    assert real.buy_upgrade(p, "shop_discount", "req").upgrades["shop_discount"] == 1


# ---------------------------------------------------------------- runs


def test_upgrades_shape_the_run(svc) -> None:
    p = _rich(svc)
    for u in ("start_money", "start_money", "shop_slot", "shop_discount", "start_peek", "start_peek",
              "start_shield"):
        meta.buy_upgrade(p.id, u)
    run = meta.start_run(p.id, "normal", consumables=["start_peek", "start_shield"], seed=3)
    cfg = run.config
    base = RunConfig()
    assert cfg.start_money == base.start_money + 20 and cfg.shop_slots == base.shop_slots + 1
    assert cfg.shop_prices["peek"] == 9 and cfg.shop_prices["shield"] == 27   # 10% off
    assert cfg.starting_items == ("peek", "shield") and not cfg.enable_chaos
    assert sorted(i.id for i in run.controller.view().items) == ["peek", "shield"]
    assert run.controller.view().money == base.start_money + 20
    assert run.applied == {"shop_discount": 1, "shop_slot": 1, "start_money": 2, "start_peek": 1, "start_shield": 1}
    after = meta.get_player(p.id).upgrades
    assert after["start_peek"] == 1 and "start_shield" not in after  # consumables used up
    assert cfg.balance_hash != RunConfig(seed=3).balance_hash


def test_bringing_what_you_do_not_have(svc) -> None:
    p = _rich(svc)
    meta.buy_upgrade(p.id, "start_peek")
    with pytest.raises(MetaError, match="not have enough"):
        meta.start_run(p.id, "normal", consumables=["start_peek", "start_peek"])
    with pytest.raises(MetaError, match="not a consumable"):
        meta.start_run(p.id, "normal", consumables=["start_money"])
    with pytest.raises(MetaError, match="Unknown game mode"):
        meta.start_run(p.id, "speed")
    assert meta.get_player(p.id).upgrades["start_peek"] == 1  # nothing used up on failure


def test_modes(svc) -> None:
    assert [m.id for m in modes()][:2] == ["normal", "chaos"]
    assert get_mode("chaos").apply(RunConfig()).enable_chaos
    p = meta.create_player(1, "M")
    assert [(o.mode.id, o.unlocked) for o in meta.modes(p.id)][:2] == [("normal", True), ("chaos", True)]
    register_mode(GameMode("test_locked", "Locked", "", unlocked_by="unlock_test", order=99))
    try:
        assert (meta.modes(p.id)[-1].mode.id, meta.modes(p.id)[-1].unlocked) == ("test_locked", False)
        with pytest.raises(MetaError, match="locked"):
            meta.start_run(p.id, "test_locked")
    finally:
        from chaos_blackjack import modes as modes_module

        modes_module._MODES.pop("test_locked")  # noqa: SLF001


def test_victory_pays_and_records(svc) -> None:
    from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank

    p = meta.create_player(1, "W")
    run = meta.start_run(p.id, "normal", seed=1)
    c = run.controller
    c.run.money = 300
    c.place_bet(150)
    c.state = GameState((Card(Rank("K"), "♠"), Card(Rank("Q"), "♠")), (Card(Rank("10"), "♥"), Card(Rank("8"), "♥")),
                        (Card(Rank("2"), "♣"),), GamePhase.PLAYER_TURN)
    c.stand()
    c.finish_dealer()
    assert c.run_end is not None and c.run_end.kind == "victory"
    reward = meta.finish_run(run.run_id, c)
    assert reward.result == "victory" and reward.tokens == 10 and reward.breakdown == (("Victory", 10),)
    assert reward.player.tokens == 10 and reward.player.stats.victories == 1
    rec = meta.history(p.id)[0]
    assert (rec.result, rec.final_money, rec.peak_money) == ("victory", 450, 450)


def test_defeat_pays_consolation_and_fills_history_and_codex(svc) -> None:
    p = meta.create_player(1, "L")
    run = meta.start_run(p.id, "chaos", seed=2)
    run.controller.buy(run.controller.view().shop_offers[0].item)
    _play_out(run.controller)
    if run.controller.run_end.kind != "defeat":
        pytest.skip("seed won")
    reward = meta.finish_run(run.run_id, run.controller)
    rec = meta.history(p.id)[0]
    assert rec.result == "defeat" and rec.mode == "chaos" and rec.tokens_earned == reward.tokens
    assert 0 <= reward.tokens <= 5 and reward.player.tokens == reward.tokens
    assert sum(t for _, t in reward.breakdown) == reward.tokens
    assert rec.summary["rounds"] == rec.rounds and rec.summary["rules_seen"]
    assert rec.summary["items_bought"]
    seen = meta.codex_seen(p.id)
    assert ("mode", "chaos") in seen and ("ai", "default") in seen
    assert any(k == "rule" for k, _ in seen) and any(k == "item" for k, _ in seen)
    stats = meta.get_player(p.id).stats
    assert (stats.runs, stats.defeats, stats.tokens_earned) == (1, 1, reward.tokens)
    with pytest.raises(MetaError, match="already been settled"):
        meta.finish_run(run.run_id, run.controller)


def test_consolation_formula() -> None:
    b = default_balance()
    assert sum(t for _, t in meta.consolation_tokens(b, 10, 100, 100)) == 2      # 10 * 0.2
    assert sum(t for _, t in meta.consolation_tokens(b, 10, 100, 150)) == 4      # + 0.5 * 4
    assert sum(t for _, t in meta.consolation_tokens(b, 60, 100, 300)) == 5      # capped
    assert meta.consolation_tokens(b, 60, 100, 300)[-1][0].startswith("Consolation cap")


def test_unfinished_runs(svc) -> None:
    p = meta.create_player(1, "U")
    run = meta.start_run(p.id, "normal", seed=4)
    with pytest.raises(MetaError, match="not over"):
        meta.finish_run(run.run_id, run.controller)
    run.controller.place_bet(5)
    if run.controller.phase == TablePhase.PLAYER_TURN:
        run.controller.save("slot1-autosave")
        resumed = meta.resume_run(p.id)
        assert resumed is not None and resumed.run_id == run.run_id
        assert resumed.controller.view().player_cards == run.controller.view().player_cards
    meta.abandon_run(run.run_id)
    assert meta.history(p.id)[0].result == "abandoned" and meta.resume_run(p.id) is None
    assert meta.get_player(p.id).stats.abandoned == 1


def test_listeners_see_every_notice_without_consuming() -> None:
    c = GameController(RunConfig(seed=1))
    seen = []
    c.add_listener(seen.append)
    c.place_bet(5)
    drained = c.drain_notices()
    assert seen == drained and any(n.kind == NoticeKind.ROUND_STARTED for n in seen)
    c.remove_listener(seen.append)


def test_data_cli_players(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "game.db"))
    real = MetaService()
    real.create_player(3, "Cli")
    assert data_cli(["grant", "3", "40"]) == 0
    assert data_cli(["players"]) == 0
    assert data_cli(["history", "3"]) == 0
    assert data_cli(["history", "1"]) == 1
    out = capsys.readouterr()
    assert "Cli: 40 tokens" in out.out and "slot 1: (empty)" in out.out and "Slot 1 is empty" in out.err
