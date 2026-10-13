"""Table / ending / confirm scenes driven headlessly."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from threading import Event, current_thread
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.app.config import RunConfig  # noqa: E402
from chaos_blackjack.ai.gptsapi_llm import GptsApiLLM  # noqa: E402
from chaos_blackjack.app.controller import GameController  # noqa: E402
from chaos_blackjack.app.notices import NoticeKind  # noqa: E402
from chaos_blackjack.app.view import Action, TablePhase  # noqa: E402
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank  # noqa: E402
from chaos_blackjack.gui.app import App  # noqa: E402
from chaos_blackjack.gui.components.table_fx import DEAL_TIME, DEAL_GAP
from chaos_blackjack.gui.components.bet_panel import BetPanel  # noqa: E402
from chaos_blackjack.gui.settings import GuiSettings  # noqa: E402
from chaos_blackjack.gui.scenes.table import CHAOS_DELAY, CHAOS_ERROR, ACTION_Y, W  # noqa: E402


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


def _portrait_click(app, table):
    # Do not flush queued scene changes: exercise several events in one frame.
    app.scenes.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, {"button": 1, "pos": table.chaos_panel.portrait_rect.center}))


def _open_poke(app, monkeypatch, llm, table=None):
    t = table or _open_table(app, enable_chaos=True)
    llm.response = '{"reply":"Keep enough chips to bet."}'
    monkeypatch.setattr(t.controller.loop.pipeline, "llm", llm)
    _portrait_click(app, t)
    app.scenes.apply_pending()
    assert llm.started.wait(timeout=1)
    return t, app.scenes.top


def test_poke_blocks_same_frame_clicks_and_keeps_banner_animating(app, monkeypatch, slow_llm):
    t = _open_table(app, enable_chaos=True)
    slow_llm.response = '{"reply":"Keep enough chips to bet."}'
    monkeypatch.setattr(t.controller.loop.pipeline, "llm", slow_llm)
    before = t.controller.view()
    delivered = []
    t.subscribe(NoticeKind.CHAOS_POKE_REPLY, lambda n: delivered.append(current_thread()))
    for _ in range(8):
        _portrait_click(app, t)
    t._deal(10)
    app.scenes.apply_pending()
    banner = app.scenes.top
    assert type(banner).__name__ == "ChaosPokeScene" and len(app.scenes.stack) == 2
    assert slow_llm.started.wait(timeout=1)
    assert not banner.continue_button.enabled
    _tick(app, 0.01)
    area = (banner.box.centerx - 30, banner.box.centery + 12, 60, 16)
    pixels = pygame.image.tostring(app.canvas.subsurface(area), "RGB")
    _tick(app, .25)
    assert pixels != pygame.image.tostring(app.canvas.subsurface(area), "RGB")
    for key in (pygame.K_RETURN, pygame.K_h, pygame.K_s, pygame.K_b):
        _key(app, key)
    _portrait_click(app, t)
    app.scenes.apply_pending()
    assert app.scenes.top is banner and slow_llm.calls == 1
    assert t.controller.view() == before
    assert slow_llm.thread is not current_thread() and slow_llm.thread.daemon
    slow_llm.release.set()
    banner._future.result(timeout=3)
    _tick(app, .01)
    assert banner.continue_button.enabled and app.scenes.top is banner
    _portrait_click(app, t)
    app.scenes.apply_pending()
    assert slow_llm.calls == 1
    _key(app, pygame.K_RETURN)
    assert app.scenes.top is t and not t._poke_pending
    assert t.controller.view() == before and t.chaos_panel.poke_enabled
    assert t.chaos_panel.speech == "Keep enough chips to bet."
    assert delivered == [current_thread()]
    monkeypatch.setattr(t.controller, "_save_fn", lambda data, name: name)
    assert "chaos_memory" not in t.controller.save("unused").to_dict()


def test_shop_poke_snapshots_purchase_and_returns_to_shop(app, monkeypatch, slow_llm):
    t = _open_table(app, enable_chaos=True, shop_prices={"peek": 10, "shield": 30}, shop_slots=2)
    _key(app, pygame.K_b)
    shop = app.scenes.top
    _key(app, pygame.K_1)
    bought = shop.view.shop_offers[0].item
    before = t.controller.view()
    slow_llm.response = '{"reply":"Keep enough chips to bet."}'
    monkeypatch.setattr(t.controller.loop.pipeline, "llm", slow_llm)
    for _ in range(3):
        _portrait_click(app, t)
    app.scenes.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2, "mod": 0}))
    app.scenes.apply_pending()
    banner = app.scenes.top
    assert slow_llm.started.wait(timeout=1)
    assert len(app.scenes.stack) == 3 and t.controller.view() == before
    snapshot = json.loads(banner.request.context_json)
    assert next(o for o in snapshot["shop"]["offers"] if o["item"] == bought)["sold"]
    assert snapshot["bankroll"] == before.money
    assert snapshot["inventory"][0]["id"] == bought
    shop._buyer(shop.view.shop_offers[1].item)()  # queued callback cannot purchase now
    _key(app, pygame.K_2)
    assert t.controller.view() == before and slow_llm.calls == 1
    slow_llm.release.set()
    banner._future.result(timeout=3)
    _tick(app, .01)
    _key(app, pygame.K_RETURN)
    assert app.scenes.top is shop and not shop._poke_pending
    _key(app, pygame.K_2)
    assert t.controller.view().money < before.money
    _key(app, pygame.K_ESCAPE)
    assert app.scenes.top is t and len(t.view.items) == 2


@pytest.mark.parametrize("settled", [False, True])
def test_poke_at_player_turn_and_round_result_restores_controls(app, monkeypatch, slow_llm, settled):
    t = _open_table(app, enable_chaos=True,
                    deal=([_c("9"), _c("7")], [_c("K"), _c("8")], [_c("K"), _c("2")]))
    monkeypatch.setattr(t.controller.loop.pipeline.scheduler, "should_attempt", lambda obs: False)
    t._deal(10)
    _tick(app, DEAL_TIME + 3 * DEAL_GAP + CHAOS_DELAY)
    t._chaos_future.result(timeout=3)
    _tick(app, .01)
    if settled:
        t.controller.stand()
        t.controller.finish_dealer()
        t._after_command()
    before = t.controller.view()
    _, banner = _open_poke(app, monkeypatch, slow_llm, t)
    snapshot = json.loads(banner.request.context_json)
    assert snapshot["dealer"]["cards"] == ["K♠", "8♠"]
    assert snapshot["deck"] == ["K♠", "2♠"]
    assert snapshot["phase"] == ("round_over" if settled else "player_turn")
    slow_llm.release.set()
    banner._future.result(timeout=3)
    _tick(app, .01)
    _key(app, pygame.K_RETURN)
    assert app.scenes.top is t and t.controller.view() == before
    assert t.next_button.enabled if settled else t.action_buttons[Action.HIT].enabled


def test_poke_exit_discards_late_reply_and_cancel_preserves_request(app, monkeypatch, slow_llm):
    t, banner = _open_poke(app, monkeypatch, slow_llm)
    result = banner._future
    # Repeated Escape events before apply_pending must create just one confirmation.
    event = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE, "mod": 0})
    for _ in range(3):
        app.scenes.handle_event(event)
    app.scenes.apply_pending()
    assert len(app.scenes.stack) == 3
    _key(app, pygame.K_ESCAPE)
    assert app.scenes.top is banner and slow_llm.calls == 1
    _key(app, pygame.K_ESCAPE)
    _key(app, pygame.K_RETURN)
    assert type(app.scenes.top).__name__ == "HomeScene"
    assert t._closed and banner._closed and not result.done()
    fresh = _open_table(app, enable_chaos=True)
    slow_llm.release.set()
    result.result(timeout=3)
    _tick(app, .01)
    assert app.scenes.top is fresh and fresh.chaos_panel.speech is None
    assert NoticeKind.CHAOS_POKE_REPLY not in [n.kind for n in t.controller.drain_notices()]


def test_failed_poke_is_dismissible_without_retry(app, monkeypatch, slow_llm):
    slow_llm.fail = True
    t, banner = _open_poke(app, monkeypatch, slow_llm)
    before = t.controller.view()
    slow_llm.release.set()
    banner._future.result(timeout=3)
    _tick(app, .01, times=3)
    assert not banner.reply.ok and banner.continue_button.enabled
    _key(app, pygame.K_RETURN)
    assert app.scenes.top is t and t.chaos_panel.poke_enabled
    assert t.controller.view() == before and slow_llm.calls == 1


def test_off_portrait_in_shop_does_not_lock_purchases(app):
    t = _open_table(app, shop_prices={"peek": 10}, shop_slots=1)
    _key(app, pygame.K_b)
    shop = app.scenes.top
    _portrait_click(app, t)
    app.scenes.apply_pending()
    assert app.scenes.top is shop and not shop._poke_pending
    _key(app, pygame.K_1)
    assert shop.view.money == 90


def test_window_quit_does_not_wait_for_poke(app, monkeypatch, slow_llm):
    _, banner = _open_poke(app, monkeypatch, slow_llm)
    result = banner._future
    app.running = True
    app._dispatch(pygame.event.Event(pygame.QUIT))
    assert not app.running and not result.done()


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
        t._chaos_future.result(timeout=3)
        _tick(app, 0.01)
    assert t.view.phase != TablePhase.CHAOS


class _SlowLLM:
    def __init__(self, response='{"action":"noop","narration":"Your move."}', *, fail=False):
        self.started = Event()
        self.release = Event()
        self.response = response
        self.fail = fail
        self.calls = 0
        self.thread = None

    def complete(self, system_prompt, user_prompt):
        self.calls += 1
        self.thread = current_thread()
        self.started.set()
        if not self.release.wait(timeout=3):
            raise TimeoutError("Test did not release the simulated LLM")
        if self.fail:
            raise RuntimeError("Simulated backend failure")
        return self.response


@pytest.fixture()
def slow_llm():
    llm = _SlowLLM()
    yield llm
    llm.release.set()


def _start_chaos(app, monkeypatch, llm, *, natural=False, backend=None):
    player = [_c("A"), _c("K")] if natural else [_c("10"), _c("8")]
    t = _open_table(app, enable_chaos=True,
                    deal=(player, [_c("10"), _c("7")], []))
    monkeypatch.setattr(t.controller.loop.pipeline, "llm", backend or llm)
    monkeypatch.setattr(t.controller.loop.pipeline.scheduler, "should_attempt", lambda obs: True)
    t._deal(10)
    _tick(app, DEAL_TIME + 3 * DEAL_GAP + CHAOS_DELAY)
    assert llm.started.wait(timeout=1)
    assert t._chaos_future is not None and not t._chaos_future.done()
    return t


def test_slow_chaos_keeps_rendering_and_completes_on_main_thread(app, monkeypatch, slow_llm):
    slow_llm.response = ('{"action":"apply_rule","rule_id":"modify_card_value",'
                         '"params":{"delta":-1},"narration":"Your move."}')
    t = _start_chaos(app, monkeypatch, slow_llm)
    cached = t.view
    main_thread = current_thread()
    delivered = []
    t.subscribe("*", lambda n: delivered.append((n.kind, current_thread())))
    view, drain = t.controller.view, t.controller.drain_notices

    def checked_read(method):
        def read():
            assert slow_llm.release.is_set(), "Controller read while worker owns it"
            assert current_thread() is main_thread
            return method()
        return read

    monkeypatch.setattr(t.controller, "view", checked_read(view))
    monkeypatch.setattr(t.controller, "drain_notices", checked_read(drain))
    before = pygame.image.tostring(app.canvas.subsurface((W // 2 - 30, ACTION_Y + 34, 60, 16)), "RGB")
    _tick(app, 0.25)
    after = pygame.image.tostring(app.canvas.subsurface((W // 2 - 30, ACTION_Y + 34, 60, 16)), "RGB")
    assert before != after  # the placeholder dots animate while the call is blocked
    _tick(app, 0.25, times=3)
    for key in (pygame.K_h, pygame.K_s, pygame.K_d, pygame.K_r, pygame.K_RETURN):
        _key(app, key)
    t._command("hit")()
    t._deal(10)
    t._use_item("peek")
    assert t.view is cached and t.view.dealer_total is None
    assert all(not b.enabled for b in t.action_buttons.values())
    assert not delivered and slow_llm.calls == 1
    assert slow_llm.thread is not main_thread and slow_llm.thread.daemon

    slow_llm.release.set()
    t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    assert t.view.phase == TablePhase.PLAYER_TURN
    assert t.view.player_total == 16 and t.view.active_rules
    assert t.view.dealer_total is None
    assert t.action_buttons[Action.HIT].enabled
    assert NoticeKind.CHAOS_NARRATION in [kind for kind, _ in delivered]
    assert all(thread is main_thread for _, thread in delivered)
    _key(app, pygame.K_s)
    _tick(app, 1.0)
    assert t.view.phase == TablePhase.ROUND_OVER


def test_chaos_worker_failure_is_shown_once_without_retry(app, monkeypatch, slow_llm):
    slow_llm.fail = True
    t = _start_chaos(app, monkeypatch, slow_llm)
    slow_llm.release.set()
    with pytest.raises(RuntimeError, match="Simulated backend failure"):
        t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    _tick(app, 1.0, times=4)
    assert t._chaos_future is None and t._chaos_failed
    assert slow_llm.calls == 1
    assert sum(line.text == CHAOS_ERROR for line in t.feed.lines) == 1
    _key(app, pygame.K_ESCAPE)
    _key(app, pygame.K_RETURN)
    assert type(app.scenes.top).__name__ == "HomeScene"


def test_llm_network_failure_preserves_noop_fallback(app, monkeypatch, slow_llm):
    def chat(*args):
        slow_llm.complete("", "")
        raise RuntimeError("Network error: timed out")

    backend = GptsApiLLM(SimpleNamespace(chat=chat))
    t = _start_chaos(app, monkeypatch, slow_llm, backend=backend)
    slow_llm.release.set()
    t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    assert backend.last_error == "Network error: timed out"
    assert t.view.phase == TablePhase.PLAYER_TURN
    assert not t._chaos_failed and not t.view.active_rules
    assert t.action_buttons[Action.HIT].enabled
    assert slow_llm.calls == 1


def test_chaos_completion_waits_for_modal_to_close(app, monkeypatch, slow_llm):
    t = _start_chaos(app, monkeypatch, slow_llm)
    cached = t.view
    _key(app, pygame.K_ESCAPE)
    slow_llm.release.set()
    t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    assert t.view is cached
    _key(app, pygame.K_ESCAPE)
    _tick(app, 0.01)
    assert t.view.phase == TablePhase.PLAYER_TURN
    assert t.action_buttons[Action.HIT].enabled


def test_cancel_exit_while_chaos_runs_does_not_read_controller(app, monkeypatch, slow_llm):
    t = _start_chaos(app, monkeypatch, slow_llm)
    cached = t.view
    timer = t._timer

    def forbidden_read():
        pytest.fail("Modal resume read the controller while the chaos worker owns it")

    with monkeypatch.context() as reads:
        reads.setattr(t.controller, "view", forbidden_read)
        reads.setattr(t.controller, "drain_notices", forbidden_read)
        _key(app, pygame.K_ESCAPE)
        _tick(app, 0.01)
        _key(app, pygame.K_ESCAPE)
        assert app.scenes.top is t
        assert t.view is cached and t._timer == timer
        _key(app, pygame.K_b)
        assert app.scenes.top is t

    slow_llm.release.set()
    t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    assert t.view.phase == TablePhase.PLAYER_TURN
    assert t.action_buttons[Action.HIT].enabled


def test_shop_purchase_survives_chaos_and_shield_dispels_result(app, monkeypatch, slow_llm):
    t = _open_table(app, enable_chaos=True, shop_prices={"shield": 10}, shop_slots=1,
                    deal=([_c("10"), _c("8")], [_c("10"), _c("7")], []))
    slow_llm.response = ('{"action":"apply_rule","rule_id":"modify_card_value",'
                         '"params":{"delta":-1}}')
    monkeypatch.setattr(t.controller.loop.pipeline, "llm", slow_llm)
    monkeypatch.setattr(t.controller.loop.pipeline.scheduler, "should_attempt", lambda obs: True)
    _key(app, pygame.K_b)
    _key(app, pygame.K_1)
    _key(app, pygame.K_ESCAPE)
    assert app.scenes.top is t
    assert t.view.money == 90 and t.view.items[0].id == "shield"
    t._deal(10)
    _tick(app, DEAL_TIME + 3 * DEAL_GAP + CHAOS_DELAY)
    assert slow_llm.started.wait(timeout=1)
    cached = t.view
    t._use_item("shield")
    _key(app, pygame.K_b)
    assert t.view is cached and app.scenes.top is t

    slow_llm.release.set()
    t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    assert t.view.player_total == 16 and t.view.active_rules
    assert t.view.items[0].id == "shield"
    t._use_item("shield")
    assert t.view.player_total == 18 and not t.view.active_rules and not t.view.items
    _key(app, pygame.K_s)
    _tick(app, 1.0)
    assert t.view.last_result.outcome == "player" and t.view.money == 100
    _key(app, pygame.K_RETURN)
    assert t.view.phase == TablePhase.BETTING


def test_window_quit_does_not_wait_for_chaos(app, monkeypatch, slow_llm):
    t = _start_chaos(app, monkeypatch, slow_llm)
    result = t._chaos_future
    app.running = True
    app._dispatch(pygame.event.Event(pygame.QUIT))
    assert not app.running and not result.done()
    slow_llm.release.set()
    result.result(timeout=3)


def test_exit_during_chaos_ignores_late_result_and_new_table_still_works(app, monkeypatch, slow_llm):
    old = _start_chaos(app, monkeypatch, slow_llm)
    result = old._chaos_future
    cached = old.view
    delivered = []
    old.subscribe("*", delivered.append)
    _key(app, pygame.K_ESCAPE)
    _key(app, pygame.K_RETURN)
    assert type(app.scenes.top).__name__ == "HomeScene"
    assert old._closed and old._chaos_future is None
    new = _open_table(app)
    slow_llm.release.set()
    result.result(timeout=3)
    old.update(1.0)
    old._command("stand")()
    _tick(app, 0.01)
    assert old.view is cached and not delivered
    assert new.view.phase == TablePhase.BETTING
    assert not new.feed.lines
    _key(app, pygame.K_RETURN)
    assert new.view.phase == TablePhase.PLAYER_TURN


def test_chaos_natural_settles_and_next_round_starts_another_worker(app, monkeypatch, slow_llm):
    t = _open_table(app, enable_chaos=True,
                    deal=([_c("A"), _c("K")], [_c("10"), _c("7")], []))
    monkeypatch.setattr(t.controller.loop.pipeline, "llm", slow_llm)
    monkeypatch.setattr(t.controller.loop.pipeline.scheduler, "should_attempt", lambda obs: True)
    t._deal(10)
    _tick(app, DEAL_TIME + 3 * DEAL_GAP + CHAOS_DELAY)
    assert t.view.phase == TablePhase.ROUND_OVER
    assert t.view.last_result.outcome == "blackjack"
    assert slow_llm.calls == 0 and not slow_llm.started.is_set()
    _key(app, pygame.K_RETURN)
    assert t.view.phase == TablePhase.BETTING
    natural_round = t.controller.loop.new_round
    monkeypatch.setattr(t.controller.loop, "new_round", lambda **kwargs: replace(
        natural_round(**kwargs), player_hand=(_c("10"), _c("8"))))
    t._deal(10)
    _tick(app, DEAL_TIME + 3 * DEAL_GAP + CHAOS_DELAY)
    assert slow_llm.started.wait(timeout=1)
    assert slow_llm.calls == 1
    slow_llm.release.set()
    t._chaos_future.result(timeout=3)
    _tick(app, 0.01)
    assert t.view.phase == TablePhase.PLAYER_TURN


def test_run_end_opens_ending(app: App) -> None:
    t = _open_table(app, deal=([_c("10"), _c("9")], [_c("10"), _c("7")], []),
                    start_money=100, target_money=105)
    t._deal(10)  # noqa: SLF001
    _key(app, pygame.K_s)
    _tick(app, 1.0, times=4)
    t = app.scenes.top
    assert type(t).__name__ == "TableScene" and t.outro is not None  # the host speaks first
    while t.intro_open():
        _key(app, pygame.K_RETURN)
    _tick(app, 0.1)
    assert type(app.scenes.top).__name__ == "EndingScene"
    assert app.scenes.top.kind == "victory"
    _key(app, pygame.K_RETURN)  # play again
    assert type(app.scenes.top).__name__ == "TableScene"


def test_escape_confirm_returns_to_home(app: App) -> None:
    _open_table(app)
    _key(app, pygame.K_ESCAPE)
    assert type(app.scenes.top).__name__ == "ConfirmScene"
    _tick(app, 0.01)
    _key(app, pygame.K_ESCAPE)  # cancel
    assert type(app.scenes.top).__name__ == "TableScene"
    _key(app, pygame.K_ESCAPE)
    _key(app, pygame.K_RETURN)  # confirm
    assert [type(s).__name__ for s in app.scenes.stack] == ["HomeScene"]


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


def test_shop_opens_while_betting_and_buys(app) -> None:
    table = _open_table(app)
    _key(app, pygame.K_b)
    shop = app.scenes.top
    assert type(shop).__name__ == "ShopScene"
    offer = table.view.shop_offers[0]
    _key(app, pygame.K_1)
    assert table.view.money == 100 - offer.price
    assert [i.id for i in table.view.items] == [offer.item]
    app.scenes.draw(app.canvas)  # renders without errors
    _key(app, pygame.K_ESCAPE)
    assert app.scenes.top is table


def test_shop_button_disabled_during_a_round(app) -> None:
    table = _open_table(app)
    table._deal(10)
    _key(app, pygame.K_b)
    assert app.scenes.top is table


def test_clicking_hovered_item_keeps_drawing(app: App) -> None:
    t = _open_table(app, deal=([_c("10"), _c("2")], [_c("10"), _c("7")], [_c("5"), _c("K")]))
    t.controller.run.items = ("peek", "peek")
    _key(app, pygame.K_RETURN)
    _tick(app, 0.5, times=4)
    app._render()  # noqa: SLF001 - lays out the item slots
    rect = item_slot(t).rect.copy()
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": rect.center, "rel": (0, 0), "buttons": (0, 0, 0)}))
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": rect.center, "button": 1}))
    _tick(app, 0.01)  # the tooltip follows the refreshed slot instead of crashing
    app._render()  # noqa: SLF001
    assert t.view.items[0].count == 1 and item_slot(t) is not None
    app.scenes.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": rect.center, "button": 1}))
    _tick(app, 0.01)
    app._render()  # noqa: SLF001 - last copy used: the slot disappears
    assert not t.view.items and item_slot(t) is None


def item_slot(table):
    """The first item slot drawn in the table's side columns (None if there is none)."""
    from chaos_blackjack.gui.components.side_column import DataBlock

    blocks = [b for col in (table.left, table.right) for b in col.visible if isinstance(b, DataBlock)]
    return next((h for b in blocks for h in b.view.hits if h.act is not None and h.act.id == "use_item"), None)
