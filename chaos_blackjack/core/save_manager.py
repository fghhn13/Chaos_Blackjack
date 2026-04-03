"""Save/load manager for Menu Driven + State Driven entry."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from chaos_blackjack.core.run_state import RunSaveData


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAVE_DIR = PROJECT_ROOT / "chaos_blackjack" / "saves"


def _ensure_dir() -> None:
    os.makedirs(SAVE_DIR, exist_ok=True)


def normalize_save_name(name: str) -> str:
    n = name.strip()
    if not n:
        return "save_1.json"
    if not n.lower().endswith(".json"):
        n = n + ".json"
    return n


def list_saves() -> list[str]:
    _ensure_dir()
    files = []
    for p in SAVE_DIR.glob("*.json"):
        files.append(p.name)
    return sorted(files)


def save_game(data: RunSaveData, name: str = "save_1.json") -> Path:
    _ensure_dir()
    fname = normalize_save_name(name)
    path = SAVE_DIR / fname
    payload: dict[str, Any] = data.to_dict()
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    return path


def load_game(name: str) -> RunSaveData:
    fname = normalize_save_name(name)
    path = SAVE_DIR / fname
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("save file must contain a JSON object")
    return RunSaveData.from_dict(payload)

