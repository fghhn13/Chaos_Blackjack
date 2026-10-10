"""Table / ending / confirm scenes driven headlessly."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.app.config import RunConfig  # noqa: E402
from chaos_blackjack.app.controller import GameController  # noqa: E402
from chaos_blackjack.app.view import Action, TablePhase  # noqa: E402
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank  # noqa: E402
from chaos_blackjack.gui.app import App  # noqa: E402
from chaos_blackjack.gui.components.bet_panel import BetPanel  # noqa: E402
from chaos_blackjack.gui.settings import GuiSettings  # noqa: E402


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


@pytest.fixture()
def app(tmp_path):
    a = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes  # noqa: F401

    yield a
    pygame.quit()


def _open_table(app: App, *, deal=None, **cfg):
    ctrl = GameController(RunConfig(seed=3, **cfg))
    if deal is not None:
        player, dealer, deck = deal

        def fixed_round(seed=None, *, inventory_override=None):
            ctrl.loop.modifiers = ctrl.loop.modifiers.with_cleared()
            return GameState(tuple(player), tuple(dealer), tuple(deck), GamePhase.PLAYER_TURN,
                             inventory=inventory_override or ())

        ctrl.loop.new_round = fixed_round  # type: ignore[method-assign]
    app.scenes.reset("table", controller=ctrl)
    app.scenes.apply_pending()
    return app.scenes.top


def _key(app: App, key: int) -> None:
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key, "mod": 0, "unicode": ""}))
    app.scenes.apply_pending()


def _tick(app: App, seconds: float = 1.0, times: int = 1) -> None:
    for _ in range(times):
        app.scenes.update(seconds)
        app.scenes.apply_pending()
        app._render()  # noqa: SLF001  (draw must not crash in any state)


def test_full_round_with_hotkeys(app: App) -> None:
    t = _open_table(app, deal=([_c("10"), _c("8")], [_c("10"), _c("6")], [_c("K")]))
    assert t.view.phase == TablePhase.BETTING
    _key(app, pygame.K_RETURN)           # deal with default bet
    assert t.view.phase == TablePhase.PLAYER_TURN
    assert all(b.visible for b in t.action_buttons.values())
    _key(app, pygame.K_s)                # stand
    assert t.view.phase == TablePhase.DEALER_TURN
    _tick(app, 1.0, times=5)             # dealer draws K and busts
    assert t.view.phase == TablePhase.ROUND_OVER
    assert t.view.last_result.outcome == "player"
    assert t.next_button.visible
    assert any("Dealer busts" in line.text for line in t.feed.lines)
    _key(app, pygame.K_RETURN)           # next round
    assert t.view.phase == TablePhase.BETTING and t.view.round == 2


def test_double_and_surrender_buttons_follow_view(app: App) -> None:
    t = _open_table(app, deal=([_c("5"), _c("6")], [_c("10"), _c("7")], [_c("2"), _c("9")]))
    t._deal(10)  # noqa: SLF001
    assert t.action_buttons[Action.DOUBLE].enabled
    assert t.action_buttons[Action.SURRENDER].enabled
    _key(app, pygame.K_h)
    assert not t.action_buttons[Action.DOUBLE].enabled
    assert not t.action_buttons[Action.SURRENDER].enabled
    assert t.action_buttons[Action.HIT].enabled


def test_double_down_hotkey(app: App) -> None:
    t = _open_table(app, deal=([_c("5"), _c("6")], [_c("10"), _c("7")], [_c("K")]))
    t._deal(10)  # noqa: SLF001
    _key(app, pygame.K_d)
    _tick(app, 1.0, times=3)
    r = t.view.last_result
    assert r.doubled and r.delta == 20


def test_natural_shows_banner_immediately(app: App) -> None:
    t = _open_table(app, deal=([_c("A"), _c("K")], [_c("9"), _c("7")], []))
    t._deal(10)  # noqa: SLF001
    _tick(app, 0.01)
    assert t.view.phase == TablePhase.ROUND_OVER
    assert t.view.last_result.outcome == "blackjack"


def test_chaos_resolves_after_delay(app: App) -> None:
    t = _open_table(app, enable_chaos=True)
    t._deal(10)  # noqa: SLF001
    if t.view.phase == TablePhase.CHAOS:
        _tick(app, 0.01)
        assert t.view.phase == TablePhase.CHAOS
        _tick(app, 1.0)
    assert t.view.phase != TablePhase.CHAOS


def test_run_end_opens_ending(app: App) -> None:
    t = _open_table(app, deal=([_c("10"), _c("9")], [_c("10"), _c("7")], []),
                    start_money=100, target_money=105)
    t._deal(10)  # noqa: SLF001
    _key(app, pygame.K_s)
    _tick(app, 1.0, times=4)
    assert type(app.scenes.top).__name__ == "EndingScene"
    assert app.scenes.top.kind == "victory"
    _key(app, pygame.K_RETURN)  # play again
    assert type(app.scenes.top).__name__ == "TableScene"


def test_escape_confirm_returns_to_menu(app: App) -> None:
    _open_table(app)
    _key(app, pygame.K_ESCAPE)
    assert type(app.scenes.top).__name__ == "ConfirmScene"
    _tick(app, 0.01)
    _key(app, pygame.K_ESCAPE)  # cancel
    assert type(app.scenes.top).__name__ == "TableScene"
    _key(app, pygame.K_ESCAPE)
    _key(app, pygame.K_RETURN)  # confirm
    assert [type(s).__name__ for s in app.scenes.stack] == ["MainMenuScene"]


def test_bet_panel_chips_and_limits(app: App) -> None:
    dealt: list[int] = []
    panel = BetPanel(app.assets, (640, 600), dealt.append, initial=10)
    panel.set_limits(1, 30)
    chip25 = next(c for c in panel.chips if c.value == 25)
    chip5 = next(c for c in panel.chips if c.value == 5)

    def click(widget, button=1):
        panel.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": widget.rect.center, "button": button}))

    click(chip25)
    assert panel.amount == 30          # clamped to max
    click(chip5, button=3)
    assert panel.amount == 25
    panel.set_limits(1, 20)
    assert panel.amount == 20 and not chip25.enabled
    panel.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN, "mod": 0, "unicode": ""}))
    panel.deal_button.click()
    assert dealt == [19]
