"""Bundled table hosts (presentation only, independent of Chaos rule selection).

A mode names its host (docs/design/AI_MODES.md). Poker Head hosts Classic
(without bending rules) and his own mode; J-54 hosts its deck table. Each
host is `ai/personas/<host>.json` with portraits under `ai/assets/<host>/`.
"""

from functools import lru_cache
import json
from pathlib import Path

from chaos_blackjack.content.ai_profile import Persona

_FOLDER = Path(__file__).resolve().parents[1] / "ai"

HOSTS = ("poker_head", "j54")
HOST_NAMES = {"poker_head": "Poker Head", "j54": "J-54"}
# Persona ids keep Poker Head's original one, so his asset ids stay default_poker_head_<expression>.
_PERSONA_IDS = {"poker_head": "default_poker_head", "j54": "host_j54"}


@lru_cache(maxsize=None)
def _load(host: str) -> Persona:
    data = json.loads((_FOLDER / f"personas/{host}.json").read_text(encoding="utf-8"))
    return Persona(
        id=_PERSONA_IDS[host],
        name=data["name"],
        portraits={key: _FOLDER / value for key, value in data["portraits"].items()},
        moods=data["moods"],
        lines={key: tuple(value) for key, value in data["lines"].items()},
        default=data["default"],
    )


def default_persona() -> Persona:
    return _load("poker_head")


def host_persona(host: str | None) -> Persona:
    """The persona of a bundled host. Runs from before hosts (None) and hosts
    this version no longer ships fall back to Poker Head."""
    return _load(host) if host in HOSTS else default_persona()


for _host in HOSTS:
    _load(_host)  # register the bundled portraits (asset ids <persona id>_<expression>)
