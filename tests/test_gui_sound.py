"""Sound policy and animation alignment without a speaker or wall-clock sleep."""

import os
import random
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.notices import Notice, NoticeKind as N
from chaos_blackjack.app.view import RoundResult
from dataclasses import replace
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.gui.anim import Animator, Tween
from chaos_blackjack.gui.app import App, Preferences
from chaos_blackjack.gui.audio import SoundManager
from chaos_blackjack.gui.components.table_fx import CHIP_DROP, DEAL_GAP, FLIP_TIME, SETTLE_TIME
from chaos_blackjack.gui.settings import GuiSettings
from chaos_blackjack.gui.widgets import Button


class Channel:
    def __init__(self):
        self.played = []
        self.volume = 1
        self.stopped = False

    def get_busy(self):
        return False

    def play(self, sound):
        self.played.append(sound)

    def set_volume(self, volume):
        self.volume = volume

    def stop(self):
        self.stopped = True


@pytest.fixture
def mixer(monkeypatch):
    channels = {}
    loaded = []
    fake = SimpleNamespace(
        get_init=lambda: (44100, -16, 2), get_num_channels=lambda: 8,
        set_num_channels=lambda count: None,
        Channel=lambda index: channels.setdefault(index, Channel()),
        Sound=lambda path: loaded.append(path) or path,
    )
    monkeypatch.setattr(pygame, "mixer", fake)
    monkeypatch.setenv("SDL_AUDIODRIVER", "test")  # no real mixer calls; all methods above are fake
    return fake, channels, loaded


def clip(root, name, data=b"fixture"):
    folder = root / "sounds"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)


def test_dummy_driver_and_initialization_failure_are_silent(tmp_path, monkeypatch):
    clip(tmp_path, "card_deal.ogg")
    audio = SoundManager([tmp_path])
    assert not audio.available and not audio.play("card_deal")
    audio.toggle_mute()
    audio.refresh()
    audio.close()
    monkeypatch.setenv("SDL_AUDIODRIVER", "test")
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    def fail(**kwargs):
        raise pygame.error("No audio device")
    monkeypatch.setattr(pygame.mixer, "init", fail)
    audio = SoundManager([tmp_path])
    assert not audio.available and not audio.play("card_deal")


def test_missing_and_invalid_clips_are_silent(tmp_path, mixer):
    audio = SoundManager([tmp_path])
    assert audio.available and not audio.play("missing")
    clip(tmp_path, "card_flip.ogg")
    audio.refresh()
    def fail(path):
        raise pygame.error("Invalid test clip")
    mixer[0].Sound = fail
    assert not audio.play("card_flip")


def test_first_directory_wins_over_lower_priority_variants(tmp_path, mixer):
    first, second = tmp_path / "first", tmp_path / "second"
    clip(first, "card_deal.wav")
    for i in range(1, 4):
        clip(second, f"card_deal_{i}.ogg")
    clip(first, "card_deal.ogg")
    audio = SoundManager([first, second])
    assert audio.paths("card_deal") == (first / "sounds/card_deal.ogg",)
    assert audio.play("card_deal")
    assert mixer[2] == [str(first / "sounds/card_deal.ogg")]


def test_throttle_is_per_cue_family_and_variants_use_local_rng(tmp_path, mixer):
    for i in range(1, 4):
        clip(tmp_path, f"card_deal_{i}.ogg")
    clip(tmp_path, "card_flip.ogg")
    now = [0.0]
    state = random.getstate()
    audio = SoundManager([tmp_path], clock=lambda: now[0], rng=random.Random(7))
    assert audio.play("card_deal")
    assert not audio.play("card_deal_2")  # direct variant shares the family cooldown
    assert audio.play("card_flip")       # another cue is independent
    now[0] = 0.049
    assert not audio.play("card_deal")
    now[0] = 0.05
    assert audio.play("card_deal")
    for i in range(1, 10):
        now[0] += 0.051
        assert audio.play("card_deal")
    assert len({path for path in mixer[2] if "card_deal" in path}) > 1
    assert random.getstate() == state


def test_master_volume_mute_and_refresh(tmp_path, mixer):
    clip(tmp_path, "card_deal.ogg")
    prefs = Preferences()
    audio = SoundManager([tmp_path], preferences=prefs)
    assert audio.volume == 0.4
    assert audio.play("card_deal")
    channel = mixer[1][8]
    assert channel.volume == pytest.approx(0.4 * 0.7)
    audio.set_volume(0.2)
    assert channel.volume == pytest.approx(0.2 * 0.7) and prefs.master_volume == 0.2
    audio.toggle_mute()
    assert prefs.muted and channel.stopped and not audio.play("card_deal")
    audio.set_volume(0.3)
    assert audio.muted and audio.effective_volume == 0
    audio.toggle_mute()
    assert audio.effective_volume == 0.3
    audio.set_volume(2)
    assert prefs.master_volume == 1
    clip(tmp_path, "chip_stack.wav")
    assert not audio.paths("chip_stack")
    audio.refresh()
    assert audio.play("chip_stack")


def test_tween_start_callbacks_fire_once_at_existing_delay():
    calls = []
    animator = Animator()
    animator.add(Tween(0.2, on_start=lambda: calls.append("immediate")))
    delayed = animator.add(Tween(0.2, delay=0.3, on_start=lambda: calls.append("start"),
                                on_done=lambda: calls.append("done")))
    assert calls == ["immediate"]
    animator.update(0.29)
    assert calls == ["immediate"] and not delayed.started
    animator.update(0.02)
    assert calls == ["immediate", "start"]
    animator.update(1)
    animator.update(1)
    assert calls == ["immediate", "start", "done"]


class AudioSpy:
    def __init__(self):
        self.time = 0.0
        self.calls = []

    def play(self, cue):
        self.calls.append((self.time, cue))
        return True


@pytest.fixture
def app(tmp_path):
    application = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes
    yield application
    application.audio.close()
    pygame.quit()


def table(app, *, player=("10", "9"), dealer=("10", "7"), deck=()):
    spy = AudioSpy()
    app.audio = spy
    app.assets.audio = spy
    controller = GameController(RunConfig(seed=3))
    def fixed_round(seed=None, *, inventory_override=None):
        return GameState(tuple(Card(Rank(rank)) for rank in player), tuple(Card(Rank(rank)) for rank in dealer),
                         tuple(Card(Rank(rank)) for rank in deck), GamePhase.PLAYER_TURN)
    controller.loop.new_round = fixed_round
    app.scenes.reset("table", controller=controller)
    app.scenes.apply_pending()
    return app.scenes.top, spy


def advance(fx, spy, seconds):
    spy.time += seconds
    fx.update(seconds)


def test_four_deal_sounds_follow_each_card_start_not_notices(app):
    original = app.audio
    try:
        scene, spy = table(app)
        scene._deal(10)
        assert spy.calls == [(0, "card_deal")]
        for _ in range(3):
            advance(scene.fx, spy, DEAL_GAP)
        deals = [time for time, cue in spy.calls if cue == "card_deal"]
        assert deals == pytest.approx([0, DEAL_GAP, 2 * DEAL_GAP, 3 * DEAL_GAP])
        stack = [time for time, cue in spy.calls if cue == "chip_stack"]
        assert stack and stack[0] >= CHIP_DROP
        advance(scene.fx, spy, 1)
        assert len([cue for _, cue in spy.calls if cue == "card_deal"]) == 4
    finally:
        app.audio = original


def test_stand_flip_sounds_at_the_visual_midpoint(app):
    original = app.audio
    try:
        scene, spy = table(app)
        scene._deal(10)
        advance(scene.fx, spy, 1)
        spy.calls.clear()
        scene._command("stand")()
        assert not spy.calls
        advance(scene.fx, spy, FLIP_TIME * 0.49)
        assert not spy.calls
        advance(scene.fx, spy, FLIP_TIME * 0.02)
        assert [cue for _, cue in spy.calls] == ["card_flip"]
        advance(scene.fx, spy, 1)
        assert len(spy.calls) == 1
    finally:
        app.audio = original


@pytest.mark.parametrize("outcome,busted,chips,banner,delta", [
    ("player", False, "chips_win", "round_win", 10),
    ("dealer", False, "chips_lose", "round_lose", -10),
    ("dealer", True, "chips_lose", "bust", -10),
    ("blackjack", False, "chips_win", "blackjack", 15),
    ("push", False, None, "push", 0),
])
def test_settle_and_banner_cues_wait_for_their_existing_tweens(app, outcome, busted, chips, banner, delta):
    original = app.audio
    try:
        scene, spy = table(app)
        result = RoundResult(1, outcome, 22 if busted else 19, 17, busted, 10, delta, 100 + delta, None)
        scene.fx.react(Notice(N.ROUND_SETTLED, data={"result": result}))
        wait = scene.fx.settle.tween.delay
        assert not spy.calls
        advance(scene.fx, spy, wait - 0.001)
        assert not spy.calls
        advance(scene.fx, spy, 0.002)
        assert [cue for _, cue in spy.calls] == ([chips] if chips else [])
        advance(scene.fx, spy, SETTLE_TIME * 0.8)
        assert spy.calls[-1][1] == banner and scene.fx.banner.started
        if chips:
            assert spy.calls[0][0] < spy.calls[-1][0]
        advance(scene.fx, spy, 2)
        assert len(spy.calls) == (2 if chips else 1)
    finally:
        app.audio = original


def test_chaos_sound_starts_with_glitch_and_rejections_are_silent(app):
    original = app.audio
    try:
        scene, spy = table(app)
        scene.fx.react(Notice(N.CHAOS_ACTION_REJECTED))
        assert not spy.calls
        scene.fx.react(Notice(N.RULE_MODIFIER_APPLIED))
        assert spy.calls == [(0, "chaos_glitch")] and scene.fx.glitch.started
        advance(scene.fx, spy, 1)
        assert len(spy.calls) == 1
        scene.fx.react(Notice(N.ITEM_USED))
        assert spy.calls[-1][1] == "item_use"
    finally:
        app.audio = original


def test_button_click_opt_out_and_chip_click_use_shared_audio(app):
    spy = AudioSpy()
    app.assets.audio = spy
    button = Button(app.assets, (0, 0, 100, 40), "Test")
    button.click()
    Button(app.assets, (0, 0, 100, 40), "Silent", sound=False).click()
    Button(app.assets, (0, 0, 100, 40), "Disabled", enabled=False).click()
    assert spy.calls == [(0, "button_click")]
    from chaos_blackjack.gui.components.bet_panel import BetPanel
    panel = BetPanel(app.assets, (640, 600), lambda amount: None)
    panel.set_limits(1, 50)
    chip_button = panel.chips[0]
    panel.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": chip_button.rect.center, "button": 1}))
    assert spy.calls[-1][1] == "chip_place"


def test_global_keys_update_preferences_and_f5_refreshes_sounds(app, monkeypatch):
    refreshes = []
    monkeypatch.setattr(app.audio, "refresh", lambda: refreshes.append("audio"))
    monkeypatch.setattr(app.assets, "refresh", lambda: refreshes.append("images"))
    def key(code):
        app._dispatch(pygame.event.Event(pygame.KEYDOWN, {"key": code}))
    key(pygame.K_m)
    assert app.prefs.muted
    key(pygame.K_MINUS)
    assert app.prefs.master_volume == 0.3 and app.prefs.muted
    key(pygame.K_m)
    assert not app.prefs.muted and app.audio.effective_volume == 0.3
    key(pygame.K_F5)
    assert refreshes == ["images", "audio"]


def test_next_round_does_not_replay_old_settle_cues_or_change_tween_timing(app):
    original = app.audio
    try:
        scene, spy = table(app)
        result = RoundResult(1, "player", 19, 17, False, 10, 10, 110, None)
        scene.fx.react(Notice(N.ROUND_SETTLED, data={"result": result}))
        pending = list(scene.fx.anim.tweens)
        timing = [(t.duration, t.delay, t.blocking) for t in pending]
        scene.fx.view_changed(replace(scene.view, phase=TablePhase.ROUND_OVER), scene.view)
        assert scene.fx.anim.tweens == pending
        assert [(t.duration, t.delay, t.blocking) for t in pending] == timing
        advance(scene.fx, spy, 2)
        assert not spy.calls
    finally:
        app.audio = original
