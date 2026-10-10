"""Optional GUI audio: first asset directory wins, failures are always silent."""

from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol

import pygame

from chaos_blackjack.gui.assets.sound_manifest import DEFAULT_MASTER_VOLUME, MANIFEST


class AudioPreferences(Protocol):
    master_volume: float
    muted: bool


class SoundManager:
    def __init__(self, asset_dirs, *, preferences: AudioPreferences | None = None,
                 clock=time.monotonic, rng: random.Random | None = None) -> None:
        self.asset_dirs = tuple(Path(folder) for folder in asset_dirs)
        self.preferences = preferences if preferences is not None else SimpleNamespace(
            master_volume=DEFAULT_MASTER_VOLUME, muted=False,
        )
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()
        self._files: dict[str, tuple[int, Path]] = {}
        self._sounds: dict[Path, pygame.mixer.Sound] = {}
        self._last_played: dict[str, float] = {}
        self._channels: list = []
        self._gains: list[float] = []
        self._owns_mixer = False
        self.available = False
        self.refresh()
        # A dummy driver is explicitly silent, even if it accepts mixer calls.
        if os.environ.get("SDL_AUDIODRIVER", "").lower() == "dummy":
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                self._owns_mixer = True
            start = pygame.mixer.get_num_channels()
            pygame.mixer.set_num_channels(start + 8)
            self._channels = [pygame.mixer.Channel(i) for i in range(start, start + 8)]
            self._gains = [1.0] * len(self._channels)
            self.available = True
        except (pygame.error, AttributeError, NotImplementedError):
            pass

    @property
    def volume(self) -> float:
        return self.preferences.master_volume

    @property
    def muted(self) -> bool:
        return self.preferences.muted

    @property
    def effective_volume(self) -> float:
        return 0.0 if self.muted else self.volume

    def set_volume(self, value: float) -> None:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Master volume must be finite")
        self.preferences.master_volume = max(0.0, min(1.0, value))
        try:
            for channel, gain in zip(self._channels, self._gains):
                channel.set_volume(self.effective_volume * gain)
        except (pygame.error, AttributeError, NotImplementedError):
            self.available = False
        if self.effective_volume == 0:
            self.stop()

    def set_muted(self, muted: bool) -> None:
        self.preferences.muted = bool(muted)
        if self.muted:
            self.stop()
        self.set_volume(self.volume)

    def toggle_mute(self) -> None:
        self.set_muted(not self.muted)

    def refresh(self) -> None:
        """F5: stop old clips, rescan sounds/ subfolders and invalidate caches."""
        self.stop()
        files = {}
        for priority, folder in enumerate(self.asset_dirs):
            try:
                for path in sorted(folder.rglob("*")):
                    if (path.is_file() and path.parent.name == "sounds"
                            and path.suffix.lower() in (".ogg", ".wav")
                            and not any(part.startswith(".") for part in path.relative_to(folder).parts)):
                        files.setdefault(path.stem, (priority, path))
            except OSError:
                continue
        self._files = files
        self._sounds.clear()
        self._last_played.clear()

    def paths(self, sound_id: str) -> tuple[Path, ...]:
        spec = MANIFEST.get(sound_id)
        names = (sound_id, *spec.variants) if spec else (sound_id,)
        matches = [(name, self._files[name]) for name in names if name in self._files]
        if not matches:
            return ()
        priority = min(item[1][0] for item in matches)
        # An exact semantic id in the winning directory overrides its variants.
        exact = self._files.get(sound_id)
        if exact is not None and exact[0] == priority:
            return (exact[1],)
        return tuple(path for _, (rank, path) in matches if rank == priority)

    def play(self, sound_id: str) -> bool:
        if not self.available or self.effective_volume <= 0:
            return False
        family = next((key for key, spec in MANIFEST.items() if sound_id in spec.variants), sound_id)
        now = self._clock()
        if now - self._last_played.get(family, float("-inf")) < 0.05 - 1e-9:
            return False
        paths = self.paths(sound_id)
        if not paths:
            return False
        try:
            if pygame.mixer.get_init() is None:
                return False
            path = self._rng.choice(paths)
            sound = self._sounds.get(path)
            if sound is None:
                sound = pygame.mixer.Sound(str(path))
                self._sounds[path] = sound
            gain = MANIFEST[family].gain if family in MANIFEST else 0.8
            for index, channel in enumerate(self._channels):
                if not channel.get_busy():
                    channel.play(sound)
                    channel.set_volume(self.effective_volume * gain)
                    self._gains[index] = gain
                    self._last_played[family] = now
                    return True
        except (pygame.error, OSError, AttributeError, NotImplementedError):
            pass
        return False

    def stop(self) -> None:
        try:
            for channel in self._channels:
                channel.stop()
        except (pygame.error, AttributeError, NotImplementedError):
            pass

    def close(self) -> None:
        self.stop()
        self._sounds.clear()
        if self._owns_mixer:
            pygame.mixer.quit()
        self.available = False
