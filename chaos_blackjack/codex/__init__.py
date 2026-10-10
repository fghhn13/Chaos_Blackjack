"""Registry-backed reference entries and deterministic controller replays."""

from chaos_blackjack.codex.demo import run_demo
from chaos_blackjack.codex.models import CodexEntry, CodexKind, DemoFrame, DemoScript, DemoStep
from chaos_blackjack.codex.registry import codex_entries, codex_kinds, register_codex_provider
from chaos_blackjack.codex.providers import install as _install

_install()

__all__ = [
    "CodexEntry", "CodexKind", "DemoFrame", "DemoScript", "DemoStep",
    "codex_entries", "codex_kinds", "register_codex_provider", "run_demo",
]
