#!/usr/bin/env python3
"""
One Gemini completion (needs GOOGLE_API_KEY in .env).
Run: python scripts/debug_gemini.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chaos_blackjack.ai.gemini_llm import load_dotenv_from_project_root, try_create_gemini_llm


def main() -> None:
    load_dotenv_from_project_root()
    llm = try_create_gemini_llm()
    if llm is None:
        print("No GOOGLE_API_KEY / GEMINI_API_KEY — set .env and retry.")
        sys.exit(1)
    out = llm.complete(
        "You reply with JSON only: {\"action\":\"noop\"}",
        "Say noop.",
    )
    print("Response:")
    print(out)


if __name__ == "__main__":
    main()
