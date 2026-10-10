"""GUI framework — runs headless via SDL's dummy video driver."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.gui.app import App  # noqa: E402
from chaos_blackjack.gui.assets import MANIFEST, AssetManager  # noqa: E402
from chaos_blackjack.gui.scene import Scene, SceneManager  # noqa: E402
from chaos_blackjack.gui.settings import GuiSettings  # noqa: E402
from chaos_blackjack.registry import get_registry  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    a = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes  # noqa: F401

    yield a
    pygame.quit()


def _click(app: App, pos) -> None:
    for t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        app.scenes.handle_event(pygame.event.Event(t, {"pos": pos, "button": 1}))
    app.scenes.apply_pending()


def test_manifest_covers_registered_items_and_rules() -> None:
    from chaos_blackjack import auto_load_plugins

    auto_load_plugins()
    reg = get_registry()
    for name in reg._items:  # noqa: SLF001
        assert name in MANIFEST, f"item {name} has no asset spec"
    for name in reg._chaos_rules:  # noqa: SLF001
        assert name in MANIFEST, f"rule {name} has no asset spec"


def test_placeholders_render_at_spec_size(app: App) -> None:
    for spec in MANIFEST.values():
        assert app.assets.source(spec.id) == "placeholder"
        assert app.assets.image(spec.id).get_size() == spec.size


def test_file_overrides_placeholder_and_scaling(tmp_path, app: App) -> None:
    sub = tmp_path / "icons"
    sub.mkdir()
    surf = pygame.Surface((64, 32))
    surf.fill((255, 0, 0))
    pygame.image.save(surf, str(sub / "peek.png"))
    app.assets.refresh()
    assert app.assets.source("peek") == "file"
    assert app.assets.image("peek").get_size() == (64, 32)
    assert app.assets.image("peek", (16, 16)).get_size() == (16, 16)
    assert app.assets.image_fit("peek", (100, 100)).get_size() == (100, 50)


def test_unknown_asset_is_missing_checker(tmp_path) -> None:
    pygame.init()
    m = AssetManager([tmp_path])
    assert m.source("nope") == "missing"
    assert m.image("nope").get_size() == (128, 128)


def test_scene_manager_stack_ops() -> None:
    log: list[str] = []

    class S(Scene):
        def on_enter(self, tag="", **_):
            self.tag = tag
            log.append(f"enter {tag}")

        def on_exit(self):
            log.append(f"exit {self.tag}")

        def on_resume(self, result=None):
            log.append(f"resume {self.tag} {result}")

    mgr = SceneManager(app=None, registry={"s": S})  # type: ignore[arg-type]
    mgr.push("s", tag="a")
    mgr.push("s", tag="b")
    mgr.apply_pending()
    mgr.pop(result=42)
    mgr.replace("s", tag="c")
    mgr.apply_pending()
    assert [s.tag for s in mgr.stack] == ["c"]
    assert log == ["enter a", "enter b", "exit b", "resume a 42", "exit a", "enter c"]
    with pytest.raises(KeyError):
        mgr.push("missing")
        mgr.apply_pending()


@pytest.mark.parametrize("scene", ["menu", "gallery", "table", "ending"])
def test_each_scene_runs_frames(app: App, scene: str) -> None:
    app.run(scene, max_frames=3)


def test_menu_new_game_opens_table_with_chaos_pref(app: App) -> None:
    app.scenes.reset("menu")
    app.scenes.apply_pending()
    menu = app.scenes.top
    chaos_toggle = next(w for w in menu.ui.widgets if getattr(w, "label", None) and callable(w.label))
    _click(app, chaos_toggle.rect.center)
    assert app.prefs.enable_chaos is True
    new_game = next(w for w in menu.ui.widgets if getattr(w, "text", "") == "New Game")
    _click(app, new_game.rect.center)
    table = app.scenes.top
    assert type(table).__name__ == "TableScene"
    assert table.controller.config.enable_chaos is True


def test_gallery_preview_overlay_opens_and_closes(app: App) -> None:
    app.scenes.reset("gallery")
    app.scenes.apply_pending()
    rect, asset_id = app.scenes.top.tiles[0]
    _click(app, rect.center)
    assert type(app.scenes.top).__name__ == "AssetPreviewScene"
    assert app.scenes.top.asset_id == asset_id
    _click(app, (10, 10))
    assert type(app.scenes.top).__name__ == "GalleryScene"


def test_window_scaling_maps_mouse_to_canvas(app: App) -> None:
    app._viewport = pygame.Rect(100, 0, 2560, 1440)  # noqa: SLF001
    assert app.to_canvas((100, 0)) == (0, 0)
    assert app.to_canvas((100 + 2560, 1440)) == (1280, 720)
