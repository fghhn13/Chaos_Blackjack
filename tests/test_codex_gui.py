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


def test_gallery_tabs_and_detail_back_preserve_category(app):
    gallery = open_scene(app)
    assert gallery.current == "rule" and len(gallery.tiles) == 7
    key(app, pygame.K_TAB)
    assert gallery.current == "mode"
    key(app, pygame.K_TAB)
    assert gallery.current == "item" and len(gallery.tiles) == 6
    rect, entry = gallery.tiles[0]
    click(app, rect.center)
    detail = app.scenes.top
    assert isinstance(detail, scenes.CodexDetailScene)
    assert detail.entry == entry and detail.demo.frames
    key(app, pygame.K_ESCAPE)
    assert app.scenes.top is gallery and gallery.current == "item"
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


def test_content_pack_gallery_paginates_without_hiding_entries(app, monkeypatch):
    monkeypatch.setattr(codex_registry, "_PROVIDERS", {k: list(v) for k, v in codex_registry._PROVIDERS.items()})
    entries = [CodexEntry("item", f"test_{i}", f"Extra {i}", "peek", "Plugin item.",
                          lambda cfg: "Details", None) for i in range(15)]
    register_codex_provider("item", lambda cfg: entries)
    scene = open_scene(app, kind="item")
    assert len(scene.entries) == 21 and len(scene.tiles) == 10
    assert not scene.previous.enabled and scene.next.enabled
    key(app, pygame.K_RIGHT)
    assert scene.page == 1 and len(scene.tiles) == 10
    key(app, pygame.K_RIGHT)
    assert scene.page == 2 and len(scene.tiles) == 1 and not scene.next.enabled
    key(app, pygame.K_LEFT)
    assert scene.page == 1
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
