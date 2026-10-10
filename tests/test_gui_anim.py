"""Tweens and table animations (presentation only; game state never waits on them)."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.app.config import RunConfig  # noqa: E402
from chaos_blackjack.app.controller import GameController  # noqa: E402
from chaos_blackjack.app.view import TablePhase  # noqa: E402
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank  # noqa: E402
from chaos_blackjack.gui import anim  # noqa: E402
from chaos_blackjack.gui.app import App  # noqa: E402
from chaos_blackjack.gui.settings import GuiSettings  # noqa: E402


@pytest.mark.parametrize("ease", [anim.linear, anim.out_quad, anim.out_cubic, anim.in_out_cubic,
                                  anim.out_back, anim.out_elastic])
def test_easings_start_at_0_and_end_at_1(ease) -> None:
    assert ease(0.0) == pytest.approx(0.0, abs=1e-9)
    assert ease(1.0) == pytest.approx(1.0, abs=1e-9)


def test_tween_delay_progress_and_done() -> None:
    done: list[bool] = []
    fx = anim.Animator()
    t = fx.add(anim.Tween(1.0, ease=anim.linear, delay=0.5, on_done=lambda: done.append(True)))
    fx.update(0.25)
    assert not t.started and t.value == 0.0 and fx.busy
    fx.update(0.75)
    assert t.value == pytest.approx(0.5)
    fx.update(0.6)
    assert t.done and done == [True] and not fx.busy and fx.tweens == []


def test_non_blocking_tweens_do_not_make_busy() -> None:
    fx = anim.Animator()
    fx.add(anim.Tween(1.0, blocking=False, tag="x"))
    assert not fx.busy
    fx.cancel("x")
    assert fx.tweens == []


# ------------------------------------------------------------------ table


def _c(r: str, s: str = "♠") -> Card:
    return Card(Rank(r), s)


@pytest.fixture()
def app(tmp_path):
    a = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes  # noqa: F401

    yield a
    pygame.quit()


def _table(app: App, player, dealer, deck):
    ctrl = GameController(RunConfig(seed=3))

    def fixed_round(seed=None, *, inventory_override=None):
        ctrl.loop.modifiers = ctrl.loop.modifiers.with_cleared()
        return GameState(tuple(player), tuple(dealer), tuple(deck), GamePhase.PLAYER_TURN,
                         inventory=inventory_override or ())

    ctrl.loop.new_round = fixed_round  # type: ignore[method-assign]
    app.scenes.reset("table", controller=ctrl)
    app.scenes.apply_pending()
    return app.scenes.top


def _run(app: App, seconds: float, dt: float = 1 / 60) -> None:
    for _ in range(round(seconds / dt)):
        app.scenes.update(dt)
        app.scenes.apply_pending()
    app._render()  # noqa: SLF001


def test_deal_animates_four_cards_in_table_order(app: App) -> None:
    t = _table(app, [_c("10"), _c("8")], [_c("10"), _c("6")], [_c("K")])
    t._deal(10)  # noqa: SLF001
    fx = t.fx
    assert set(fx.cards) == {("player", 0), ("dealer", 0), ("player", 1), ("dealer", 1)}
    delays = {k: c.tween.delay for k, c in fx.cards.items()}
    assert delays[("player", 0)] < delays[("dealer", 0)] < delays[("player", 1)] < delays[("dealer", 1)]
    assert fx.busy and fx.hand_moving("player")
    _run(app, 1.0)
    assert not fx.busy and fx.cards == {}


def test_dealer_waits_for_cards_but_player_input_does_not(app: App) -> None:
    t = _table(app, [_c("10"), _c("8")], [_c("10"), _c("6")], [_c("K")])
    t._deal(10)  # noqa: SLF001
    # Input works mid-deal.
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_s, "mod": 0, "unicode": ""}))
    assert t.view.phase == TablePhase.DEALER_TURN
    _run(app, 0.3)                      # cards still flying: the dealer has not acted
    assert t.view.phase == TablePhase.DEALER_TURN and t.fx.busy
    _run(app, 4.0)
    assert t.view.phase == TablePhase.ROUND_OVER


def test_hole_card_reveal_flips_and_round_settles(app: App) -> None:
    t = _table(app, [_c("10"), _c("9")], [_c("10"), _c("7")], [])
    t._deal(10)  # noqa: SLF001
    _run(app, 1.0)
    t._command("stand")()  # noqa: SLF001
    # Standing reveals the hole card (the view hides it only on the player's turn).
    assert t.fx.cards[("dealer", 1)].kind == "flip" and t.fx.busy
    _run(app, 3.0)
    assert t.view.phase == TablePhase.ROUND_OVER and t.fx.settle is not None
    assert t.fx.money_shown() == t.view.money == 110
    assert t.fx.banner_progress() == pytest.approx(1.0)


def test_money_rolls_toward_new_bankroll(app: App) -> None:
    t = _table(app, [_c("10"), _c("9")], [_c("10"), _c("7")], [])
    t._deal(10)  # noqa: SLF001
    _run(app, 1.0)
    t._command("stand")()  # noqa: SLF001
    _run(app, 1.5)
    seen = set()
    for _ in range(40):
        _run(app, 0.05)
        seen.add(t.fx.money_shown())
    assert 110 in seen and len(seen) > 2  # passed through intermediate values
