"""Schedule cues and translate notices; no audio device or game mutation here."""

from __future__ import annotations

import heapq
import math
from pathlib import Path

from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.audio.catalog import ASSET_ROOT, DEFAULT_MASTER_VOLUME, checked_volume, load_catalog
from chaos_blackjack.contracts.audio import AudioBackend


class SilentAudioBackend:
    available = False

    def play(self, path: Path, gain: float) -> bool:
        return False

    def set_volume(self, volume: float) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


class AudioManager:
    def __init__(
        self, backend: AudioBackend | None = None, *, volume: float = DEFAULT_MASTER_VOLUME,
        muted: bool = False, asset_root: Path = ASSET_ROOT,
    ) -> None:
        self.backend = backend if backend is not None else SilentAudioBackend()
        self.catalog = load_catalog(asset_root)
        self.volume = checked_volume(volume)
        self.muted = bool(muted)
        self._time = 0.0
        self._sequence = 0
        self._variants: dict[str, int] = {}
        self._pending: list[tuple[float, int, str]] = []
        self._in_chaos = False
        self.backend.set_volume(self.effective_volume)

    @property
    def effective_volume(self) -> float:
        return 0.0 if self.muted else self.volume

    @property
    def available(self) -> bool:
        return self.backend.available

    def set_volume(self, volume: float) -> None:
        self.volume = checked_volume(volume)
        self.backend.set_volume(self.effective_volume)
        if self.effective_volume == 0:
            self.stop()

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)
        self.backend.set_volume(self.effective_volume)
        if self.muted:
            self.stop()

    def toggle_mute(self) -> None:
        self.set_muted(not self.muted)

    def play(self, cue_id: str, *, delay: float = 0.0) -> bool:
        if cue_id not in self.catalog:
            raise ValueError(f"Unknown sound cue: {cue_id}")
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("Sound delay must be finite and nonnegative")
        if self.effective_volume == 0 or not self.available:
            return False
        if delay:
            self._sequence += 1
            heapq.heappush(self._pending, (self._time + delay, self._sequence, cue_id))
            return True
        return self._play_now(cue_id)

    def _play_now(self, cue_id: str) -> bool:
        cue = self.catalog[cue_id]
        index = self._variants.get(cue_id, 0)
        self._variants[cue_id] = index + 1
        return self.backend.play(cue.files[index % len(cue.files)], cue.gain)

    def update(self, dt: float) -> None:
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("Audio frame delta must be finite and nonnegative")
        self._time += dt
        while self._pending and self._pending[0][0] <= self._time:
            _, _, cue_id = heapq.heappop(self._pending)
            if self.effective_volume > 0 and self.available:
                self._play_now(cue_id)

    def handle_notice(self, notice: Notice) -> None:
        if notice.kind == NoticeKind.PHASE_CHANGED:
            self._in_chaos = notice.data.get("to") == "chaos"
        elif notice.kind == NoticeKind.ROUND_STARTED:
            self.stop()  # no delayed clips from the previous round
            self.play("chips")
            for index in range(4):
                self.play("deal", delay=0.08 * (index + 1))
        elif notice.kind == NoticeKind.DRAW_CARD:
            self.play("deal")
        elif notice.kind == NoticeKind.DOUBLED:
            self.play("chips")
        elif notice.kind == NoticeKind.RULE_MODIFIER_APPLIED:
            self.play("chaos")
        elif notice.kind == NoticeKind.ITEM_USED and self._in_chaos:
            self.play("chaos")
        elif notice.kind == NoticeKind.ROUND_SETTLED:
            result = notice.data.get("result")
            outcome = result.get("outcome") if isinstance(result, dict) else getattr(result, "outcome", None)
            if outcome in ("player", "blackjack"):
                self.play("win")
            elif outcome in ("dealer", "surrender"):
                self.play("lose")

    def stop(self) -> None:
        self._pending.clear()
        self.backend.stop()

    def close(self) -> None:
        self.stop()
        self.backend.close()
