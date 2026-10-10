"""Audio output boundary; game logic never imports a mixer."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AudioBackend(Protocol):
    available: bool

    def play(self, path: Path, gain: float) -> bool:
        """Start a clip without blocking; False means unavailable or dropped."""
        ...

    def set_volume(self, volume: float) -> None:
        """Update the master gain of current and future clips."""
        ...

    def stop(self) -> None:
        ...

    def close(self) -> None:
        ...
