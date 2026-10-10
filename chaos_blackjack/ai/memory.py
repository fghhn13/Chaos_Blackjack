"""Bounded run-local history. Disabled stores neither collect nor export data."""

from collections import deque
from dataclasses import asdict, is_dataclass
import json


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Unsupported memory value: {type(value).__name__}")


class ChaosMemory:
    def __init__(self, *, enabled: bool = False, limit: int = 32):
        if limit < 1:
            raise ValueError("Chaos memory limit must be positive")
        self.enabled = enabled
        self._entries: deque[str] = deque(maxlen=limit)

    def record(self, round_no: int, kind: str, details: dict) -> None:
        if self.enabled:
            self._entries.append(json.dumps(
                {"round": round_no, "kind": kind, "details": details},
                ensure_ascii=False, default=_json_default,
            ))

    def export(self) -> list[dict] | None:
        return [json.loads(entry) for entry in self._entries] if self.enabled else None

    def restore(self, entries: list[dict] | None) -> None:
        self._entries.clear()
        if self.enabled:
            for entry in (entries or [])[-self._entries.maxlen:]:
                self.record(int(entry["round"]), str(entry["kind"]), dict(entry["details"]))
