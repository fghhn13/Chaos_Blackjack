"""Application layer — UI-agnostic run controller shared by CLI and GUI."""

from __future__ import annotations

_EXPORTS = {
    "GameController": "chaos_blackjack.app.controller",
    "ActionError": "chaos_blackjack.app.controller",
    "RunConfig": "chaos_blackjack.app.config",
    "GameView": "chaos_blackjack.app.view",
    "TablePhase": "chaos_blackjack.app.view",
    "Action": "chaos_blackjack.app.view",
    "Notice": "chaos_blackjack.app.notices",
    "NoticeKind": "chaos_blackjack.app.notices",
}


def __getattr__(name: str):
    # Lazy so that `chaos_blackjack.ui` can import app helpers without cycles.
    mod = _EXPORTS.get(name)
    if mod is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(mod), name)


__all__ = list(_EXPORTS)
