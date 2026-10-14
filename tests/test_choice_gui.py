"""The GUI's choice dialog and Poker Head's build flows, headless (SDL dummy drivers)."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from dataclasses import replace

import pygame
import pytest

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.shop import ShopOffer, ShopState
from chaos_blackjack.data.balance import default_balance
from chaos_blackjack.modes import get_mode


@pytest.fixture
def app(tmp_path):
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401

    a = App(GuiSettings(asset_dirs=(tmp_path,)))
    yield a
    pygame.quit()


def _controller() -> GameController:
    # The dialogs at the reference scale: 100 chips, amounts as written for 100, two slots, free cores.
    cfg = get_mode("chaos").apply(RunConfig.from_balance(default_balance(), seed=7, use_llm=False))
    settings = {**cfg.mode_settings, "chaos.money_base": 100, "chaos.build_slots": 2, "chaos.core_cash": "{}"}
    return GameController(replace(cfg, enable_chaos=False, start_money=100, target_money=500, target_multiple=0.0,
                                  exit_multiple=0.0, mode_settings=settings), save_fn=lambda d, n: n)


def _frame(app) -> None:
    app.scenes.update(0.05)
    app.scenes.apply_pending()
    app._render()  # noqa: SLF001


def _key(app, key) -> None:
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0, "unicode": ""}))
    app.scenes.apply_pending()


def _open_table(app, c):
    app.scenes.reset("table", controller=c)
    app.scenes.apply_pending()
    _frame(app)
    return app.scenes.stack[0]


def test_the_opening_invitation_opens_a_dialog_that_cannot_be_dismissed(app) -> None:
    c = _controller()
    _open_table(app, c)
    assert type(app.scenes.top).__name__ == "ChoiceScene"
    _key(app, pygame.K_ESCAPE)                      # not cancellable: the dialog stays
    _frame(app)
    assert type(app.scenes.top).__name__ == "ChoiceScene" and c.choice is not None
    first = c.choice.options[0].id
    _key(app, pygame.K_1)
    _frame(app)
    assert c.choice is None and type(app.scenes.top).__name__ == "TableScene"
    assert c.table.loadout.core == first
    assert len(c.view().shop_offers) >= 3


def test_a_full_build_asks_what_to_replace_from_the_shop(app) -> None:
    c = _controller()
    c.choose(c.choice.options[0].id)
    c.table.loadout.equipped = ["ph_long_reward", "ph_mark"]
    c.shop = ShopState(c.run.round, (ShopOffer("ph_sleeve", 55),))
    table = _open_table(app, c)
    table._open_shop()  # noqa: SLF001
    app.scenes.apply_pending()
    shop = app.scenes.top
    shop.buy_buttons[0].click()
    app.scenes.apply_pending()
    _frame(app)
    assert type(app.scenes.top).__name__ == "ChoiceScene" and c.run.money == 100
    _key(app, pygame.K_ESCAPE)                      # cancel: nothing charged, back in the shop
    _frame(app)
    assert app.scenes.top is shop and c.choice is None and c.run.money == 100
    shop.buy_buttons[0].click()
    app.scenes.apply_pending()
    _key(app, pygame.K_2)                           # replace Sleeve Mark
    _frame(app)
    assert app.scenes.top is shop and c.run.money == 45
    assert c.table.loadout.equipped == ["ph_long_reward", "ph_sleeve"]


def test_items_show_their_phase_and_a_targeted_item_asks_in_the_bag(app) -> None:
    from chaos_blackjack.app.layout import layout_for

    c = _controller()
    c.choose(c.choice.options[0].id)
    c.table.holdings.add("ph_buyback", 6)
    c.table.holdings.add("ph_peek", 4)
    c.table._sync_items()  # noqa: SLF001
    _open_table(app, c)
    app.scenes.push("run_panel", controller=c, layout=layout_for("chaos"), tab="bag")
    app.scenes.apply_pending()
    panel = app.scenes.top
    entries = {e.title: e for w in panel.view.widgets for e in getattr(w, "entries", ())}
    assert "On your turn" in entries["Card Lens"].text and not entries["Card Lens"].act.enabled
    assert "Before betting" in entries["Original Price Receipt"].text and entries["Original Price Receipt"].act.enabled
    panel._act(entries["Original Price Receipt"].act)  # noqa: SLF001
    app.scenes.apply_pending()
    _frame(app)
    assert type(app.scenes.top).__name__ == "ChoiceScene" and c.choice.kind == "target"
    _key(app, pygame.K_1)
    _frame(app)
    assert c.choice is None and c.run.money == 104 and c.run.items == ()
