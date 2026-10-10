"""Optional mixer adapter. Device/clip failures degrade to silent playback."""

from __future__ import annotations

from pathlib import Path


class PygameAudioBackend:
    def __init__(self) -> None:
        self.available = False
        self.last_error = ""
        self._volume = 0.4
        self._sounds: dict[Path, object] = {}
        self._channels: list = []
        self._gains: list[float] = []
        self._owns_mixer = False
        try:
            import pygame
        except ImportError as exc:
            self.last_error = str(exc)
            return
        self._pygame = pygame
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                self._owns_mixer = True
            start = pygame.mixer.get_num_channels()
            pygame.mixer.set_num_channels(start + 8)
            self._channels = [pygame.mixer.Channel(index) for index in range(start, start + 8)]
            self._gains = [1.0] * len(self._channels)
            self.available = True
        except pygame.error as exc:
            self.last_error = str(exc)

    def play(self, path: Path, gain: float) -> bool:
        if not self.available:
            return False
        try:
            sound = self._sounds.get(path)
            if sound is None:
                sound = self._pygame.mixer.Sound(str(path))
                self._sounds[path] = sound
            for index, channel in enumerate(self._channels):
                if not channel.get_busy():
                    self._gains[index] = gain
                    channel.play(sound)
                    channel.set_volume(self._volume * gain)
                    return True
            return False  # bounded overlap; never cut off an existing cue
        except (self._pygame.error, OSError) as exc:
            self.last_error = str(exc)
            return False

    @property
    def busy(self) -> bool:
        if not self.available:
            return False
        try:
            return any(channel.get_busy() for channel in self._channels)
        except self._pygame.error:
            return False

    def set_volume(self, volume: float) -> None:
        self._volume = volume
        if self.available:
            try:
                for channel, gain in zip(self._channels, self._gains):
                    channel.set_volume(volume * gain)
            except self._pygame.error as exc:
                self.available = False
                self.last_error = str(exc)

    def stop(self) -> None:
        if self.available:
            try:
                for channel in self._channels:
                    channel.stop()
            except self._pygame.error as exc:
                self.available = False
                self.last_error = str(exc)

    def close(self) -> None:
        self.stop()
        self._sounds.clear()
        if self._owns_mixer:
            self._pygame.mixer.quit()
        self.available = False
