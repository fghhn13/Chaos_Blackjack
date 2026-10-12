"""Bundled table hosts (presentation only, independent of Chaos rule selection).

A mode names its host (docs/design/AI_MODES.md). The only bundled host is
Poker Head; he hosts Classic (without bending rules) and his own mode.
"""

from functools import lru_cache
import json
from pathlib import Path

from chaos_blackjack.content.ai_profile import Persona


@lru_cache(maxsize=1)
def default_persona() -> Persona:
    folder = Path(__file__).resolve().parents[1] / "ai"
    data = json.loads((folder / "personas/poker_head.json").read_text(encoding="utf-8"))
    return Persona(
        id="default_poker_head",
        name=data["name"],
        portraits={key: folder / value for key, value in data["portraits"].items()},
        moods=data["moods"],
        lines={key: tuple(value) for key, value in data["lines"].items()},
        default=data["default"],
    )


HOSTS = ("poker_head",)
HOST_NAMES = {"poker_head": "Poker Head"}


def host_persona(host: str | None) -> Persona:
    """The persona of a bundled host. Runs from before hosts (None) and hosts
    this version no longer ships fall back to Poker Head."""
    return default_persona()


default_persona()  # register the bundled portraits (asset ids default_poker_head_<expression>)
