"""Layouts — which parts a table shows, and where.

A layout names parts (app/parts.py, or native GUI components) for three
places: the left and right columns beside the cards (stacked top to bottom,
usually the `compact` variant) and the tabs of the run panel (`full`). An
entry is "<part id>" or "<part id>:<variant>". The play area in the middle
is the same at every table and is not part of a layout.

A mode sets `GameMode.layout`; modes without one use DEFAULT_LAYOUT. A table
with its own mechanics usually starts from the default and inserts its parts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PanelTab:
    id: str
    label: str
    parts: tuple[str, ...]
    hotkey: str = ""        # a letter that opens the panel on this tab


@dataclass(frozen=True)
class Layout:
    left: tuple[str, ...]
    right: tuple[str, ...]
    panel: tuple[PanelTab, ...]

    def tab(self, tab_id: str) -> PanelTab | None:
        return next((t for t in self.panel if t.id == tab_id), None)


def split_entry(entry: str, default_variant: str) -> tuple[str, str]:
    part, _, variant = entry.partition(":")
    return part, variant or default_variant


BAG = PanelTab("bag", "Bag", ("core.items",), hotkey="i")
RULES = PanelTab("rules", "Rules", ("core.rules",))
LOG = PanelTab("log", "Log", ("core.log",), hotkey="l")
RUN = PanelTab("run", "Run", ("core.run_stats",))

DEFAULT_LAYOUT = Layout(
    left=("core.host", "core.rules:compact", "core.feed"),
    right=("core.deck_pile", "core.items:compact", "core.buttons"),
    panel=(BAG, RULES, LOG, RUN),
)


def layout_for(mode_id: str) -> Layout:
    """The layout of a mode (the default for unknown or layout-less modes)."""
    from chaos_blackjack.modes import get_mode

    try:
        return get_mode(mode_id).layout or DEFAULT_LAYOUT
    except KeyError:
        return DEFAULT_LAYOUT
