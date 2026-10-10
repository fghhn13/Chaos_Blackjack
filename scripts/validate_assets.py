"""Check delivered art against the GUI asset manifest (needs only pygame).

For every manifest id it resolves the file the game would load (same search
order as the GUI) and checks:
  * the delivery size,
  * transparency: backgrounds fully opaque; cards, chips and icons RGBA with
    transparent pixels and clear corners; characters transparent (recommended),
  * file size (warns above --max-kb),
  * naming: image files in the asset folders whose name is not an asset id,
    and ids that resolve to more than one file (the first folder wins).

Prints a Markdown table (or --json). Exit code 1 if anything FAILs, or if an
id has no file and --require-all is set.

  python scripts/validate_assets.py
  python scripts/validate_assets.py --dir assets --require-all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from chaos_blackjack.gui.assets.manager import IMAGE_EXTS  # noqa: E402
from chaos_blackjack.gui.assets.manifest import MANIFEST  # noqa: E402
from chaos_blackjack.gui.settings import default_asset_dirs  # noqa: E402

OPAQUE = {"background"}
TRANSPARENT = {"card", "chip", "item", "rule"}
RECOMMENDED_TRANSPARENT = {"character"}
# Share of visible pixels that may be *nearly* opaque (alpha 200-254) before the
# body counts as "not solid" (generated art often sits at alpha 254).
# Anti-aliased edges spread over all alpha values, so line art passes.
SEMI_LIMIT = 0.25
# Card faces and the back must share one outline or cards jump when flipped.
OUTLINE_PAIR = ("card_back", "card_front_blank")
OUTLINE_TOLERANCE = 2  # px at delivery size


def scan(dirs: list[Path]) -> tuple[dict[str, list[Path]], list[Path]]:
    """All image files per stem (in search order) and files matching no id."""
    by_stem: dict[str, list[Path]] = {}
    stray: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in IMAGE_EXTS:
                continue
            if any(part.startswith(".") for part in p.relative_to(d).parts):
                continue
            by_stem.setdefault(p.stem, []).append(p)
            if p.stem not in MANIFEST:
                stray.append(p)
    return by_stem, stray


def alpha_report(surf: pygame.Surface) -> dict:
    w, h = surf.get_size()
    total = w * h
    if not surf.get_flags() & pygame.SRCALPHA:
        return {"alpha": False, "transparent": 0.0, "semi": 0.0, "opaque": True, "corners_clear": False}
    visible = pygame.mask.from_surface(surf, 0).count()  # alpha > 0
    solid = pygame.mask.from_surface(surf, 254).count()  # alpha == 255
    near = pygame.mask.from_surface(surf, 199).count() - solid  # alpha 200..254
    corners = [surf.get_at(p).a for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return {
        "alpha": True,
        "transparent": (total - visible) / total,
        "semi": near / max(1, visible),
        "opaque": solid == total,
        "corners_clear": all(a == 0 for a in corners),
    }


def check(asset_id: str, files: list[Path], max_kb: int) -> dict:
    spec = MANIFEST[asset_id]
    row: dict = {
        "id": asset_id,
        "category": spec.category,
        "expected": f"{spec.size[0]}×{spec.size[1]}",
        "file": None,
        "size": "",
        "alpha": "",
        "transparent": "",
        "kb": "",
        "status": "MISSING",
        "issues": [],
    }
    if not files:
        row["issues"].append("no file; the game uses the placeholder")
        return row
    path = files[0]
    row["file"] = _rel(path)
    if len(files) > 1:
        row["issues"].append("shadows " + ", ".join(_rel(p) for p in files[1:]))
    try:
        surf = pygame.image.load(str(path))
    except pygame.error as e:
        row["status"] = "FAIL"
        row["issues"].append(f"unreadable: {e}")
        return row

    fail, warn = [], []
    size = surf.get_size()
    row["size"] = f"{size[0]}×{size[1]}"
    if size != spec.size:
        fail.append(f"size {row['size']} != {row['expected']}")
    kb = path.stat().st_size // 1024
    row["kb"] = kb
    if kb > max_kb:
        warn.append(f"{kb} KB > {max_kb} KB")
    if path.suffix.lower() != ".png":
        warn.append("not a PNG")

    a = alpha_report(surf)
    row["alpha"] = "RGBA" if a["alpha"] else "RGB"
    row["transparent"] = f"{a['transparent']:.1%}"
    if spec.category in OPAQUE:
        if not a["opaque"]:
            fail.append("background must be fully opaque")
    else:
        transparent_ok = a["alpha"] and a["transparent"] > 0
        problem = None
        if not a["alpha"]:
            problem = "no alpha channel"
        elif a["transparent"] == 0:
            problem = "alpha channel but no transparent pixels"
        elif not a["corners_clear"]:
            problem = "corners not transparent (painted background or checkerboard?)"
        if problem:
            (fail if spec.category in TRANSPARENT else warn).append(problem)
        if transparent_ok and a["semi"] > SEMI_LIMIT:
            warn.append(f"{a['semi']:.0%} of visible pixels are nearly but not fully opaque (body not solid?)")

    row["issues"] = fail + warn + row["issues"]
    row["status"] = "FAIL" if fail else ("WARN" if warn or len(files) > 1 else "OK")
    return row


def subject_rect(path: Path) -> pygame.Rect | None:
    surf = pygame.image.load(str(path))
    if not surf.get_flags() & pygame.SRCALPHA:
        return surf.get_rect()
    rects = pygame.mask.from_surface(surf, 16).get_bounding_rects()
    return rects[0].unionall(rects[1:]) if rects else None


def check_outlines(rows: list[dict], by_stem: dict[str, list[Path]]) -> None:
    files = [by_stem.get(i) for i in OUTLINE_PAIR]
    if not all(files):
        return
    a, b = (subject_rect(f[0]) for f in files)
    if a is None or b is None:
        return
    worst = max(abs(x - y) for x, y in zip(a, b))
    if worst > OUTLINE_TOLERANCE:
        row = next(r for r in rows if r["id"] == OUTLINE_PAIR[1])
        row["issues"].append(f"outline {tuple(b)} differs from {OUTLINE_PAIR[0]} {tuple(a)} by {worst}px")
        if row["status"] == "OK":
            row["status"] = "WARN"


def suggest(stem: str) -> str | None:
    n = re.sub(r"(_(v\d+|approved|final|candidate|draft|\d+))+$", "", stem.lower().replace("-", "_"))
    return n if n in MANIFEST else None


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.name if p.is_file() else str(p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", action="append", help="asset folder(s) to check, in search order "
                    "(default: the game's search order: CHAOS_ASSETS_DIR, assets/, black-jack-assets/exports/)")
    ap.add_argument("--max-kb", type=int, default=2048)
    ap.add_argument("--require-all", action="store_true", help="treat missing ids as failures")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pygame.init()
    dirs = [Path(d) for d in args.dir] if args.dir else list(default_asset_dirs())
    by_stem, stray = scan(dirs)
    rows = [check(i, by_stem.get(i, []), args.max_kb) for i in MANIFEST]
    check_outlines(rows, by_stem)
    stray_rows = [{"file": _rel(p), "suggested_id": suggest(p.stem)} for p in stray]

    if args.json:
        print(json.dumps({"dirs": [_rel(d) for d in dirs], "assets": rows, "unrecognized": stray_rows},
                         indent=2, ensure_ascii=False))
    else:
        print("Searched: " + ", ".join(_rel(d) for d in dirs) + "\n")
        print("| id | category | expected | actual | alpha | transparent | KB | status | file / issues |")
        print("|---|---|---|---|---|---|---:|---|---|")
        for r in rows:
            detail = "; ".join(([f"`{r['file']}`"] if r["file"] else []) + r["issues"])
            print(f"| {r['id']} | {r['category']} | {r['expected']} | {r['size']} | {r['alpha']} | "
                  f"{r['transparent']} | {r['kb']} | {r['status']} | {detail} |")
        if stray_rows:
            print("\nImage files the game ignores (name is not an asset id):")
            for s in stray_rows:
                hint = f" -> rename to {s['suggested_id']}.png?" if s["suggested_id"] else ""
                print(f"  {s['file']}{hint}")
        counts = {k: sum(r["status"] == k for r in rows) for k in ("OK", "WARN", "FAIL", "MISSING")}
        print("\n" + "  ".join(f"{k} {v}" for k, v in counts.items()))

    failed = any(r["status"] == "FAIL" for r in rows)
    missing = any(r["status"] == "MISSING" for r in rows)
    return 1 if failed or (args.require_all and missing) else 0


if __name__ == "__main__":
    sys.exit(main())
