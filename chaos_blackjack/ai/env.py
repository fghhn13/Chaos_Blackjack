"""Project `.env` loading (stdlib only) and small env helpers.

Parser follows gptsapi-agent-starter: `NAME=value` / `export NAME=value`
lines, `#` comments, optional matching quotes. Variables already set in the
process environment win over the file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _ASSIGNMENT.match(line)
        if not m:
            continue  # ignore malformed lines rather than failing the game
        name, value = m.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[name] = value
    return values


def load_dotenv_from_project_root(path: Path | None = None) -> None:
    """Load `.env` from the repository root into os.environ (no overrides)."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for name, value in parse_env_file(env_path).items():
        os.environ.setdefault(name, value)


def env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")
