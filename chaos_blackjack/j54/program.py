"""J-54's program: the schedule of conditions over the run (docs/design/J54_V2_SPEC.md section 3).

The program is drawn once from the run seed and saved with the run. Segments
of `segment_len` rounds (e.g. 2 to 4) cover every round; each segment has one
condition, never the same one twice in a row. The first is a classic one when
`classic_opening` is on, and the number of camp switches is one of
`cross_switches`: a classic <-> anti switch counts 1, a switch to or from the
loner counts half (the halves are summed, then rounded down).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

ATTEMPTS = 5000  # rule sequences tried before taking the closest to the drawn switch count


@dataclass(frozen=True)
class Segment:
    rule: str
    start: int    # first round
    length: int

    @property
    def end(self) -> int:
        """Last round."""
        return self.start + self.length - 1

    def to_list(self) -> list[Any]:
        return [self.rule, self.start, self.length]


@dataclass(frozen=True)
class Program:
    segments: tuple[Segment, ...]

    def index_at(self, round_no: int) -> int:
        """The segment playing at `round_no` (the last one after the end)."""
        for i, s in enumerate(self.segments):
            if round_no <= s.end:
                return i
        return len(self.segments) - 1

    def at(self, round_no: int) -> Segment:
        return self.segments[self.index_at(round_no)]

    def next_after(self, round_no: int) -> Segment | None:
        i = self.index_at(round_no) + 1
        return self.segments[i] if i < len(self.segments) else None

    def to_list(self) -> list[list[Any]]:
        return [s.to_list() for s in self.segments]

    @staticmethod
    def from_list(data: Sequence[Sequence[Any]]) -> "Program":
        return Program(tuple(Segment(str(r), int(start), int(length)) for r, start, length in data))


def int_range(text: Any) -> tuple[int, int]:
    """"2,4" -> (2, 4); "3" -> (3, 3)."""
    parts = [int(x) for x in str(text).split(",") if x.strip()]
    if not parts:
        raise ValueError(f"Expected a number or a range like '2,4', got {text!r}")
    return min(parts), max(parts)


def switches(camps: Sequence[str]) -> int:
    """Camp switches of a sequence: classic <-> anti counts 1, to or from the loner a half."""
    full = half = 0
    for a, b in zip(camps, camps[1:]):
        if a == b:
            continue
        if "loner" in (a, b):
            half += 1
        else:
            full += 1
    return full + half // 2


def _lengths(rng: random.Random, rounds: int, lo: int, hi: int) -> list[int]:
    out: list[int] = []
    left = rounds
    while left > 0:
        fits = [n for n in range(lo, hi + 1) if n == left or left - n >= lo]
        n = rng.choice(fits) if fits else left
        out.append(n)
        left -= n
    return out


def generate(seed: Any, rounds: int, camps: Mapping[str, str], segment_len: tuple[int, int],
             cross_switches: tuple[int, int], classic_opening: bool) -> Program:
    """The run's program. `camps` maps each condition of the pool to its camp."""
    if not camps:
        raise ValueError("J-54's program needs at least one condition")
    rng = random.Random(f"{seed}:j54:program")
    lengths = _lengths(rng, rounds, *segment_len)
    target = rng.randint(*cross_switches)
    pool = sorted(camps)
    opening = [r for r in pool if camps[r] == "classic"] if classic_opening else []
    best: tuple[int, list[str]] | None = None   # (distance to the target, rules)
    for _ in range(ATTEMPTS):
        rules = [rng.choice(opening or pool)]
        while len(rules) < len(lengths):
            rules.append(rng.choice([r for r in pool if r != rules[-1]] or pool))
        miss = abs(switches([camps[r] for r in rules]) - target)
        if best is None or miss < best[0]:
            best = (miss, rules)
        if miss == 0:
            break
    assert best is not None
    segments, start = [], 1
    for rule, n in zip(best[1], lengths):
        segments.append(Segment(rule, start, n))
        start += n
    return Program(tuple(segments))
