"""Touch gestures must scroll the original GUI without clicking list rows."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.scene import Scene
from chaos_blackjack.gui.settings import GuiSettings
from chaos_blackjack.gui.widgets import Button, ScrollColumn, WidgetGroup
from chaos_blackjack.gui.touch import TOUCH_SCROLL


@pytest.fixture
def app(tmp_path):
    value = App(GuiSettings(window_size=(640, 360), asset_dirs=(tmp_path,)))
    yield value
    value.audio.close()
    pygame.quit()


def finger(app, kind, x, y, finger_id=1):
    # Test callers use window pixels, as a browser does, including letterboxing.
    w, h = app.window.get_size()
    app._dispatch(pygame.event.Event(kind, touch_id=1, finger_id=finger_id,
                                     x=x / w, y=y / h, dx=0, dy=0))


def column_scene(app):
    clicks = []
    column = ScrollColumn((100, 100, 500, 300), gap=0)
    for i in range(10):
        column.add(Button(app.assets, (0, 0, 0, 100), str(i), lambda i=i: clicks.append(i)))
    scene = Scene(app)
    scene.ui = WidgetGroup(column)
    scene.handle_event = scene.ui.handle_event
    app.scenes.stack = [scene]
    return column, clicks


def test_tap_occurs_once_with_sdl_touch_mouse_duplicates(app):
    column, clicks = column_scene(app)
    finger(app, pygame.FINGERDOWN, 100, 75)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        app._dispatch(pygame.event.Event(kind, pos=(100, 75), button=1, touch=True))
    finger(app, pygame.FINGERUP, 103, 77)
    assert clicks == [0]
    assert column.scroll == 0


def test_swipe_scrolls_clamps_and_never_selects_a_row(app):
    column, clicks = column_scene(app)
    finger(app, pygame.FINGERDOWN, 100, 180)
    finger(app, pygame.FINGERMOTION, 100, 120)
    finger(app, pygame.FINGERUP, 100, 80)
    assert column.scroll == 200
    assert clicks == []
    finger(app, pygame.FINGERDOWN, 100, 180)
    finger(app, pygame.FINGERMOTION, 100, -500)
    finger(app, pygame.FINGERUP, 100, -500)
    assert column.scroll == column.max_scroll
    finger(app, pygame.FINGERDOWN, 100, 80)
    finger(app, pygame.FINGERUP, 100, 500)
    assert column.scroll == 0
    assert clicks == []


def test_swipe_outside_a_column_cannot_scroll_it(app):
    column, clicks = column_scene(app)
    finger(app, pygame.FINGERDOWN, 400, 180)
    finger(app, pygame.FINGERUP, 400, 80)
    assert column.scroll == 0 and clicks == []


def test_letterboxed_window_uses_logical_scroll_distance(app):
    app.window = pygame.display.set_mode((640, 500))
    app._update_viewport()
    column, clicks = column_scene(app)
    finger(app, pygame.FINGERDOWN, 100, 250)
    finger(app, pygame.FINGERUP, 100, 200)
    assert column.scroll == 100 and clicks == []


def test_multitouch_cancels_the_tap_and_the_next_single_tap_works(app):
    _, clicks = column_scene(app)
    finger(app, pygame.FINGERDOWN, 100, 75)
    finger(app, pygame.FINGERDOWN, 120, 75, finger_id=2)
    finger(app, pygame.FINGERUP, 120, 75, finger_id=2)
    finger(app, pygame.FINGERUP, 100, 75)
    assert clicks == []
    finger(app, pygame.FINGERDOWN, 100, 75)
    finger(app, pygame.FINGERUP, 100, 75)
    assert clicks == [0]


def test_changed_scene_or_focus_loss_does_not_receive_a_stale_tap(app):
    _, clicks = column_scene(app)
    finger(app, pygame.FINGERDOWN, 100, 75)
    new = Scene(app)
    new.handle_event = app.scenes.top.handle_event
    app.scenes.stack = [new]
    finger(app, pygame.FINGERUP, 100, 75)
    finger(app, pygame.FINGERDOWN, 100, 75)
    app._dispatch(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    finger(app, pygame.FINGERUP, 100, 75)
    assert clicks == []


def test_desktop_mouse_clicks_are_unchanged(app):
    _, clicks = column_scene(app)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        app._dispatch(pygame.event.Event(kind, pos=(100, 75), button=1, touch=False))
    assert clicks == [0]


def test_collection_swipe_does_not_open_the_tile_under_the_finger(app, monkeypatch):
    from chaos_blackjack.codex import CodexEntry, register_codex_provider
    from chaos_blackjack.codex import registry
    from chaos_blackjack.gui.scenes.codex import CodexScene
    monkeypatch.setattr(registry, "_PROVIDERS", {key: list(value) for key, value in registry._PROVIDERS.items()})
    entries = [CodexEntry("item", f"touch-{i}", f"Extra {i}", "peek", "Plugin item",
                          lambda cfg: "Details", None) for i in range(15)]
    register_codex_provider("item", lambda cfg: entries)
    scene = CodexScene(app)
    scene.on_enter(section="core")
    assert scene.max_scroll > 0
    app.scenes.stack = [scene]
    rect, _ = scene.visible_tiles()[0]
    x, y = rect.centerx / 2, rect.centery / 2
    finger(app, pygame.FINGERDOWN, x, y)
    finger(app, pygame.FINGERMOTION, x, y - 80)
    finger(app, pygame.FINGERUP, x, y - 80)
    app.scenes.apply_pending()
    assert app.scenes.top is scene
    assert scene.scroll == min(160, scene.max_scroll)


def test_long_collection_detail_swipes_only_in_the_text_panel(app):
    from chaos_blackjack.codex import CodexEntry
    from chaos_blackjack.gui.scenes.codex import CodexDetailScene, TEXT_RECT
    scene = CodexDetailScene(app)
    scene.on_enter(entry=CodexEntry("item", "touch-long", "Long explanation", "peek", "Custom entry",
                                    lambda cfg: "Explanation with enough words to overflow. " * 240, None))
    app.scenes.stack = [scene]
    x, y = TEXT_RECT.centerx / 2, TEXT_RECT.centery / 2
    finger(app, pygame.FINGERDOWN, x, y)
    finger(app, pygame.FINGERUP, x, y - 50)
    assert scene.text_offset == 100
    scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=(200, 300), dy=100))
    assert scene.text_offset == 100


def test_history_swipe_accumulates_small_motion_and_clamps(app):
    from chaos_blackjack.gui.scenes.history import HistoryScene, DETAIL_RECT
    scene = HistoryScene(app)
    scene.setup()
    scene.detail_scroll = 0
    scene.detail_lines = lambda: ["Visible summary"] * 40
    scene.ui = WidgetGroup()
    height = app.assets.font(16).get_linesize()
    for _ in range(height):
        scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=DETAIL_RECT.center, dy=1))
    assert scene.detail_scroll == 1
    scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=DETAIL_RECT.center, dy=10000))
    assert scene.detail_scroll == 40 - 222 // height
    scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=DETAIL_RECT.center, dy=-10000))
    assert scene.detail_scroll == 0


def test_new_table_shop_swipes_without_buying_a_product(app):
    from dataclasses import replace
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.data.balance import default_balance
    from chaos_blackjack.gui.scenes.shop import ShopScene
    from chaos_blackjack.modes import get_mode

    config = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=7, use_llm=False))
    controller = GameController(replace(config, mode_settings={**config.mode_settings, "chaos.unlock_all": 1}))
    controller.choose(controller.view().choice.options[0].id)
    scene = ShopScene(app)
    scene.on_enter(controller=controller)
    app.scenes.stack = [scene]
    assert scene.grid and scene.content_h > scene.area.h
    before = controller.view()
    scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=(0, 0), dy=100))
    assert scene.scroll == 0
    x, y = scene.area.centerx / 2, scene.area.centery / 2
    finger(app, pygame.FINGERDOWN, x, y)
    finger(app, pygame.FINGERUP, x, y - 80)
    assert scene.scroll == 160 and controller.view() == before
    scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=scene.area.center, dy=100000))
    assert scene.scroll == scene.content_h - scene.area.h
    scene.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=scene.area.center, dy=-100000))
    assert scene.scroll == 0 and controller.view() == before
