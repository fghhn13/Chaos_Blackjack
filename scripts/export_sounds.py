"""Export an approved sound plan; standard library + pygame, no audio generation.

Copies original OGG/WAV by default. Optional --normalize decodes existing clips
and writes peak-normalized WAV. Originals and existing exports are never overwritten.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import sys
import wave

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

from chaos_blackjack.gui.assets.sound_manifest import MANIFEST


def prepare(plan: dict, source_root: Path, out: Path, *, normalize: float | None = None) -> list[dict]:
    if plan.get("schema") != 1 or not plan.get("selection_approved"):
        raise ValueError("Expected a version 1, explicitly approved sound plan")
    if normalize is not None and not 0 < normalize <= 1:
        raise ValueError("Normalization peak must be in (0, 1]")
    source_root, out = source_root.resolve(), out.resolve()
    if out.is_relative_to(source_root):
        raise ValueError("Export directory must not be inside the raw sound source directory")
    rows = []
    for cue_id, choice in plan["cues"].items():
        spec = MANIFEST[cue_id]
        pack = plan["packs"][choice["pack"]]
        if pack["license"] not in ("CC0-1.0", "CC-BY-3.0", "CC-BY-4.0"):
            raise ValueError("Only documented CC0 or CC BY sources may be exported")
        filenames = choice["files"]
        if len(filenames) > 1 and len(filenames) != len(spec.variants):
            raise ValueError(f"Wrong number of variants for {cue_id}")
        ids = spec.variants if len(filenames) > 1 else (cue_id,)
        for export_id, filename in zip(ids, filenames):
            source = (source_root / pack["folder"] / filename).resolve()
            if not source.is_relative_to(source_root) or source.suffix.lower() not in (".ogg", ".wav"):
                raise ValueError(f"Invalid source: {filename}")
            sound = pygame.mixer.Sound(str(source))  # decode only; never play
            data = source.read_bytes()
            suffix = ".wav" if normalize is not None else source.suffix.lower()
            target = out / f"{export_id}{suffix}"
            # Never allow an older alternate-format clip to shadow a new export.
            if any((out / f"{export_id}{ext}").exists() for ext in (".ogg", ".wav")):
                raise FileExistsError(f"Export already exists: {export_id}")
            samples = array.array("h", sound.get_raw())
            peak = max((abs(value) for value in samples), default=0) / 32768
            rows.append({"id": export_id, "cue": cue_id, "source": source.relative_to(source_root).as_posix(),
                         "source_url": pack["url"], "license": pack["license"],
                         "seconds": round(sound.get_length(), 4), "source_bytes": len(data),
                         "source_sha256": hashlib.sha256(data).hexdigest(), "peak": round(peak, 4),
                         "file": target.name, "_source": source, "_target": target, "_samples": samples})
    return rows


def export(plan: dict, source_root: Path, out: Path, rows: list[dict], normalize: float | None) -> list[dict]:
    licenses = []
    for pack_id in {choice["pack"] for choice in plan["cues"].values()}:
        pack = plan["packs"][pack_id]
        source = source_root / pack["folder"] / "License.txt"
        target = out / "licenses" / f"kenney-{pack_id}.txt"
        if target.exists():
            raise FileExistsError(f"License export already exists: {target}")
        licenses.append((source.read_bytes(), target))
    if (out / "manifest.json").exists():
        raise FileExistsError("Sound provenance manifest already exists")
    out.mkdir(parents=True, exist_ok=True)
    report = []
    for row in rows:
        target = row["_target"]
        if normalize is None:
            with target.open("xb") as output:
                output.write(row["_source"].read_bytes())
        else:
            frequency, sample_format, channels = pygame.mixer.get_init()
            if sample_format != -16:
                raise ValueError("Normalization requires signed 16-bit mixer samples")
            samples = row["_samples"]
            peak = max((abs(value) for value in samples), default=0)
            gain = normalize * 32767 / peak if peak else 1
            adjusted = array.array("h", (max(-32768, min(32767, round(value * gain))) for value in samples))
            if sys.byteorder != "little":
                adjusted.byteswap()
            with target.open("xb") as output, wave.open(output, "wb") as wav:
                wav.setparams((channels, 2, frequency, 0, "NONE", "not compressed"))
                wav.writeframes(adjusted.tobytes())
        data = target.read_bytes()
        metadata = {key: value for key, value in row.items() if not key.startswith("_")}
        metadata.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), normalized_peak=normalize)
        report.append(metadata)
    for data, target in licenses:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(data)
    with (out / "manifest.json").open("x", encoding="utf-8") as output:
        json.dump({"schema": 1, "selection_approved": plan["selection_approved"], "files": report,
                   "missing_cues": sorted(set(MANIFEST) - set(plan["cues"]))}, output, indent=2)
        output.write("\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("sound_plan.json"))
    art_root = Path(os.environ.get("CHAOS_ART_REPO", ROOT / "black-jack-assets"))
    parser.add_argument("--source-root", type=Path, default=art_root / "source" / "sounds")
    parser.add_argument("--out", type=Path, default=ROOT / "assets" / "sounds")
    parser.add_argument("--normalize", type=float, metavar="PEAK", help="optional peak 0..1; exports WAV, not generated audio")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true", help="check existing exported clips without raw sources or writes")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    owns_mixer = pygame.mixer.get_init() is None
    try:
        if owns_mixer:
            pygame.mixer.init(frequency=44100, size=-16, channels=2)
        if args.verify:
            report = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
            rows = report["files"]
            for row in rows:
                if Path(row["file"]).name != row["file"]:
                    raise ValueError("Invalid exported filename")
                data = (args.out / row["file"]).read_bytes()
                if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                    raise ValueError(f"Export checksum mismatch: {row['id']}")
                if row["normalized_peak"] is None and row["sha256"] != row["source_sha256"]:
                    raise ValueError(f"Original clip changed: {row['id']}")
                if abs(pygame.mixer.Sound(str(args.out / row["file"])).get_length() - row["seconds"]) > 0.001:
                    raise ValueError(f"Clip duration changed: {row['id']}")
            missing = sorted(set(MANIFEST) - {row["cue"] for row in rows})
        else:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            rows = prepare(plan, args.source_root, args.out, normalize=args.normalize)
            if not args.dry_run:
                rows = export(plan, args.source_root, args.out, rows, args.normalize)
            missing = sorted(set(MANIFEST) - set(plan["cues"]))
        rows = [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows]
        if args.json:
            print(json.dumps({"ok": True, "dry_run": args.dry_run, "files": rows, "missing_cues": missing}, indent=2))
        else:
            print("| id | source file | seconds | bytes |")
            print("| --- | --- | ---: | ---: |")
            for row in rows:
                size = row.get("bytes", row["source_bytes"])
                print(f"| {row['id']} | {row['source']} | {row['seconds']:.4f} | {size} |")
                if size > 200 * 1024:
                    print(f"Warning: {row['id']} exceeds 200 KiB", file=sys.stderr)
            print("Missing cues: " + (", ".join(missing) or "none"))
        return 0
    except (OSError, ValueError, KeyError, pygame.error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    finally:
        if owns_mixer:
            pygame.mixer.quit()


if __name__ == "__main__":
    raise SystemExit(main())
