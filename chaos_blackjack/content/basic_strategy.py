"""Blackjack basic strategy — the chart the tutorial shows (dealer stands on all 17s, late surrender).

Cells: "H" hit, "S" stand, "D" double (hit when you cannot), "DS" double (stand when you cannot),
"R" surrender (hit when you cannot). Rows are your hand, columns the dealer's up card. The same
decisions as the simulator's basic-strategy bot (black-jack-sim, bjsim/bots.py).
"""

from __future__ import annotations

DEALER_COLUMNS: tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "A")

CELL_NAMES = {"H": "Hit", "S": "Stand", "D": "Double", "DS": "Double", "R": "Surrender"}
CELL_LEGEND: tuple[tuple[str, str], ...] = (
    ("H", "Hit"), ("S", "Stand"), ("D", "Double, or hit"), ("DS", "Double, or stand"), ("R", "Surrender, or hit"),
)


def _row(spec: str) -> tuple[str, ...]:
    cells = tuple(spec.split())
    assert len(cells) == len(DEALER_COLUMNS), spec
    return cells


#                      2  3  4  5  6  7  8  9  10 A
HARD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("5-8", _row("H  H  H  H  H  H  H  H  H  H")),
    ("9",   _row("H  D  D  D  D  H  H  H  H  H")),
    ("10",  _row("D  D  D  D  D  D  D  D  H  H")),
    ("11",  _row("D  D  D  D  D  D  D  D  D  H")),
    ("12",  _row("H  H  S  S  S  H  H  H  H  H")),
    ("13",  _row("S  S  S  S  S  H  H  H  H  H")),
    ("14",  _row("S  S  S  S  S  H  H  H  H  H")),
    ("15",  _row("S  S  S  S  S  H  H  H  R  H")),
    ("16",  _row("S  S  S  S  S  H  H  R  R  R")),
    ("17+", _row("S  S  S  S  S  S  S  S  S  S")),
)
SOFT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("A,2", _row("H  H  H  D  D  H  H  H  H  H")),
    ("A,3", _row("H  H  H  D  D  H  H  H  H  H")),
    ("A,4", _row("H  H  D  D  D  H  H  H  H  H")),
    ("A,5", _row("H  H  D  D  D  H  H  H  H  H")),
    ("A,6", _row("H  D  D  D  D  H  H  H  H  H")),
    ("A,7", _row("S  DS DS DS DS S  S  H  H  H")),
    ("A,8", _row("S  S  S  S  S  S  S  S  S  S")),
    ("A,9", _row("S  S  S  S  S  S  S  S  S  S")),
)


def column(up_card: str) -> int:
    """The column of a dealer up card's rank ("J", "Q", "K" read as 10)."""
    rank = "10" if up_card in ("J", "Q", "K") else up_card
    return DEALER_COLUMNS.index(rank)


def cell(total: int, soft: bool, up_card: str) -> str:
    """The chart's cell for a two-or-more-card hand of `total` (soft = an ace counted as 11)."""
    col = column(up_card)
    if soft and 13 <= total <= 20:
        return SOFT[total - 13][1][col]
    if total <= 8:
        return HARD[0][1][col]
    if total >= 17:
        return HARD[-1][1][col]
    return HARD[total - 8][1][col]


def advice(total: int, soft: bool, up_card: str, *, can_double: bool = True, can_surrender: bool = True) -> str:
    """The action the chart recommends right now: "hit", "stand", "double" or "surrender"."""
    c = cell(total, soft, up_card)
    if c == "R":
        return "surrender" if can_surrender else "hit"
    if c in ("D", "DS"):
        return "double" if can_double else ("stand" if c == "DS" else "hit")
    return "stand" if c == "S" else "hit"


__all__ = ["CELL_LEGEND", "CELL_NAMES", "DEALER_COLUMNS", "HARD", "SOFT", "advice", "cell", "column"]
