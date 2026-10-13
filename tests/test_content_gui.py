"""Loaded pack items can be used through the generic inventory overlay."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.settings import GuiSettings


def test_custom_item_inventory_keyboard_use(tmp_path):
    app = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes

    try:
        controller = GameController(RunConfig(content_packs=("example",), use_llm=False))
        controller.state = GameState(
            player_hand=tuple(Card(Rank(r)) for r in ("5", "6", "4")),
            dealer_hand=(Card(Rank("9")), Card(Rank("7"))),
            deck=(Card(Rank("2")),), inventory=("example_trim",), phase=GamePhase.PLAYER_TURN,
        )
        controller.phase = TablePhase.PLAYER_TURN
        app.scenes.reset("table", controller=controller)
        app.scenes.apply_pending()
        table = app.scenes.top
        # I opens the run panel on the bag, which describes pack items too.
        app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i}))
        app.scenes.apply_pending()
        panel = app.scenes.top
        assert panel.tab.id == "bag"
        assert panel.view.widgets[0].entries[0].text.startswith("Discard")
        app._render()
        app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
        app.scenes.apply_pending()
        # 1 uses the first item on your turn.
        app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_1}))
        app.scenes.apply_pending()
        assert app.scenes.top is table
        assert len(controller.state.player_hand) == 2
        assert controller.state.inventory == ()
        assert not table.view.items
        app._render()
    finally:
        pygame.quit()


def test_custom_item_panel_tooltip_and_mouse_use(tmp_path, monkeypatch):
    """The redesigned sidebar consumes content-pack help and the same item runtime."""
    from chaos_blackjack.gui.components import widget_view

    app = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes

    try:
        controller = GameController(RunConfig(content_packs=("example",), use_llm=False))
        controller.state = GameState(
            player_hand=tuple(Card(Rank(r)) for r in ("5", "6", "4")),
            dealer_hand=(Card(Rank("9")), Card(Rank("7"))),
            deck=(Card(Rank("2")),), inventory=("example_trim",), phase=GamePhase.PLAYER_TURN,
        )
        controller.phase = TablePhase.PLAYER_TURN
        app.scenes.reset("table", controller=controller)
        app.scenes.apply_pending()
        app._render()
        table = app.scenes.top
        from tests.test_gui_table import item_slot

        slot = item_slot(table)
        rect = slot.rect.copy()
        assert slot.act.arg == "example_trim" and "Discard" in slot.tooltip
        tooltips = []
        monkeypatch.setattr(widget_view, "draw_tooltip", lambda surface, assets, text, pos: tooltips.append(text))
        table.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": rect.center}))
        app._render()
        assert "Discard" in tooltips[-1]
        table.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": rect.center, "button": 1}))
        assert len(controller.state.player_hand) == 2
        assert controller.state.inventory == () and not table.view.items
    finally:
        app.audio.close()
        pygame.quit()
