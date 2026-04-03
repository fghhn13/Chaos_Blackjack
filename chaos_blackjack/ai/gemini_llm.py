"""Google Gemini backend for ChaosPipeline — reads API key from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from chaos_blackjack.contracts.llm import LLMBackend


def load_dotenv_from_project_root() -> None:
    """Load ``.env`` from repository root (next to ``pyproject.toml``)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")


@dataclass
class GeminiLLM:
    """Calls Gemini with ``system_instruction`` + user turn (JSON-only contract)."""

    model_name: str = "gemini-2.0-flash"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import google.generativeai as genai

        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt,
        )
        generation_config = None
        try:
            generation_config = genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=256,
            )
        except Exception:
            generation_config = None

        if generation_config is not None:
            response = model.generate_content(
                user_prompt,
                generation_config=generation_config,
            )
        else:
            response = model.generate_content(user_prompt)
        try:
            text = response.text
        except ValueError:
            return '{"action":"noop"}'
        if not text or not text.strip():
            return '{"action":"noop"}'
        return text.strip()


def try_create_gemini_llm() -> LLMBackend | None:
    """
    If ``GOOGLE_API_KEY`` / ``GEMINI_API_KEY`` is set (e.g. via ``.env``), return GeminiLLM.

    Callers (e.g. ``GameLoop``) should only invoke this when ``CHAOS_USE_GEMINI`` is enabled;
    otherwise return None so callers use StubLLM.
    """
    load_dotenv_from_project_root()
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key or not str(key).strip():
        return None
    import google.generativeai as genai

    genai.configure(api_key=str(key).strip())
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
    return GeminiLLM(model_name=model)
