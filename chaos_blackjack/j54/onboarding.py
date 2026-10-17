"""J-54's first visit: when each explanation is due, and its beats (docs/design/TUTORIAL.md section 8).

The table calls the moment functions below at four points of a run (`run_started` before the firmware choice,
`firmware_offered` as it opens, `entered_betting` for the first "Next condition" announcement and the first
betting phase in which Release is affordable); each milestone is cued at most once per run. `take` hands the
cues out with J-54's lines (ai/hosts/j54.json, `onboarding`) through `J54Table.onboarding`, and the GUI shows
those a guided player has not reached yet. Nothing here knows about players: the GUI says whether the player is
guided, and an unguided one gets nothing.

The meter hint is not a milestone: the first betting phase of a run in which the meter reaches its second band,
a guided player sees one line beside the meter (`meter_hint`, read by the snapshot).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.content.host_script import HostLine, host_onboarding
from chaos_blackjack.meta.onboarding import (
    J54_INTRO_CONDITION as CONDITION, J54_INTRO_FIRMWARE as FIRMWARE, J54_INTRO_RELEASE as RELEASE,
    J54_INTRO_TABLE as TABLE,
)

if TYPE_CHECKING:
    from chaos_blackjack.j54.table import J54Table

MILESTONES = (TABLE, FIRMWARE, CONDITION, RELEASE)

# What lights up while a milestone's beats show (HostLine.focus: layout parts, or "<part>/<element icon>").
FOCUS: dict[str, tuple[str, ...]] = {
    TABLE: ("j54.deck",),
    CONDITION: ("j54.badges/j54_next", "core.rules"),
    RELEASE: ("j54.ops/j54_release",),
}

# The profile numbers J-54's lines may name ({compute_income}, ...).
_NUMBERS = ("compute_income", "compute_cap", "cut_size", "hot_purge_size", "release_cost", "target_from_round",
            "capture_from_round", "rounds")


@dataclass
class Guide:
    """The table's onboarding state: cues not handed out yet, milestones cued this run (neither is saved: a
    resumed run never repeats a beat because the GUI recorded the milestone when it was shown), and the round
    of the meter hint (saved, so the hint stays once per run)."""

    guided: bool = False
    cues: list[str] = field(default_factory=list)
    cued: set[str] = field(default_factory=set)
    hint_round: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"hint_round": self.hint_round}

    def restore(self, data: dict[str, Any]) -> None:
        """A resumed run: drop the start's cues (a restore rebuilds the table through `start`)."""
        self.cues, self.cued = [], set()
        hint = data.get("hint_round")
        self.hint_round = int(hint) if hint is not None else None


def _cue(table: "J54Table", milestone: str) -> None:
    guide = table.guide
    if milestone not in guide.cued:
        guide.cued.add(milestone)
        guide.cues.append(milestone)


# --------------------------------------------------------------------------- the moments


def run_started(table: "J54Table") -> None:
    """A new run, before the firmware choice: the table, the heat strip, compute and the two goals."""
    _cue(table, TABLE)


def firmware_offered(table: "J54Table") -> None:
    """The firmware choice opens."""
    _cue(table, FIRMWARE)


def entered_betting(table: "J54Table") -> None:
    """A round's betting phase (after income and the program): the first announcement; Release affordable."""
    from chaos_blackjack.j54.table import SEALED

    if table.announcement:
        _cue(table, CONDITION)
    if table.joker == SEALED and table.compute >= table._int("release_cost"):  # noqa: SLF001
        _cue(table, RELEASE)


# --------------------------------------------------------------------------- handing out


def beats(table: "J54Table", milestone: str) -> tuple[HostLine, ...]:
    """J-54's lines for a milestone, with the profile's numbers and the elements they light up."""
    numbers = {key: table.settings[key] for key in _NUMBERS}
    focus = FOCUS.get(milestone, ())
    return tuple(replace(line, text=line.text.format(**numbers), focus=focus)
                 for line in host_onboarding("j54", milestone))


def take(table: "J54Table", guided: bool) -> tuple[tuple[str, tuple[HostLine, ...]], ...]:
    """The explanations cued since the last call, handed out once ((milestone, beats); none for an unguided
    player). Also notes the meter hint's round for a guided player."""
    cues, table.guide.cues = table.guide.cues, []
    table.guide.guided = guided
    if not guided:
        return ()
    _note_hint(table)
    return tuple((m, beats(table, m)) for m in cues)


def _second_band(table: "J54Table") -> tuple[int, int] | None:
    from chaos_blackjack.j54.public import parse_bands

    bands = parse_bands(table.settings["bands"])
    return bands[1] if len(bands) > 1 else None


def _note_hint(table: "J54Table") -> None:
    from chaos_blackjack.j54.public import measure

    guide, band = table.guide, _second_band(table)
    if guide.hint_round is not None or band is None or table.c.phase != TablePhase.BETTING or table.c.choice:
        return
    if measure(table)[0].win * 100 >= band[0]:
        guide.hint_round = table.entered_round


def meter_hint(table: "J54Table", suggested: int) -> str | None:
    """The line beside the meter in the betting phase it first reached the second band (guided players only)."""
    guide, band = table.guide, _second_band(table)
    if (not guide.guided or band is None or guide.hint_round != table.entered_round
            or table.c.phase != TablePhase.BETTING):
        return None
    return f"The meter says {band[1]}% of the bankroll: {suggested} chips."


__all__ = ["CONDITION", "FIRMWARE", "FOCUS", "Guide", "MILESTONES", "RELEASE", "TABLE", "beats", "entered_betting",
           "firmware_offered", "meter_hint", "run_started", "take"]
