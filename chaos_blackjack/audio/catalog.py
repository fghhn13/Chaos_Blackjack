"""Sound cue metadata and offline provenance checks (standard library only)."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parent / "assets"
DEFAULT_MASTER_VOLUME = 0.4


def checked_volume(value: float) -> float:
    volume = float(value)
    if not math.isfinite(volume) or not 0.0 <= volume <= 1.0:
        raise ValueError("Volume must be a finite number between 0 and 1")
    return volume


@dataclass(frozen=True)
class Cue:
    files: tuple[Path, ...]
    gain: float
    description: str


def load_catalog(root: Path = ASSET_ROOT) -> dict[str, Cue]:
    data = json.loads((root / "cues.json").read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise ValueError("Unsupported audio cue schema")
    if checked_volume(data["default_master_volume"]) != DEFAULT_MASTER_VOLUME:
        raise ValueError("Cue manifest and default master volume disagree")
    catalog = {}
    for cue_id, cue in data["cues"].items():
        filenames = cue["files"]
        if not filenames or any(not isinstance(name, str) or Path(name).name != name for name in filenames):
            raise ValueError(f"Invalid clip names for cue {cue_id}")
        catalog[cue_id] = Cue(
            tuple(root / "kenney" / name for name in filenames),
            checked_volume(cue["gain"]), str(cue["description"]),
        )
    return catalog


def validate_assets(root: Path = ASSET_ROOT) -> dict:
    catalog = load_catalog(root)
    source = json.loads((root / "kenney" / "source.json").read_text(encoding="utf-8"))
    if source.get("license") != "CC0-1.0":
        raise ValueError("Expected documented CC0 source")
    license_text = (root / "kenney" / "License.txt").read_text(encoding="utf-8-sig")
    if "CC0" not in license_text or "Kenney" not in license_text:
        raise ValueError("Missing original Kenney CC0 license")
    for filename, metadata in source["files"].items():
        if Path(filename).name != filename:
            raise ValueError(f"Invalid provenance filename: {filename}")
        data = (root / "kenney" / filename).read_bytes()
        if not data.startswith(b"OggS"):
            raise ValueError(f"Not an OGG stream: {filename}")
        if len(data) != metadata["bytes"] or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
            raise ValueError(f"Source checksum mismatch: {filename}")
    for cue_id, cue in catalog.items():
        if any(path.name not in source["files"] for path in cue.files):
            raise ValueError(f"Cue {cue_id} references an undocumented source")
    return {"ok": True, "source": source["source_url"], "license": source["license"],
            "files": len(source["files"]), "cues": list(catalog),
            "default_master_volume": DEFAULT_MASTER_VOLUME}
