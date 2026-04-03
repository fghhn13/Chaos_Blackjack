#!/usr/bin/env python3
"""List Gemini models that support generateContent (uses GOOGLE_API_KEY from .env)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(ROOT / ".env")

import google.generativeai as genai

key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not key or not str(key).strip():
    print("No GOOGLE_API_KEY / GEMINI_API_KEY in environment or .env", file=sys.stderr)
    sys.exit(1)

genai.configure(api_key=key.strip())

print("Models with generateContent:\n")
for m in genai.list_models():
    methods = getattr(m, "supported_generation_methods", []) or []
    if "generateContent" in methods:
        print(m.name)
