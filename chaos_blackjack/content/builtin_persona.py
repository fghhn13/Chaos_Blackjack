"""Bundled default dealer presentation, independent of Chaos rule selection."""

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
