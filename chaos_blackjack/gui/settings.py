"""GUI settings — window, frame rate and where to look for art."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from chaos_blackjack.audio.catalog import DEFAULT_MASTER_VOLUME

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Everything is laid out on this fixed canvas, then scaled to the window.
LOGICAL_SIZE = (1280, 720)


def default_asset_dirs() -> tuple[Path, ...]:
    """Searched in order; the first file whose name matches an asset id wins.

    `CHAOS_ASSETS_DIR` (os.pathsep-separated) is checked before the defaults.
    """
    dirs: list[Path] = []
    env = os.environ.get("CHAOS_ASSETS_DIR", "").strip()
    if env:
        dirs.extend(Path(p) for p in env.split(os.pathsep) if p)
    dirs.append(PROJECT_ROOT / "assets")
    dirs.append(PROJECT_ROOT / "black-jack-assets" / "exports")
    return tuple(dirs)


@dataclass(frozen=True)
class GuiSettings:
    title: str = "Chaos Blackjack"
    window_size: tuple[int, int] = LOGICAL_SIZE
    fps: int = 60
    fullscreen: bool = False
    asset_dirs: tuple[Path, ...] = field(default_factory=default_asset_dirs)
    balance_profile: str | None = None  # None = $CHAOS_PROFILE, else "default"
    master_volume: float = DEFAULT_MASTER_VOLUME
    audio_muted: bool = False
