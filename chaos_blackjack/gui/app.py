"""App — window, main loop, logical-canvas scaling, shared services.

Scenes draw on a fixed 1280x720 canvas (`settings.LOGICAL_SIZE`). The App
scales it into the real window with letterboxing and converts mouse
positions back, so scenes only ever see canvas coordinates.

Global keys: F11 fullscreen, F5 rescan assets/sounds, M mute, +/- volume.
"""

from __future__ import annotations

import sqlite3

from dataclasses import dataclass

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.assets import AssetManager
from chaos_blackjack.gui.audio import SoundManager
from chaos_blackjack.gui.assets.sound_manifest import DEFAULT_MASTER_VOLUME
from chaos_blackjack.gui.scene import SceneManager
from chaos_blackjack.data.balance import load_balance
from chaos_blackjack.data.prefs import get_pref, set_pref
from chaos_blackjack.gui.settings import LOGICAL_SIZE, GuiSettings
from chaos_blackjack.app.config import RunConfig

_MOUSE_EVENTS = (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)


@dataclass
class Preferences:
    """Choices made in menus that later scenes read; kept in data/game.db."""

    enable_chaos: bool = False
    master_volume: float = DEFAULT_MASTER_VOLUME
    muted: bool = False

    @classmethod
    def load(cls) -> "Preferences":
        return cls(enable_chaos=bool(get_pref("gui.enable_chaos", False)))

    def save(self) -> None:
        try:
            set_pref("gui.enable_chaos", self.enable_chaos)
        except (sqlite3.Error, OSError):
            pass  # a preference that cannot be stored is not worth a crash


class App:
    def __init__(self, settings: GuiSettings | None = None, *, run_config: RunConfig | None = None) -> None:
        self.settings = settings or GuiSettings()
        pygame.init()
        pygame.display.set_caption(self.settings.title)
        self.fullscreen = self.settings.fullscreen
        self.window = self._open_window()
        self.canvas = pygame.Surface(LOGICAL_SIZE).convert()
        self.clock = pygame.time.Clock()
        self.assets = AssetManager(self.settings.asset_dirs)
        self.balance = load_balance(self.settings.balance_profile)
        self.run_config = run_config or RunConfig.from_balance(self.balance)
        self.prefs = Preferences.load()
        if run_config is not None:
            self.prefs.enable_chaos = run_config.enable_chaos
        self.prefs.master_volume = self.settings.master_volume
        self.prefs.muted = self.settings.audio_muted
        self.audio = SoundManager(self.settings.asset_dirs, preferences=self.prefs)
        self.assets.audio = self.audio
        self.scenes = SceneManager(self)
        self.running = False
        self._viewport = pygame.Rect((0, 0), LOGICAL_SIZE)
        self._update_viewport()

    # ------------------------------------------------------------- lifecycle

    def run(self, first_scene: str = "menu", *, max_frames: int | None = None, **params) -> None:
        import chaos_blackjack.gui.scenes  # noqa: F401  (registers scenes)

        self.scenes.reset(first_scene, **params)
        self.scenes.apply_pending()
        self.running = True
        frames = 0
        try:
            while self.running and self.scenes.top is not None:
                dt = self.clock.tick(self.settings.fps) / 1000.0
                for event in pygame.event.get():
                    self._dispatch(event)
                self.scenes.update(dt)
                self.scenes.apply_pending()
                self._render()
                frames += 1
                if max_frames is not None and frames >= max_frames:
                    break
        finally:
            self.audio.close()
            pygame.quit()

    def quit(self) -> None:
        self.running = False

    # ---------------------------------------------------------------- events

    def _dispatch(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self._update_viewport()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            self.toggle_fullscreen()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
            self.assets.refresh()
            self.audio.refresh()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
            self.audio.toggle_mute()
            return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.adjust_volume(-0.1)
            return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.adjust_volume(0.1)
            return
        if event.type in _MOUSE_EVENTS:
            event = pygame.event.Event(event.type, {**event.dict, "pos": self.to_canvas(event.pos)})
        self.scenes.handle_event(event)

    def adjust_volume(self, delta: float) -> None:
        self.audio.set_volume(round(min(1.0, max(0.0, self.audio.volume + delta)), 2))

    def to_canvas(self, pos: tuple[int, int]) -> tuple[int, int]:
        vp = self._viewport
        x = (pos[0] - vp.x) * LOGICAL_SIZE[0] / max(1, vp.w)
        y = (pos[1] - vp.y) * LOGICAL_SIZE[1] / max(1, vp.h)
        return int(x), int(y)

    def mouse_pos(self) -> tuple[int, int]:
        return self.to_canvas(pygame.mouse.get_pos())

    # --------------------------------------------------------------- display

    def _open_window(self) -> pygame.Surface:
        if self.fullscreen:
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        return pygame.display.set_mode(self.settings.window_size, pygame.RESIZABLE)

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self.window = self._open_window()
        self._update_viewport()

    def _update_viewport(self) -> None:
        ww, wh = pygame.display.get_surface().get_size()
        k = min(ww / LOGICAL_SIZE[0], wh / LOGICAL_SIZE[1])
        w, h = int(LOGICAL_SIZE[0] * k), int(LOGICAL_SIZE[1] * k)
        self._viewport = pygame.Rect((ww - w) // 2, (wh - h) // 2, w, h)

    def _render(self) -> None:
        self.canvas.fill(theme.DARK)
        self.scenes.draw(self.canvas)
        window = pygame.display.get_surface()
        if window.get_size() != self._viewport.size or self._viewport.topleft != (0, 0):
            window.fill((0, 0, 0))
        if self._viewport.size == LOGICAL_SIZE:
            window.blit(self.canvas, self._viewport)
        else:
            window.blit(pygame.transform.smoothscale(self.canvas, self._viewport.size), self._viewport)
        pygame.display.flip()
