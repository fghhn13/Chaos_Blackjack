"""Load permission profiles bundled under chaos_blackjack.ai.permissions."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_permission_profile(name: str) -> dict[str, Any]:
    """Load ``{name}.json`` from package data (e.g. easy, hard)."""
    root = resources.files("chaos_blackjack.ai") / "permissions" / f"{name}.json"
    text = root.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("permission profile must be a JSON object")
    return data
