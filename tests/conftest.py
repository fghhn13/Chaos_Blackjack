"""Shared fixtures — plugins loaded once per test session."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chaos_blackjack.registry.loader import auto_load_plugins


@pytest.fixture(scope="session", autouse=True)
def load_plugins() -> None:
    auto_load_plugins()
