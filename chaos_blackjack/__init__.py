"""Chaos Blackjack — registry-driven plugin architecture (v2)."""

__version__ = "0.2.0"


def __getattr__(name: str):
    if name == "auto_load_plugins":
        from chaos_blackjack.registry.loader import auto_load_plugins

        return auto_load_plugins
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["auto_load_plugins", "__version__"]
