"""Providers are evaluated on every query; newly registered content is visible."""

from __future__ import annotations

from collections.abc import Callable

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex.models import CodexEntry, CodexKind

CodexProvider = Callable[[RunConfig], list[CodexEntry]]

_KINDS = {
    "rule": CodexKind("rule", "Chaos rules", 0),
    "mode": CodexKind("mode", "Game modes", 1),
    "item": CodexKind("item", "Items", 2),
    "ai": CodexKind("ai", "Chaos AI", 3),
    "build": CodexKind("build", "Build", 4),
    "environment": CodexKind("environment", "Environment rules", 5),
}
_PROVIDERS: dict[str, list[CodexProvider]] = {}


def register_codex_provider(kind: str, fn: CodexProvider) -> None:
    """Append a provider, once per callable. Later entries can override an id.

    Plugins can supply presentation metadata or new kinds without modifying
    the built-in providers. Unknown kinds get a human-readable tab label.
    """
    if not kind or not callable(fn):
        raise ValueError("A codex provider needs a kind and a callable")
    _KINDS.setdefault(kind, CodexKind(kind, kind.replace("_", " ").title(), len(_KINDS)))
    providers = _PROVIDERS.setdefault(kind, [])
    if fn not in providers:
        providers.append(fn)


def _ensure_providers() -> None:
    from chaos_blackjack.codex.providers import install

    install()


def codex_kinds() -> list[CodexKind]:
    _ensure_providers()
    return sorted(_KINDS.values(), key=lambda k: (k.order, k.id))


def codex_entries(kind: str | None = None, config: RunConfig | None = None) -> list[CodexEntry]:
    _ensure_providers()
    cfg = config if config is not None else RunConfig()
    entries: dict[tuple[str, str], CodexEntry] = {}
    for k in codex_kinds():
        if kind is not None and kind != k.id:
            continue
        for provider in tuple(_PROVIDERS.get(k.id, ())):
            for entry in provider(cfg):
                if entry.kind != k.id:
                    raise ValueError(f"Provider for {k.id!r} returned kind {entry.kind!r}")
                entries[(entry.kind, entry.id)] = entry
    return sorted(entries.values(), key=lambda e: (_KINDS[e.kind].order, e.order, e.name, e.id))
