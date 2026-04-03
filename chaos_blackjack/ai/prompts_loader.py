"""Load prompt templates from chaos_blackjack.ai.prompts."""

from __future__ import annotations

from importlib import resources


def load_prompt(name: str) -> str:
    """Load ``{name}.txt`` from package data."""
    path = resources.files("chaos_blackjack.ai") / "prompts" / f"{name}.txt"
    return path.read_text(encoding="utf-8")
