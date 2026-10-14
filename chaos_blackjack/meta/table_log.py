"""TableLog — writes every table notice of a player's run to a JSON Lines file.

One file per run, `data/table_logs/run-<run id>.jsonl` beside the database,
appended to when a saved run is continued. Each line is one notice with the
round, phase, cash and (at tables that have them) net assets at that moment,
so a played run can be read back for balance work. Like RunTracker it listens
without consuming notices. Only runs kept in a database file are logged
(tests and in-memory services write nothing).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.notices import Notice

if TYPE_CHECKING:
    from chaos_blackjack.app.controller import GameController


def _plain(value: Any) -> Any:
    """A JSON-safe copy of notice data (dataclasses become dicts; anything else unknown becomes text)."""
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


class TableLog:
    def __init__(self, controller: "GameController", path: Path) -> None:
        self.controller = controller
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("a", encoding="utf-8")
        cfg = controller.config
        self._write({"event": "attached", "mode": cfg.mode, "profile": cfg.balance_profile, "seed": cfg.seed,
                     "start_money": cfg.start_money, "target_money": controller.run.target_money})
        controller.add_listener(self.on_notice)

    def on_notice(self, n: Notice) -> None:
        self._write({"kind": n.kind, "text": n.text, "data": _plain(dict(n.data))})

    def _write(self, record: dict[str, Any]) -> None:
        c = self.controller
        line = {"t": round(time.time(), 3), "round": c.run.round, "phase": c.phase.value, "money": c.run.money}
        table = c.table
        if table is not None and hasattr(table, "net_assets"):
            line["net_assets"] = table.net_assets()
        line.update(record)
        try:
            self._file.write(json.dumps(line, ensure_ascii=False) + "\n")
            self._file.flush()
        except (OSError, ValueError):
            pass  # a log must never break the game

    def detach(self) -> None:
        self.controller.remove_listener(self.on_notice)
        try:
            self._file.close()
        except OSError:
            pass
