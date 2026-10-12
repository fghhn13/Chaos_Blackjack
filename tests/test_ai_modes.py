"""AI modes: hosts, rule and item pools, the table introduction and mode-specific upgrades
(docs/design/AI_MODES.md)."""

from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.content.builtin_persona import default_persona, host_persona
from chaos_blackjack.data import clone_profile, connect, default_balance
from chaos_blackjack.data.admin import export_seed, set_value
from chaos_blackjack.data.balance import load_balance
from chaos_blackjack.meta import MetaError, MetaService, build_run_config
from chaos_blackjack.meta.fake import install_fake
from chaos_blackjack.content.host_script import HOST_EVENTS, HostLine, host_script, host_scripts
from chaos_blackjack.modes import GameMode, get_mode, intro_lines, intro_script


@pytest.fixture()
def svc():
    s = install_fake(demo=False)
    yield s
    meta.use_service(None)


# ------------------------------------------------------------------- modes


def test_built_in_modes_have_hosts_and_pools() -> None:
    classic, poker_head = get_mode("normal"), get_mode("chaos")
    assert (classic.name, classic.host, classic.rules, classic.series) == ("Classic Table", "poker_head", (), "core")
    assert (poker_head.name, poker_head.host, poker_head.rules, poker_head.series) == (
        "Poker Head's Table", "poker_head", None, "poker_head")
    # Poker Head is the only bundled host; old or unknown hosts fall back to him.
    assert host_persona("poker_head") is default_persona() is host_persona(None) is host_persona("house")


def test_series_put_core_first_then_expansions() -> None:
    from chaos_blackjack.modes import get_series, series_list

    assert [(s.id, s.name, s.expansion) for s in series_list()] == [
        ("core", "Classic Table", False), ("poker_head", "Poker Head", True)]
    assert get_series("unknown_pack").expansion and get_series("unknown_pack").name == "Unknown Pack"


def test_apply_sets_mode_host_and_pools() -> None:
    base = RunConfig.from_balance(default_balance())
    mode = GameMode("trial", "Trial", "", host="poker_head", rules=("great_crash", "suit_power"),
                    items=("peek", "shield"), overrides={"enable_chaos": True, "target_money": 250})
    config = mode.apply(base)
    assert (config.mode, config.host, config.target_money) == ("trial", "poker_head", 250)
    assert config.rule_pool == ("great_crash", "suit_power")
    assert set(config.shop_prices) == {"peek", "shield"}
    assert {rid for rid, _, _ in config.chaos_stub} <= {"great_crash", "suit_power", ""}
    # Mode fields are presentation and pools: the run's numbers only change with the goal.
    assert RunConfig.from_dict(config.to_dict()) == config


def test_rule_pool_disables_every_other_rule() -> None:
    config = replace(RunConfig(use_llm=False, enable_chaos=True, seed=3), rule_pool=("great_crash",))
    controller = GameController(config)
    controller.place_bet(controller.view().bet_min)
    pipeline = controller.loop.pipeline
    assert "great_crash" not in pipeline.disabled_rules
    assert set(controller.registry.rule_ids()) - {"great_crash"} <= pipeline.disabled_rules


def test_runs_record_their_mode_and_old_configs_keep_poker_head() -> None:
    assert RunConfig().host is None and host_persona(RunConfig().host) is default_persona()
    old = {k: v for k, v in RunConfig().to_dict().items() if k not in ("mode", "host", "rule_pool")}
    assert RunConfig.from_dict(old).host is None


# ------------------------------------------------------------- introduction


def test_intro_is_a_random_greeting_then_the_goal_and_rules() -> None:
    import random

    base = RunConfig.from_balance(default_balance())
    classic = get_mode("normal")
    beats = intro_script(classic, classic.apply(base), random.Random(1))
    assert beats[:-1] in host_scripts("poker_head", "intro", mode="normal")  # his Classic-table lines
    assert "Reach 300 chips from 100" in beats[-1].text and "No rule changes" in beats[-1].text
    poker_head = get_mode("chaos")
    seen = {tuple(intro_lines(poker_head, poker_head.apply(base), random.Random(seed))[:-1]) for seed in range(30)}
    assert len(seen) > 1  # different greetings
    beats = intro_script(poker_head, poker_head.apply(base), random.Random(2))
    assert beats[-1].mood == "present_card" and "I may bend a rule" in beats[-1].text
    narrow = GameMode("x", "X", "", rules=("great_crash",), overrides={"enable_chaos": True})
    lines = intro_lines(narrow, narrow.apply(base))
    assert lines[-1].endswith("I may bend a rule before each hand: Great Crash.")


def test_line_libraries_cover_every_event_with_known_moods() -> None:
    expressions = set(default_persona().portraits)
    for mode in ("", "normal", "chaos"):
        for event in HOST_EVENTS:
            scripts = host_scripts("poker_head", event, mode=mode)
            assert len(scripts) >= 3, (mode, event)
            for script in scripts:
                assert script and all(isinstance(b, HostLine) and b.mood in expressions and b.text for b in script)
    # Classic has its own lines (he bends no rules there); Poker Head's table uses the default ones.
    assert host_scripts("poker_head", "intro", mode="normal") != host_scripts("poker_head", "intro")
    assert host_scripts("poker_head", "intro", mode="chaos") == host_scripts("poker_head", "intro")
    assert host_script(None, "victory") in host_scripts("poker_head", "victory")  # runs from before hosts
    assert host_script("nobody_yet", "intro") in host_scripts("poker_head", "intro")
    with pytest.raises(ValueError):
        host_script("poker_head", "lunch")


def test_table_intro_shows_for_new_runs_and_esc_skips_it(svc) -> None:
    pygame = pytest.importorskip("pygame")
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    app = App(GuiSettings(), run_config=RunConfig(use_llm=False))
    try:
        p = meta.create_player(1, "Intro")
        started = meta.start_run(p.id, "chaos", seed=1)
        app.scenes.reset("meta_table", started=started, player_id=p.id, intro=True)
        app.scenes.apply_pending()
        table = app.scenes.top
        assert table.intro_open() and table.intro.name == "Poker Head"
        first = table.intro.portrait
        assert first.startswith("default_poker_head_")
        bet = table.view.current_bet
        # While the host talks, keys go to the introduction, not the table.
        app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0))
        assert table.intro.index == 1 and table.view.phase == TablePhase.BETTING and table.view.current_bet == bet
        app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
        app.scenes.apply_pending()
        assert not table.intro_open() and app.scenes.top is table  # skipped, not abandoned
        app._render()  # noqa: SLF001
        # Continue (no intro flag), then Classic: Poker Head hosts it too.
        app.scenes.reset("meta_table", started=meta.resume_run(p.id) or started, player_id=p.id)
        app.scenes.apply_pending()
        assert app.scenes.top.intro is None
        meta.abandon_run(started.run_id)
        classic = meta.start_run(p.id, "normal", seed=2)
        app.scenes.reset("meta_table", started=classic, player_id=p.id, intro=True)
        app.scenes.apply_pending()
        table = app.scenes.top
        assert table.intro.name == "Poker Head" and table.chaos_panel.persona is default_persona()
        assert table.intro.lines[:-1] in [[b.text for b in s] for s in host_scripts("poker_head", "intro",
                                                                                    mode="normal")]
        app._render()  # noqa: SLF001
    finally:
        app.audio.close()
        pygame.quit()


# -------------------------------------------------------- mode-specific upgrades


def _profile_with_mode_upgrades(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_DB", str(tmp_path / "g.db"))
    conn = connect()
    clone_profile(conn, "default", "modes")
    set_value(conn, "modes", "upgrade.start_money.mode", "chaos")
    set_value(conn, "modes", "upgrade.start_peek.mode", "chaos")
    return conn


def test_mode_upgrades_apply_only_in_their_mode(tmp_path, monkeypatch) -> None:
    conn = _profile_with_mode_upgrades(tmp_path, monkeypatch)
    try:
        b = load_balance("modes", conn)
        assert {u.upgrade_id: u.mode for u in b.meta_upgrades}["start_money"] == "chaos"
        assert "'chaos'" in export_seed(conn, "modes")
        owned = {"start_money": 2, "start_peek": 1}
        chaos, applied = build_run_config(b, get_mode("chaos"), owned, ["start_peek"])
        assert chaos.start_money == b.start_money + 20 and applied == {"start_money": 2, "start_peek": 1}
        classic, applied = build_run_config(b, get_mode("normal"), owned)
        assert classic.start_money == b.start_money and applied == {}
        with pytest.raises(MetaError, match="only be brought to Poker Head's Table"):
            build_run_config(b, get_mode("normal"), owned, ["start_peek"])
        s = MetaService(conn)
        p = s.create_player(1, "M")
        offer = {o.upgrade_id: o for o in s.meta_shop(p.id, "modes")}["start_money"]
        assert offer.mode == "chaos"
        assert {o.upgrade_id: o for o in s.meta_shop(p.id)}["start_money"].mode is None  # default profile
    finally:
        conn.close()


def test_run_setup_lists_only_upgrades_of_the_selected_mode(svc) -> None:
    pygame = pytest.importorskip("pygame")
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    app = App(GuiSettings(), run_config=RunConfig(use_llm=False))
    try:
        p = meta.create_player(1, "Setup")
        svc.grant_tokens(p.id, 100)
        meta.buy_upgrade(p.id, "start_peek")
        meta.buy_upgrade(p.id, "start_shield")
        app.scenes.reset("run_setup", player_id=p.id)
        app.scenes.apply_pending()
        setup = app.scenes.top
        assert set(setup.item_rows) == {"start_peek", "start_shield"}
        # Pretend the shop marks Peek as a Poker Head consumable.
        setup.offers = [replace(o, mode="chaos") if o.upgrade_id == "start_peek" else o for o in setup.offers]
        setup.memory["mode"] = "chaos"
        setup.choose_mode("normal")
        assert set(setup.item_rows) == {"start_shield"}
        setup.choose_mode("chaos")
        assert set(setup.item_rows) == {"start_peek", "start_shield"}
        app._render()  # noqa: SLF001
    finally:
        app.audio.close()
        pygame.quit()


def test_host_speaks_when_the_run_ends_before_the_results(svc) -> None:
    pygame = pytest.importorskip("pygame")
    from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    app = App(GuiSettings(), run_config=RunConfig(use_llm=False))
    try:
        p = meta.create_player(1, "Outro")
        started = meta.start_run(p.id, "normal", seed=1)  # Classic: no rule can change the rigged hand
        app.scenes.reset("meta_table", started=started, player_id=p.id)
        app.scenes.apply_pending()
        table = app.scenes.top
        c = table.controller
        c.run.money = 300
        c.place_bet(150)
        c.state = GameState((Card(Rank("K"), "♠"), Card(Rank("Q"), "♠")), (Card(Rank("10"), "♥"), Card(Rank("8"), "♥")),
                            (Card(Rank("2"), "♣"),), GamePhase.PLAYER_TURN)
        c.stand()
        c.finish_dealer()
        table._after_command()  # noqa: SLF001
        assert table.view.phase == TablePhase.RUN_OVER
        for _ in range(40):
            app.scenes.update(0.1)
            app.scenes.apply_pending()
        assert app.scenes.top is table and table.outro is not None and table.intro_open()
        assert [b.text for b in table.outro.beats] in [[b.text for b in s] for s in host_scripts("poker_head", "victory", mode="normal")]
        app._render()  # noqa: SLF001
        app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
        app.scenes.update(0.1)
        app.scenes.apply_pending()
        assert type(app.scenes.top).__name__ == "RunResultScene"
    finally:
        app.audio.close()
        pygame.quit()


def test_shop_areas_then_series(svc, monkeypatch) -> None:
    pygame = pytest.importorskip("pygame")
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    real = meta.meta_shop
    # Pretend the profile ties Reroll Pass to the Poker Head mode.
    monkeypatch.setattr(meta, "meta_shop", lambda pid, profile=None: [
        replace(o, mode="chaos") if o.upgrade_id == "reroll_pass" else o for o in real(pid, profile)])
    app = App(GuiSettings(), run_config=RunConfig(use_llm=False))
    try:
        p = meta.create_player(1, "Shopper")
        app.scenes.reset("meta_shop", player_id=p.id)
        app.scenes.apply_pending()
        shop = app.scenes.top
        assert shop.title == "Shop" and list(shop.area_tabs) == ["upgrades", "cosmetics", "starter"]
        assert shop.area == "upgrades" and list(shop.series_tabs) == ["core", "poker_head"]
        assert "reroll_pass" not in {o.upgrade_id for o in shop.visible_offers}
        shop.pick_series("poker_head")
        assert [o.upgrade_id for o in shop.visible_offers] == ["reroll_pass"]
        # Starter items follow the tables that sell the item: Shield is only sold at Poker Head's.
        shop.pick_area("starter")
        assert shop.series == "poker_head" and [o.upgrade_id for o in shop.visible_offers] == ["start_shield"]
        shop.pick_series("core")
        assert "start_shield" not in {o.upgrade_id for o in shop.visible_offers}
        # Cosmetics follow their own series; achievement rewards are listed, locked.
        shop.pick_area("cosmetics")
        shop.pick_series("poker_head")
        offers = {o.cosmetic.id: o for o in shop.visible_offers}
        assert set(offers) == {"deck_poker_head", "table_poker_head"}
        assert not offers["deck_poker_head"].can_buy and "Poker Face" in offers["deck_poker_head"].unlock_hint
        assert app.session["shop_area"] == "cosmetics" and app.session["shop_series"] == "poker_head"
        app._render()  # noqa: SLF001
        monkeypatch.setattr(meta, "meta_shop", real)
        shop.pick_area("upgrades")
        assert list(shop.series_tabs) == ["core"]  # an empty expansion is hidden in an area
    finally:
        app.audio.close()
        pygame.quit()
