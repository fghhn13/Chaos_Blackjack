"""Widget data — the small fixed vocabulary that table information is drawn with.

A *part* (app/parts.py) turns game state into widgets; the GUI has one
renderer per widget `kind` and never needs to know which table or mechanic a
widget came from. Widgets are plain frozen data (no logic, no pygame).

Kinds: stat, badges, bars, progress, list, rows, slots, log.
`tone` is a presentation hint: "" (normal), good, bad, warn, chaos, muted, gold.
A clickable element carries an `Act`: the GUI sends it back through
`GameController.perform` (or handles a `gui:` act itself) without knowing
what it does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Act:
    """A command an element sends when clicked: `id` (e.g. "use_item",
    "gui:panel"), an optional argument, and whether it is allowed right now."""

    id: str
    arg: str = ""
    enabled: bool = True


@dataclass(frozen=True)
class Stat:
    label: str
    value: str
    icon: str = ""          # asset id
    tone: str = ""
    tooltip: str = ""
    kind: str = "stat"


@dataclass(frozen=True)
class Badge:
    icon: str               # asset id
    text: str
    tooltip: str = ""
    tone: str = ""
    act: Act | None = None


@dataclass(frozen=True)
class Badges:
    items: tuple[Badge, ...]
    title: str = ""
    kind: str = "badges"


@dataclass(frozen=True)
class Bar:
    label: str
    value: int
    tone: str = ""


@dataclass(frozen=True)
class Bars:
    bars: tuple[Bar, ...]
    title: str = ""
    note: str = ""
    compact: bool = False   # a strip of thin bars without labels (side columns)
    act: Act | None = None  # clicking the widget
    baseline: int | None = None   # a reference value drawn as a line (e.g. a standard deck's 4)
    baseline_label: str = ""
    kind: str = "bars"


@dataclass(frozen=True)
class Progress:
    label: str
    value: int
    maximum: int
    tone: str = ""
    title: str = ""
    kind: str = "progress"


@dataclass(frozen=True)
class Entry:
    title: str
    text: str = ""
    icon: str = ""          # asset id
    tone: str = ""
    tooltip: str = ""
    badge: str = ""         # short tag shown on the right (e.g. a count or a trigger)
    act: Act | None = None


@dataclass(frozen=True)
class ListWidget:
    entries: tuple[Entry, ...]
    title: str = ""
    empty: str = ""
    compact: bool = False   # icons only, details in tooltips
    kind: str = "list"


@dataclass(frozen=True)
class Row:
    label: str
    value: str
    tone: str = ""


@dataclass(frozen=True)
class Rows:
    rows: tuple[Row, ...]
    title: str = ""
    kind: str = "rows"


@dataclass(frozen=True)
class Slot:
    icon: str               # asset id
    count: int = 1
    tooltip: str = ""
    hotkey: str = ""        # "1".."9"
    act: Act | None = None


@dataclass(frozen=True)
class Slots:
    slots: tuple[Slot, ...]
    title: str = ""
    empty: str = ""
    columns: int = 4
    kind: str = "slots"


@dataclass(frozen=True)
class LogLine:
    round: int
    category: str
    text: str


@dataclass(frozen=True)
class Log:
    lines: tuple[LogLine, ...]
    categories: tuple[str, ...] = ()
    title: str = ""
    kind: str = "log"


Widget = Union[Stat, Badges, Bars, Progress, ListWidget, Rows, Slots, Log]

TONES = ("", "good", "bad", "warn", "chaos", "muted", "gold")
