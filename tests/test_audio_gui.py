"""Mixer decoding, live master gain and GUI notice wiring with dummy SDL."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.audio import AudioManager
from chaos_blackjack.audio.catalog import ASSET_ROOT
from chaos_blackjack.audio.pygame_backend import PygameAudioBackend
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.core.game_state import Card, GamePhase, GameState, Rank
from chaos_blackjack.gui.app import App
from chaos_blackjack.gui.settings import GuiSettings


def test_all_original_clips_decode_and_live_channels_obey_master_volume():
    backend = PygameAudioBackend()
    try:
        assert backend.available, backend.last_error
        clips = list((ASSET_ROOT / "kenney").glob("*.ogg"))
        assert len(clips) == 54
        assert all(pygame.mixer.Sound(str(path)).get_length() > 0 for path in clips)
        audio = AudioManager(backend)
        assert audio.play("chaos")
        channel = backend._channels[0]
        assert channel.get_volume() == pytest.approx(0.4 * 0.65, abs=0.01)
        audio.set_volume(0.2)
        assert channel.get_volume() == pytest.approx(0.2 * 0.65, abs=0.01)
        audio.toggle_mute()
        assert not backend.busy
        # Invalid files fail silently in the optional backend, not in game logic.
        assert not backend.play(ASSET_ROOT / "missing.ogg", 1)
        assert backend.last_error
    finally:
        backend.close()
        pygame.quit()


def test_missing_audio_device_does_not_prevent_gui(monkeypatch, tmp_path):
    pygame.quit()
    def unavailable(*args, **kwargs):
        raise pygame.error("No test audio device")
    monkeypatch.setattr(pygame.mixer, "init", unavailable)
    # pygame.init attempts the actual mixer separately; force the adapter retry path.
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    app = App(GuiSettings(asset_dirs=(tmp_path,)))
    try:
        assert not app.audio.available
        app.run(max_frames=1)
    finally:
        app.audio.close()
        pygame.quit()


def test_settings_mouse_and_global_audio_keys_keep_saved_volume(tmp_path):
    app = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes
    try:
        app.scenes.reset("meta_settings")
        app.scenes.apply_pending()
        settings = app.scenes.top
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            app._dispatch(pygame.event.Event(kind, {"pos": settings.mute.rect.center, "button": 1}))
        assert app.audio.muted and app.audio.volume == 0.4
        def key(code):
            app._dispatch(pygame.event.Event(pygame.KEYDOWN, {"key": code}))
        key(pygame.K_PLUS)
        assert app.audio.muted and app.audio.volume == 0.5
        key(pygame.K_m)
        assert not app.audio.muted and app.audio.effective_volume == 0.5
        for _ in range(20):
            key(pygame.K_MINUS)
        assert app.audio.volume == 0
        for _ in range(20):
            key(pygame.K_KP_PLUS)
        assert app.audio.volume == 1
        app._render()
        assert "100%" in settings.mute.text
    finally:
        app.audio.close()
        pygame.quit()


def test_table_fans_notices_to_audio_once_without_consuming_feed(tmp_path):
    app = App(GuiSettings(asset_dirs=(tmp_path,)))
    import chaos_blackjack.gui.scenes
    cues = []
    app.audio.play = lambda cue, **kwargs: cues.append(cue) or True
    try:
        controller = GameController(RunConfig(seed=3, use_llm=False))
        def fixed_round(seed=None, *, inventory_override=None):
            return GameState(tuple(Card(Rank(r)) for r in ("A", "K")),
                             tuple(Card(Rank(r)) for r in ("9", "7")), (), GamePhase.PLAYER_TURN)
        controller.loop.new_round = fixed_round
        app.scenes.reset("table", controller=controller)
        app.scenes.apply_pending()
        table = app.scenes.top
        table._deal(10)
        assert cues == ["card_deal"]
        table.fx.update(2)
        assert cues.count("card_deal") == 4
        assert cues.count("chip_stack") == 1
        assert cues.count("blackjack") == 1
        assert table.view.last_result.outcome == "blackjack"
        assert table.feed.lines  # audio did not steal the existing event stream
        table._pump_notices()
        played = list(cues)
        table.fx.update(2)
        assert cues == played
        app.scenes.reset("home")
        app.scenes.apply_pending()
        assert type(app.scenes.top).__name__ == "HomeScene"
    finally:
        app.audio.close()
        pygame.quit()
