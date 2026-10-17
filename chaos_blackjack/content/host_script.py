"""What a mode's host says at the table: random scripts from a line library.

Each bundled host has `chaos_blackjack/ai/hosts/<host>.json`: per event
(`intro`, `victory`, `defeat`) a list of alternative scripts, each a list of
[mood, text] beats; a mood is one of the host's portrait expressions. A key
`<event>.<mode id>` (e.g. `intro.normal`) replaces the event for one mode, so
a host can sound different at a table where it bends no rules; a key
`<event>.<variant>` (e.g. `victory.capture`, named by the table's
`host_variant`) replaces it for one way a run ends. Adding lines is data only. Design: docs/design/AI_MODES.md §3.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HOST_EVENTS = ("intro", "victory", "defeat")
_FOLDER = Path(__file__).resolve().parents[1] / "ai" / "hosts"


@dataclass(frozen=True)
class HostLine:
    mood: str
    text: str


@lru_cache(maxsize=None)
def _library(host: str) -> dict:
    path = _FOLDER / f"{host}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in data:
        event = key.split(".", 1)[0]
        if event not in HOST_EVENTS:
            continue
        for script in data[key]:
            if not script or any(len(beat) != 2 or not all(isinstance(x, str) and x for x in beat)
                                 for beat in script):
                raise ValueError(f"Host {host}: every {event} script needs [mood, text] beats")
    return data


def _resolve(host: str | None) -> str:
    """Runs from before hosts, and hosts without a library, use Poker Head's."""
    return host if host and (_FOLDER / f"{host}.json").is_file() else "poker_head"


def _scripts(library: dict, event: str, mode: str, variant: str) -> list:
    """The variant's scripts, else the mode's, else the event's."""
    return ((library.get(f"{event}.{variant}") if variant else None)
            or (library.get(f"{event}.{mode}") if mode else None) or library.get(event, []))


def host_script(host: str | None, event: str, rng: random.Random | None = None, *,
                mode: str = "", variant: str = "") -> list[HostLine]:
    """One random script for `event` (a variant's or the mode's own scripts first); [] when the host has none."""
    if event not in HOST_EVENTS:
        raise ValueError(f"Unknown host event {event!r}; events: {', '.join(HOST_EVENTS)}")
    library = _library(_resolve(host))
    scripts = _scripts(library, event, mode, variant)
    if not scripts:
        return []
    return [HostLine(mood, text) for mood, text in (rng or random).choice(scripts)]


def host_profile(host: str | None) -> tuple[tuple[str, ...], str]:
    """The host's character profile (paragraphs) and signature line, for the Collection."""
    library = _library(_resolve(host))
    return tuple(library.get("profile", ())), str(library.get("signature", ""))


def summary_mood(host: str | None) -> str:
    """The mood for generated lines (goal and rules)."""
    return _library(_resolve(host)).get("summary_mood", "calm")


def host_scripts(host: str | None, event: str, *, mode: str = "", variant: str = "") -> list[list[HostLine]]:
    """Every script `host_script` may pick (for tests and tools)."""
    scripts = _scripts(_library(_resolve(host)), event, mode, variant)
    return [[HostLine(m, t) for m, t in s] for s in scripts]
