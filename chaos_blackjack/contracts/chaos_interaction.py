"""Immutable inputs and outputs for a portrait conversation."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PokeRequest:
    context_json: str
    intent: Literal["guide", "mislead"]  # Internal; never displayed to the player.


@dataclass(frozen=True)
class PokeReply:
    text: str
    ok: bool = True


@dataclass(frozen=True)
class PokeOutcome:
    request: PokeRequest
    reply: PokeReply
