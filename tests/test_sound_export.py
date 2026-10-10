"""Use the approved source clips for export checks; no generated audio fixtures."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from chaos_blackjack.gui.assets.sound_manifest import MANIFEST
_script = Path(__file__).resolve().parents[1] / "scripts/export_sounds.py"
_spec = importlib.util.spec_from_file_location("export_sounds", _script)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
main = _module.main

ASSETS = Path(__file__).resolve().parents[1] / "assets/sounds"


def test_delivered_manifest_covers_every_id_and_original_bytes():
    report = json.loads((ASSETS / "manifest.json").read_text())
    assert not report["missing_cues"]
    assert {row["cue"] for row in report["files"]} == set(MANIFEST)
    pygame.mixer.init()
    try:
        for row in report["files"]:
            data = (ASSETS / row["file"]).read_bytes()
            assert data.startswith(b"OggS")
            assert hashlib.sha256(data).hexdigest() == row["source_sha256"] == row["sha256"]
            assert len(data) == row["bytes"] < 200 * 1024
            assert pygame.mixer.Sound(str(ASSETS / row["file"])).get_length() == pytest.approx(row["seconds"], abs=0.001)
            assert row["license"] == "CC0-1.0" and row["normalized_peak"] is None
    finally:
        pygame.mixer.quit()


def source_plan(tmp_path):
    source = tmp_path / "source"
    (source / "pack/Audio").mkdir(parents=True)
    (source / "pack/Audio/flip.ogg").write_bytes((ASSETS / "card_flip.ogg").read_bytes())
    (source / "pack/License.txt").write_bytes((ASSETS / "licenses/kenney-casino.txt").read_bytes())
    plan = {"schema": 1, "selection_approved": "2026-10-10",
            "packs": {"test": {"folder": "pack", "license": "CC0-1.0", "url": "https://kenney.nl/assets/casino-audio"}},
            "cues": {"card_flip": {"pack": "test", "files": ["Audio/flip.ogg"]}}}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    return source, path


def test_export_copies_without_overwriting_and_dry_run_writes_nothing(tmp_path, capsys):
    source, plan = source_plan(tmp_path)
    out = tmp_path / "delivery"
    argv = ["--plan", str(plan), "--source-root", str(source), "--out", str(out)]
    assert main([*argv, "--dry-run"]) == 0 and not out.exists()
    assert main(argv) == 0
    assert main(["--out", str(out), "--verify"]) == 0
    before = (out / "card_flip.ogg").read_bytes()
    assert before == (source / "pack/Audio/flip.ogg").read_bytes()
    assert main(argv) == 1
    assert (out / "card_flip.ogg").read_bytes() == before
    assert main(["--plan", str(plan), "--source-root", str(source), "--out", str(source / "outputs")]) == 1
    (out / "card_flip.ogg").write_bytes(before + b"tampered test copy")
    assert main(["--out", str(out), "--verify"]) == 1
    capsys.readouterr()


def test_optional_normalization_converts_original_clip_to_wav(tmp_path, capsys):
    source, plan = source_plan(tmp_path)
    out = tmp_path / "normalized"
    assert main(["--plan", str(plan), "--source-root", str(source), "--out", str(out), "--normalize", "0.8"]) == 0
    assert (out / "card_flip.wav").read_bytes().startswith(b"RIFF")
    import array
    import wave
    with wave.open(str(out / "card_flip.wav")) as wav:
        samples = array.array("h", wav.readframes(wav.getnframes()))
    assert max(abs(value) for value in samples) / 32767 == pytest.approx(0.8, abs=0.001)
    assert (source / "pack/Audio/flip.ogg").read_bytes() == (ASSETS / "card_flip.ogg").read_bytes()
    capsys.readouterr()
