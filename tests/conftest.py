"""Shared fixtures — plugins loaded once per test session."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Tests must never make billed API calls, whatever the local .env says
# (.env loading never overrides variables that are already set).
os.environ["CHAOS_USE_LLM"] = "0"
# ...and never read or write the player's data/game.db.
os.environ["CHAOS_DB"] = ":memory:"
os.environ.pop("CHAOS_PROFILE", None)
# Meta upgrades are off in this version; their dormant code keeps its tests (tests of the "off" state unset it).
os.environ["CHAOS_META_UPGRADES"] = "1"

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chaos_blackjack.registry.loader import auto_load_plugins


@pytest.fixture(scope="session", autouse=True)
def load_plugins() -> None:
    auto_load_plugins()
