"""Parts, widgets, layouts, the run log and the run panel."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from dataclasses import replace

import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.layout import DEFAULT_LAYOUT, Layout, PanelTab, layout_for, split_entry
from chaos_blackjack.app.parts import PartContext, build_part, register_part
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.app.widgets import Act, Progress, Slots
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.modes import GameMode, get_mode


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


def _controller(mode: str = "chaos", seed: int = 3) -> GameController:
    c = GameController(get_mode(mode).apply(RunConfig.from_balance(default_balance(), seed=seed)),
                       save_fn=lambda d, n: n)
    c.drain_notices()
    if c.view().choice is not None:  # Poker Head's opening invitation
        c.choose(c.view().choice.options[0].id)
    return c


def _play_round(c: GameController) -> None:
    c.place_bet(10)
    if c.phase == TablePhase.CHAOS:
        c.resolve_chaos()
    if c.phase == TablePhase.PLAYER_TURN:
        c.stand()
    c.finish_dealer()


# ---------------------------------------------------------------- layouts


def test_modes_choose_their_layout() -> None:
    assert layout_for("normal") is DEFAULT_LAYOUT and layout_for("unknown") is DEFAULT_LAYOUT
    j54 = layout_for("j54")
    assert "j54.badges" in j54.right and j54.tab("deck") is not None and j54.tab("contracts") is not None
    assert [t.id for t in DEFAULT_LAYOUT.panel] == ["bag", "rules", "log", "run"]
    assert split_entry("j54.deck:compact", "full") == ("j54.deck", "compact")
    assert split_entry("core.log", "full") == ("core.log", "full")


def test_parts_only_show_where_they_apply() -> None:
    plain, j54 = _controller(), _controller("j54")
    assert build_part("j54.deck", PartContext(plain, plain.view())) == ()
    assert build_part("no.such.part", PartContext(plain, plain.view())) == ()
    kinds = [w.kind for w in build_part("j54.deck", PartContext(j54, j54.view()), "full")]
    assert kinds == ["bars", "list", "rows"]
    compact = build_part("j54.deck", PartContext(j54, j54.view()), "compact")[0]
    assert compact.compact and compact.act == Act("gui:panel", "deck") and len(compact.bars) == 13


def test_a_new_mechanic_is_a_part_plus_a_layout() -> None:
    """A table unlike any other only registers parts and names them in a layout."""
    register_part("test.meter", lambda ctx, variant: (Progress("Curse", 3, 10, tone="bad"),))
    layout = Layout(left=("core.host",), right=("test.meter",),
                    panel=(PanelTab("curse", "Curse", ("test.meter", "core.log")),))
    c = _controller()
    widgets = build_part("test.meter", PartContext(c, c.view()))
    assert widgets[0].kind == "progress" and layout.tab("curse").parts[0] == "test.meter"
    assert GameMode("test_curse", "Curse", "", layout=layout).layout is layout


def test_item_slots_carry_use_actions_and_hotkeys() -> None:
    c = _controller()
    c.run.items = ("peek", "peek", "swap")
    slots = build_part("core.items", PartContext(c, c.view()), "compact")[0]
    assert isinstance(slots, Slots)
    assert [(s.icon, s.count, s.hotkey) for s in slots.slots] == [("peek", 2, "1"), ("swap", 1, "2")]
    assert all(s.act.id == "use_item" and not s.act.enabled for s in slots.slots)  # not your turn yet


def test_rules_part_lists_the_dealers_pool() -> None:
    c = _controller("j54")
    full = build_part("core.rules", PartContext(c, c.view()), "full")
    names = {e.title for e in full[1].entries}
    assert {"Burn Protocol", "Layered Sort", "Data Backflow"} <= names
    assert all(not e.text.startswith(e.title) for e in full[1].entries)
    off = _controller("normal")
    assert len(build_part("core.rules", PartContext(off, off.view()), "full")) == 1


# ------------------------------------------------------------------ perform


def test_perform_uses_items_and_rejects_unknown_actions() -> None:
    c = _controller("normal")
    c.run.items = ("peek",)

    def fixed(seed=None, *, inventory_override=None, cards=None):
        return GameState((_c("10"), _c("6")), (_c("9"), _c("7")), (_c("5"), _c("K")), GamePhase.PLAYER_TURN,
                         inventory=inventory_override or ())

    c.loop.new_round = fixed
    c.place_bet(10)
    result = c.perform("use_item", "peek")
    assert result.ok and c.run.items == ()
    with pytest.raises(ActionError):
        c.perform("j54.challenge", "")


# ------------------------------------------------------------------ run log


def test_run_log_records_categories_and_stats() -> None:
    c = _controller("j54")
    for _ in range(3):
        _play_round(c)
        if c.phase == TablePhase.ROUND_OVER:
            c.next_round()
    categories = {e.category for e in c.run_log.entries}
    assert {"hand", "money", "deck"} <= categories
    s = c.run_log.stats
    assert s["hands"] == 3 and s["wins"] + s["losses"] + s["pushes"] == 3
    assert {e.round for e in c.run_log.entries} >= {1, 2, 3}


def test_run_log_is_capped_but_keeps_counters() -> None:
    from chaos_blackjack.app.notices import Notice, NoticeKind
    from chaos_blackjack.app.run_log import RunLog

    log = RunLog(limit=5)
    for i in range(20):
        log.record(i, Notice(NoticeKind.TABLE_EVENT, f"event {i}"))
    assert len(log.entries) == 5 and log.entries[0].text == "event 15"


def test_run_log_is_saved_and_restored() -> None:
    from chaos_blackjack.core.run_state import RunSaveData

    c = _controller("j54")
    _play_round(c)
    c.next_round()
    data = c.save("x")
    assert data.log == c.run_log.to_dict()
    loaded = GameController.from_save(RunSaveData.from_dict(data.to_dict()), save_fn=lambda d, n: n)
    assert loaded.run_log.to_dict() == c.run_log.to_dict()


# --------------------------------------------------------------------- GUI


pygame = pytest.importorskip("pygame")


@pytest.fixture()
def app(tmp_path):
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    a = App(GuiSettings(asset_dirs=(tmp_path,)))
    yield a
    pygame.quit()


def _open(app, controller):
    app.scenes.reset("table", controller=controller)
    app.scenes.apply_pending()
    app._render()  # noqa: SLF001
    return app.scenes.top


def _key(app, key):
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0, "unicode": ""}))
    app.scenes.apply_pending()


def test_table_builds_its_columns_from_the_layout(app) -> None:
    from chaos_blackjack.gui.components.side_column import DataBlock

    t = _open(app, _controller("j54"))
    right = [b.part for b in t.right.visible if isinstance(b, DataBlock)]
    assert right == ["j54.deck", "j54.badges", "core.items"]
    plain = _open(app, _controller("normal"))
    assert [b.part for b in plain.right.visible if isinstance(b, DataBlock)] == ["core.items"]
    assert plain.deck_rect.size == t.deck_rect.size


def test_panel_opens_on_keys_and_switches_tabs(app) -> None:
    t = _open(app, _controller("j54"))
    _key(app, pygame.K_TAB)
    panel = app.scenes.top
    assert panel is not t and panel.tab.id == "bag"
    _key(app, pygame.K_RIGHT)
    assert panel.tab.id == "deck"
    _key(app, pygame.K_l)
    assert panel.tab.id == "log"
    app._render()  # noqa: SLF001
    _key(app, pygame.K_TAB)
    assert app.scenes.top is t
    _key(app, pygame.K_l)
    assert app.scenes.top.tab.id == "log"


def test_clicking_the_deck_opens_the_deck_tab(app) -> None:
    t = _open(app, _controller("j54"))
    pos = t.deck_rect.center
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": 1}))
    app.scenes.apply_pending()
    assert app.scenes.top.tab.id == "deck"
    plain = _open(app, _controller("chaos"))  # no deck tab: the shoe is not a button
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": plain.deck_rect.center, "button": 1}))
    app.scenes.apply_pending()
    assert app.scenes.top is plain


def test_bag_tab_uses_items_through_actions(app) -> None:
    c = _controller("normal")
    c.run.items = ("peek",)

    def fixed(seed=None, *, inventory_override=None, cards=None):
        return GameState((_c("10"), _c("6")), (_c("9"), _c("7")), (_c("5"), _c("K")), GamePhase.PLAYER_TURN,
                         inventory=inventory_override or ())

    c.loop.new_round = fixed
    c.place_bet(10)
    t = _open(app, c)
    _key(app, pygame.K_i)
    panel = app.scenes.top
    app._render()  # noqa: SLF001
    hit = next(h for h in panel.view.hits if h.act is not None and h.act.id == "use_item")
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": hit.rect.center, "button": 1}))
    assert c.run.items == () and "Next card" in panel.message[0]
    assert not t.view.items  # the table refreshed through on_change


def test_log_filter_and_scroll(app) -> None:
    c = _controller("j54")
    for _ in range(4):
        _play_round(c)
        if c.phase == TablePhase.ROUND_OVER:
            c.next_round()
    _open(app, c)
    _key(app, pygame.K_l)
    panel = app.scenes.top
    app._render()  # noqa: SLF001
    chip = next(h for h in panel.view.hits if h.act is not None and h.act.arg == "deck")
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": chip.rect.center, "button": 1}))
    assert panel.state["log_filter"] == "deck"
    app._render()  # noqa: SLF001
    panel.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, {"x": 0, "y": -3}))
    assert panel.scroll >= 0


def test_browser_frame_and_swipes_work_with_the_widget_panel(app, monkeypatch) -> None:
    import json
    from types import SimpleNamespace
    from chaos_blackjack.gui.browser import BrowserStore
    from chaos_blackjack.gui.touch import TOUCH_SCROLL

    c = _controller("j54")
    _open(app, c)
    _key(app, pygame.K_TAB)
    panel = app.scenes.top
    register_part("test.touch_panel", lambda ctx, variant: (Progress("Visible meter", 1, 2),) * 40)
    panel.layout = Layout(left=(), right=(), panel=(PanelTab("long", "Long", ("test.touch_panel",)),))
    panel.tabs = panel.layout.panel
    panel.index = 0
    panel.tab_buttons = panel.tab_buttons[:1]
    panel._build()
    app._render()
    assert panel.view.measure() > panel.content.h
    panel.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=(0, 0), dy=100))
    assert panel.scroll == 0
    panel.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=panel.content.center, dy=100000))
    assert panel.scroll == panel.view.measure() - panel.content.h
    window = SimpleNamespace(chaosInitialSave="", chaosTouchInput=False)
    bridge = BrowserStore(window)
    monkeypatch.setattr(bridge, "flush", lambda: None)
    bridge.frame(app)  # WidgetView has no GameView fields; this used to crash.
    state = json.loads(window.chaosState)
    assert state["scene"] == "RunPanelScene" and state["phase"] == c.view().phase.value
    assert state["scroll_regions"][0]["max"] == panel.scroll
    panel.handle_event(pygame.event.Event(TOUCH_SCROLL, pos=panel.content.center, dy=-100000))
    assert panel.scroll == 0


def test_columns_hide_what_does_not_fit(app) -> None:
    from chaos_blackjack.gui.components.side_column import SideColumn

    register_part("test.tall", lambda ctx, variant: (Progress("A", 1, 2),) * 30)
    t = _open(app, _controller("chaos"))
    col = SideColumn(app.assets, t.right.rect, ("core.deck_pile", "test.tall", "core.buttons"),
                     {"core.deck_pile": t.deck_block, "core.buttons": t.buttons_block}, lambda act: None)
    col.sync(t.view, PartContext(t.controller, t.view))
    assert col.hidden == 1
    surface = pygame.Surface((1280, 720))
    col.draw(surface)
