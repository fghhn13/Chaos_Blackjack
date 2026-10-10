"""Tweens: time-based 0→1 progress with easing, driven by Scene.update(dt).

Animations are presentation only. Game state changes instantly in the
controller; a scene reads `Tween.value` while drawing to place things
between where they were and where the state says they are.

    fx = Animator()
    t = fx.add(Tween(0.3, ease=out_back, delay=0.1))
    fx.update(dt)            # every frame
    x = lerp(x0, x1, t.value)
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

Ease = Callable[[float], float]


# ---------------------------------------------------------------- easing


def linear(t: float) -> float:
    return t


def out_quad(t: float) -> float:
    return 1 - (1 - t) * (1 - t)


def out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def in_out_cubic(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def out_back(t: float, overshoot: float = 1.70158) -> float:
    c3 = overshoot + 1
    return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2


def out_elastic(t: float) -> float:
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_point(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return lerp(a[0], b[0], t), lerp(a[1], b[1], t)


# ----------------------------------------------------------------- tween


@dataclass(eq=False)
class Tween:
    duration: float
    ease: Ease = out_cubic
    delay: float = 0.0
    on_done: Callable[[], None] | None = None
    # Blocking tweens hold back automatic game steps (dealer, chaos AI)
    # until they finish; they never block player input.
    blocking: bool = True
    tag: str = ""
    elapsed: float = field(default=0.0, init=False)

    @property
    def started(self) -> bool:
        return self.elapsed >= self.delay

    @property
    def raw(self) -> float:
        """Linear progress 0..1 (0 during the delay)."""
        if self.duration <= 0:
            return 1.0 if self.started else 0.0
        return max(0.0, min(1.0, (self.elapsed - self.delay) / self.duration))

    @property
    def value(self) -> float:
        """Eased progress."""
        return self.ease(self.raw)

    @property
    def done(self) -> bool:
        return self.elapsed >= self.delay + self.duration

    def finish(self) -> None:
        self.elapsed = self.delay + self.duration


class Animator:
    def __init__(self) -> None:
        self.tweens: list[Tween] = []

    def add(self, tween: Tween) -> Tween:
        self.tweens.append(tween)
        return tween

    def update(self, dt: float) -> None:
        for t in list(self.tweens):
            t.elapsed += dt
            if t.done:
                self.tweens.remove(t)
                if t.on_done is not None:
                    t.on_done()

    @property
    def busy(self) -> bool:
        return any(t.blocking for t in self.tweens)

    def cancel(self, tag: str) -> None:
        self.tweens = [t for t in self.tweens if t.tag != tag]

    def finish_all(self) -> None:
        for t in self.tweens:
            t.finish()
        self.update(0.0)


__all__ = [
    "Animator", "Ease", "Tween", "in_out_cubic", "lerp", "lerp_point",
    "linear", "out_back", "out_cubic", "out_elastic", "out_quad",
]
