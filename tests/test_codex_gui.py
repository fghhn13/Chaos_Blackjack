"""Gallery navigation, frame-only playback and profile-sensitive details."""

import os
from dataclasses import replace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex import CodexEntry, codex_entries, register_codex_provider
from chaos_blackjack.codex import registry as codex_registry
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.assets.manifest import MANIFEST
from chaos_blackjack.gui.scenes import codex as scenes
from chaos_blackjack.gui.settings import GuiSettings


@pytest.fixture
def app(tmp_path):
    instance = App(GuiSettings(asset_dirs=(tmp_path,), audio_muted=True))
    yield instance
    instance.audio.close()
    pygame.quit()


def open_scene(app, name="codex", **params):
    app.scenes.push(name, **params)
    app.scenes.apply_pending()
    return app.scenes.top


def key(app, key):
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0}))
    app.scenes.apply_pending()


def click(app, pos):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        app.scenes.handle_event(pygame.event.Event(kind, {"button": 1, "pos": pos}))
    app.scenes.apply_pending()


def test_gallery_core_series_then_expansions_and_detail_back_preserve_section(app):
    gallery = open_scene(app)
    assert [s.label for s in gallery.sections] == ["Classic Table", "Poker Head", "J-54"]
    assert gallery.current == "core" and gallery.expansions_label_x is not None
    assert {e.kind for _, e in gallery.tiles} == {"mode", "item"} and not gallery.about.visible
    key(app, pygame.K_TAB)
    assert gallery.current == "poker_head" and gallery.about.visible
    assert gallery.section.profile and gallery.section.quote.startswith("Old friends")
    assert len([e for _, e in gallery.tiles if e.kind == "rule"]) == 7
    gallery.draw(app.canvas)
    rect, entry = gallery.tiles[0]
    click(app, rect.center)
    detail = app.scenes.top
    assert isinstance(detail, scenes.CodexDetailScene)
    assert detail.entry == entry and detail.demo.frames
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is gallery and gallery.current == "poker_head"
    click(app, gallery.about.rect.center)
    assert app.scenes.top.entry.kind == "mode" and app.scenes.top.entry.id == "chaos"
    key(app, pygame.K_ESCAPE)
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is None


def test_playback_pause_seek_replay_and_end(app, monkeypatch):
    entry = next(e for e in codex_entries("rule") if e.id == "great_crash")
    scene = open_scene(app, "codex_detail", entry=entry)
    monkeypatch.setattr(scenes, "run_demo", lambda *_: pytest.fail("Playback reran the controller"))
    for _ in range(120):
        scene.update(1 / 60)
    assert scene.demo.index == 1
    key(app, pygame.K_SPACE)
    assert not scene.demo.playing
    scene.update(10)
    assert scene.demo.index == 1
    key(app, pygame.K_RIGHT)
    assert scene.demo.index == 2 and not scene.demo.fx.busy
    key(app, pygame.K_LEFT)
    assert scene.demo.index == 1
    key(app, pygame.K_r)
    assert scene.demo.index == 0 and scene.demo.playing
    for _ in range(1200):
        scene.update(1 / 60)
    assert scene.demo.index == len(scene.demo.frames) - 1
    assert not scene.demo.playing and not scene.next.enabled
    key(app, pygame.K_SPACE)
    assert scene.demo.index == 0 and scene.demo.playing


@pytest.mark.parametrize("kind", ["mode", "ai"])
def test_entries_without_demo_show_icon_and_text(app, kind):
    scene = open_scene(app, "codex_detail", entry=codex_entries(kind)[0])
    assert not scene.demo.frames
    assert not scene.play.enabled and not scene.replay.enabled
    scene.draw(app.canvas)
    key(app, pygame.K_SPACE)
    assert not scene.demo.playing


def test_detail_config_reaches_text_and_replay(app):
    cfg = replace(RunConfig(), chaos_rule_params={"great_crash": {"ten_value": 8}}, min_bet=4)
    entry = next(e for e in codex_entries("rule") if e.id == "great_crash")
    scene = open_scene(app, "codex_detail", entry=entry, config=cfg)
    assert "value 8" in scene.detail
    assert scene.demo.frames[1].view.player_total == 16
    assert scene.demo.frames[0].view.current_bet == 4
    scene.draw(app.canvas)


def test_long_plugin_text_scrolls_and_stays_clipped(app):
    entry = CodexEntry("item", "long", "A long description", "peek", "A custom entry.",
                       lambda cfg: "Paragraph. " * 500, None)
    scene = open_scene(app, "codex_detail", entry=entry)
    key(app, pygame.K_PAGEDOWN)
    assert scene.text_offset > 0
    for _ in range(200):
        scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1}))
    last = scene.text_offset
    scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -10}))
    assert scene.text_offset == last
    scene.draw(app.canvas)
    assert app.canvas.get_clip() == app.canvas.get_rect()
    for _ in range(200):
        key(app, pygame.K_PAGEUP)
    assert scene.text_offset == 0


def test_long_sections_scroll_without_hiding_entries(app, monkeypatch):
    monkeypatch.setattr(codex_registry, "_PROVIDERS", {k: list(v) for k, v in codex_registry._PROVIDERS.items()})
    entries = [CodexEntry("item", f"test_{i}", f"Extra {i}", "peek", "Plugin item.",
                          lambda cfg: "Details", None) for i in range(15)]
    register_codex_provider("item", lambda cfg: entries)
    scene = open_scene(app, section="core")
    assert len(scene.entries) == 21 and len(scene.tiles) == 21  # Classic + 5 shared items + 15 never sold
    assert scene.max_scroll > 0 and len(scene.visible_tiles()) < 21
    first = scene.tiles[0][0].y
    key(app, pygame.K_PAGEDOWN)
    assert scene.scroll > 0 and scene.tiles[0][0].y < first
    for _ in range(10):
        scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"y": -1}))
    assert scene.scroll == scene.max_scroll and scene.tiles[-1] in scene.visible_tiles()
    scene.draw(app.canvas)


def test_invalid_demo_has_readable_text_fallback(app, monkeypatch):
    monkeypatch.setattr(scenes, "run_demo", lambda *_: (_ for _ in ()).throw(ValueError("Invalid profile")))
    scene = open_scene(app, "codex_detail", entry=codex_entries("item")[0])
    assert scene.demo_error and not scene.demo.frames
    assert not scene.play.enabled
    scene.draw(app.canvas)


def test_all_builtin_details_render_all_frames(app):
    for entry in codex_entries():
        scene = scenes.CodexDetailScene(app)
        scene.on_enter(entry=entry)
        if scene.demo.frames:
            for index in range(len(scene.demo.frames)):
                scene.demo.step(index - scene.demo.index)
                scene.draw(app.canvas)
        else:
            scene.draw(app.canvas)


def test_mode_icon_specs_have_working_fallbacks(app):
    for mode in codex_entries("mode"):
        assert mode.icon in MANIFEST
        assert MANIFEST[mode.icon].category == "mode"
        assert app.assets.image(mode.icon).get_size() == (256, 256)


def test_integrated_content_packs_supply_item_and_ai_entries():
    cfg = RunConfig(content_packs=("example",), ai_id="example_dealer", use_llm=False,
                    shop_prices={"example_trim": 27})
    items = {e.id: e for e in codex_entries("item", cfg)}
    ais = {e.id: e for e in codex_entries("ai", cfg)}
    assert "example_trim" in items and "Discard" in items["example_trim"].summary
    assert "27 chips" in items["example_trim"].detail(cfg)
    assert "example_dealer" in ais and ais["example_dealer"].detail(cfg)
    assert "example_trim" not in {e.id for e in codex_entries("item")}
    assert "example_dealer" not in {e.id for e in codex_entries("ai")}


def test_sections_place_every_entry_by_series():
    from chaos_blackjack.codex import codex_sections

    sections = {s.id: s for s in codex_sections(RunConfig())}
    assert list(sections) == ["core", "poker_head", "j54"]
    core, poker_head = sections["core"], sections["poker_head"]
    assert not core.expansion and poker_head.expansion
    assert [e.id for e in {g.id: g for g in core.groups}["tables"].entries] == ["normal"]
    assert poker_head.host == "poker_head" and poker_head.portrait.startswith("default_poker_head_")
    assert poker_head.mode.id == "chaos" and poker_head.quote
    groups = {g.id: g for g in poker_head.groups}
    assert {e.id for e in groups["rules"].entries} == {e.id for e in codex_entries("rule")
                                                       if not e.id.startswith("j54_")}
    assert [e.id for e in groups["items"].entries] == ["shield"]  # Classic never sells Shield
    assert "shield" not in {e.id for e in core.entries} and "rules" not in {g.id for g in core.groups}
    # Nothing is left out: every rule, item and mode appears somewhere.
    placed = {(e.kind, e.id) for s in sections.values() for e in s.entries}
    placed |= {("mode", s.mode.id) for s in sections.values() if s.mode is not None}
    for kind in ("rule", "item", "mode"):
        assert {(kind, e.id) for e in codex_entries(kind)} <= placed, kind


def test_sections_follow_mode_pools(monkeypatch):
    from chaos_blackjack import modes as modes_module
    from chaos_blackjack.codex import codex_sections
    from chaos_blackjack.modes import GameMode, register_mode

    monkeypatch.setattr(modes_module, "_MODES", dict(modes_module._MODES))
    register_mode(GameMode("trial", "Trial", "A narrow table.", icon="mode_chaos", order=5, series="trial_pack",
                           overrides={"enable_chaos": True}, rules=("great_crash",), items=("peek", "fate_oracle")))
    sections = {s.id: s for s in codex_sections(RunConfig())}
    assert list(sections) == ["core", "poker_head", "j54", "trial_pack"]  # a new expansion gets its own tab
    trial = {g.id: g for g in sections["trial_pack"].groups}
    assert [e.id for e in trial["rules"].entries] == ["great_crash"]
    # Peek and Fate Oracle are sold at the trial table too, so they stay in the core; Swap is
    # still sold at the core Classic table, so it stays there as well.
    core_items = {e.id for e in sections["core"].entries if e.kind == "item"}
    assert {"peek", "fate_oracle", "swap"} <= core_items and "shield" not in core_items
