"""Import plugin subpackages so register_* side effects run."""

from __future__ import annotations

import importlib
import pkgutil


def auto_load_plugins() -> None:
    """Load chaos_blackjack.items and chaos_blackjack.rules.plugins (non-private modules)."""
    _walk_and_import("chaos_blackjack.items")
    _walk_and_import("chaos_blackjack.rules.plugins")


def _walk_and_import(package_name: str) -> None:
    try:
        package = importlib.import_module(package_name)
    except ImportError:
        return
    if not hasattr(package, "__path__"):
        return
    for _finder, name, ispkg in pkgutil.walk_packages(
        package.__path__,
        package.__name__ + ".",
    ):
        if name.rsplit(".", 1)[-1].startswith("_"):
            continue
        importlib.import_module(name)
