"""LLM backend protocol — swap stub / OpenAI / local without changing pipeline."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...
