"""Art pipeline: turn raw generated images into game-ready `<asset id>.png`.

Subcommands
  inventory  list candidate source files per manifest id (read-only)
  process    crop / scale / clean one source into a delivery PNG
  plan       run `process` for every entry of a JSON export plan

Source files are never modified. Outputs refuse to overwrite an existing
file unless `--force` is given, and never write into a source directory.

Needs Pillow and numpy (`pip install -e ".[art]"`); validation and previews
(`validate_assets.py`, `preview_assets.py`) only need pygame.

Examples
  python scripts/asset_tools.py inventory
  python scripts/asset_tools.py process --id chip_1 --src black-jack-assets/source/chip_1_v1.png
  python scripts/asset_tools.py process --id chip_5 --src black-jack-assets/source/chip_1_v1.png \\
      --recolor-to "#9A5B50"
  python scripts/asset_tools.py plan black-jack-assets/docs/export-plan.json --force
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover - guidance only
    sys.exit('asset_tools.py needs Pillow and numpy: python -m pip install -e ".[art]"')

ART_REPO = Path(os.environ.get("CHAOS_ART_REPO", ROOT / "black-jack-assets"))
GAME_ASSETS = ROOT / "assets"
# Raw art lives here; the tools must never write into these folders.
PROTECTED_DIRS = (ART_REPO / "source", ART_REPO / "references")
CANDIDATE_DIRS = (
    ART_REPO / "exports",
    ART_REPO / "source",
    ART_REPO / "references",
    GAME_ASSETS,
    ROOT / "output",
)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Category -> expected transparency ("opaque" | "transparent" | "transparent_recommended").
ALPHA_POLICY = {
    "background": "opaque",
    "card": "transparent",
    "chip": "transparent",
    "item": "transparent",
    "rule": "transparent",
    "character": "transparent_recommended",
}
# Transparent margin around the trimmed subject, as a fraction of the target size.
DEFAULT_MARGIN = {"card": 0.02, "chip": 0.04, "character": 0.04, "item": 0.12, "rule": 0.12}
# Source names that do not start with their asset id.
ALIASES = {
    "card_front": "card_front_blank",
    "chip": "chip_1",
    "table": "table_background",
    "background": "table_background",
    "menu": "menu_background",
    "chaos": "chaos_calm",
}
_VERSION_SUFFIX = re.compile(r"(_(v\d+|approved|final|candidate|draft|alt\d*|\d+))+$")


# --------------------------------------------------------------------- manifest


@dataclass(frozen=True)
class Spec:
    id: str
    category: str
    size: tuple[int, int]

    @property
    def policy(self) -> str:
        return ALPHA_POLICY.get(self.category, "transparent")


def load_specs() -> dict[str, Spec]:
    """Read the game manifest (imports pygame, but needs no display)."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    from chaos_blackjack.gui.assets.manifest import MANIFEST

    return {k: Spec(v.id, v.category, v.size) for k, v in MANIFEST.items()}


def normalize_stem(stem: str) -> str:
    s = stem.lower().replace("-", "_").replace(" ", "_")
    return _VERSION_SUFFIX.sub("", s)


def match_id(stem: str, ids: set[str]) -> str | None:
    if stem in ids:
        return stem
    n = normalize_stem(stem)
    if n in ids:
        return n
    if n in ALIASES:
        return ALIASES[n]
    hits = [i for i in ids if n.startswith(i + "_")]
    return max(hits, key=len) if hits else None


# ----------------------------------------------------------------- image stats


def alpha_stats(img: Image.Image) -> dict:
    if "A" not in img.getbands():
        return {"has_alpha": False, "transparent": 0.0, "semi": 0.0, "corners_clear": False, "max_alpha": 255}
    a = np.asarray(img.getchannel("A"))
    visible = a > 0
    corners = [a[0, 0], a[0, -1], a[-1, 0], a[-1, -1]]
    return {
        "has_alpha": True,
        "transparent": float((a == 0).mean()),
        "semi": float(((a > 0) & (a < 255)).sum() / max(1, visible.sum())),
        "corners_clear": all(c == 0 for c in corners),
        "max_alpha": int(a.max()),
    }


def content_bbox(img: Image.Image, threshold: int) -> tuple[int, int, int, int] | None:
    if "A" not in img.getbands():
        return (0, 0, *img.size)
    return img.getchannel("A").point(lambda v: 255 if v > threshold else 0).getbbox()


# -------------------------------------------------------------------- inventory


def cmd_inventory(args: argparse.Namespace) -> int:
    specs = load_specs()
    ids = set(specs)
    dirs = [Path(d) for d in args.dirs] if args.dirs else list(CANDIDATE_DIRS)
    found: dict[str, list[dict]] = {i: [] for i in specs}
    unmatched: list[str] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in IMAGE_EXTS or any(part.startswith(".") for part in p.relative_to(d).parts):
                continue
            rel = _rel(p)
            asset_id = match_id(p.stem, ids)
            if asset_id is None:
                unmatched.append(rel)
                continue
            with Image.open(p) as img:
                st = alpha_stats(img)
                found[asset_id].append({
                    "path": rel,
                    "size": list(img.size),
                    "mode": img.mode,
                    "exact_name": p.stem == asset_id,
                    "in_game_dir": _is_under(p, GAME_ASSETS) or _is_under(p, ART_REPO / "exports"),
                    "transparent": round(st["transparent"], 3),
                    "kb": p.stat().st_size // 1024,
                })
    if args.json:
        print(json.dumps({"ids": found, "unmatched": unmatched}, indent=2, ensure_ascii=False))
        return 0
    print("| id | category | target | candidates |")
    print("|---|---|---|---|")
    for asset_id, spec in specs.items():
        rows = found[asset_id]
        if not rows:
            cell = "**none** (placeholder)"
        else:
            parts = []
            for r in rows:
                flag = "" if r["exact_name"] else " ⚠ name"
                live = " ✓ loaded by game" if r["exact_name"] and r["in_game_dir"] else ""
                parts.append(f"`{r['path']}` {r['size'][0]}×{r['size'][1]} {r['mode']}{flag}{live}")
            cell = "<br>".join(parts)
        print(f"| {asset_id} | {spec.category} | {spec.size[0]}×{spec.size[1]} | {cell} |")
    if unmatched:
        print("\nUnmatched image files:")
        for u in unmatched:
            print(f"  {u}")
    missing = [i for i, r in found.items() if not r]
    print(f"\n{len(specs) - len(missing)}/{len(specs)} ids have at least one candidate.")
    return 0


# ---------------------------------------------------------------------- process


@dataclass
class Job:
    id: str
    src: Path
    out_dir: Path = GAME_ASSETS
    fit: str = "auto"  # auto | contain | cover
    margin: float | None = None
    anchor: tuple[float, float] = (0.5, 0.5)
    allow_upscale: bool = False
    alpha_floor: int = 8
    alpha_snap: int = 250
    trim_threshold: int = 16
    recolor_to: str | None = None
    recolor_from: str | None = None
    recolor_line: str | None = None
    ring: tuple[float, float] | None = None  # None = auto-detect the inner line
    max_kb: int = 2048
    force: bool = False
    dry_run: bool = False


def process(job: Job, specs: dict[str, Spec]) -> dict:
    spec = specs.get(job.id)
    if spec is None:
        raise SystemExit(f"unknown asset id {job.id!r}; ids come from chaos_blackjack/gui/assets/manifest.py")
    src = job.src.resolve()
    if not src.is_file():
        raise SystemExit(f"source not found: {job.src}")
    out_dir = job.out_dir.resolve()
    if any(_is_under(out_dir, d.resolve()) for d in PROTECTED_DIRS):
        raise SystemExit(f"refusing to write into a raw-art folder: {out_dir}")
    dest = out_dir / f"{job.id}.png"
    if dest == src:
        raise SystemExit("output would overwrite the source file")
    if dest.exists() and not job.force and not job.dry_run:
        raise SystemExit(f"{_rel(dest)} exists; pass --force to replace it")

    with Image.open(src) as raw:
        raw.load()
        img = raw.convert("RGBA")
    notes: list[str] = []
    tw, th = spec.size
    opaque = spec.policy == "opaque"
    fit = job.fit if job.fit != "auto" else ("cover" if opaque else "contain")

    img = _clean_alpha(img, job.alpha_floor, job.alpha_snap)
    if job.recolor_to:
        img = recolor_ring(img, job.recolor_to, job.recolor_from, job.recolor_line, job.ring, job.trim_threshold)
        notes.append(f"recolored ring to {job.recolor_to}")

    if fit == "cover":
        k = max(tw / img.width, th / img.height)
        _check_upscale(k, job, notes)
        sw, sh = max(tw, round(img.width * k)), max(th, round(img.height * k))
        scaled = img.resize((sw, sh), Image.LANCZOS)
        x = round((sw - tw) * job.anchor[0])
        y = round((sh - th) * job.anchor[1])
        out = scaled.crop((x, y, x + tw, y + th))
        lost = 1 - (tw * th) / (sw * sh)
        if lost > 0.005:
            notes.append(f"cover crop removed {lost:.1%} of the scaled image")
    elif fit == "contain":
        bbox = content_bbox(img, job.trim_threshold)
        if bbox is None:
            raise SystemExit(f"{job.src}: image is fully transparent")
        subject = img.crop(bbox)
        margin = DEFAULT_MARGIN.get(spec.category, 0.04) if job.margin is None else job.margin
        bw, bh = tw * (1 - 2 * margin), th * (1 - 2 * margin)
        k = min(bw / subject.width, bh / subject.height)
        _check_upscale(k, job, notes)
        sw, sh = max(1, round(subject.width * k)), max(1, round(subject.height * k))
        subject = subject.resize((sw, sh), Image.LANCZOS)
        out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        out.alpha_composite(subject, ((tw - sw) // 2, (th - sh) // 2))
        notes.append(f"subject {sw}×{sh} at ({(tw - sw) // 2},{(th - sh) // 2}), margin {margin:.0%}")
    else:
        raise SystemExit(f"unknown fit {fit!r}")

    if opaque:
        if alpha_stats(out)["transparent"] > 0 or out.getchannel("A").getextrema()[0] < 255:
            notes.append("flattened transparency onto black (background must be opaque)")
        flat = Image.new("RGBA", out.size, (0, 0, 0, 255))
        flat.alpha_composite(out)
        out = flat.convert("RGB")
    else:
        out = _zero_hidden_rgb(out)

    data, quantized = _encode_png(out, job.max_kb)
    if quantized:
        notes.append(f"quantized to a 256-colour palette to stay under {job.max_kb} KB")
    st = alpha_stats(out)
    result = {
        "id": job.id,
        "src": _rel(src),
        "out": _rel(dest),
        "size": list(out.size),
        "mode": out.mode,
        "fit": fit,
        "kb": len(data) // 1024,
        "transparent": round(st["transparent"], 3),
        "notes": notes,
        "written": False,
    }
    if spec.policy != "opaque" and st["transparent"] == 0:
        result["notes"].append("WARNING: no transparent pixels; source may have a painted background")
    if not job.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        result["written"] = True
    return result


def _check_upscale(k: float, job: Job, notes: list[str]) -> None:
    if k > 1.0001:
        if not job.allow_upscale:
            raise SystemExit(
                f"{job.id}: source is too small (would upscale ×{k:.2f}); "
                "get approval, then pass --allow-upscale"
            )
        notes.append(f"UPSCALED ×{k:.2f}")
    else:
        notes.append(f"downscaled ×{k:.3f}")


def _clean_alpha(img: Image.Image, floor: int, snap: int) -> Image.Image:
    """Drop near-invisible haze (alpha <= floor) and make near-opaque bodies opaque."""
    a = np.asarray(img.getchannel("A")).copy()
    if floor > 0:
        a[a <= floor] = 0
    if snap < 255:
        a[a >= snap] = 255
    out = img.copy()
    out.putalpha(Image.fromarray(a, "L"))
    return out


def _zero_hidden_rgb(img: Image.Image) -> Image.Image:
    arr = np.asarray(img).copy()
    arr[arr[..., 3] == 0, :3] = 0
    return Image.fromarray(arr, "RGBA")


def _encode_png(img: Image.Image, max_kb: int) -> tuple[bytes, bool]:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    if buf.tell() <= max_kb * 1024:
        return buf.getvalue(), False
    if img.mode == "RGBA":
        q = img.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    else:
        q = img.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    q.save(buf, "PNG", optimize=True)
    return buf.getvalue(), True


# ---------------------------------------------------------------------- recolor


def _hex(c: str) -> np.ndarray:
    c = c.lstrip("#")
    if len(c) != 6:
        raise SystemExit(f"colour must be #RRGGBB, got {c!r}")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def recolor_ring(
    img: Image.Image,
    to: str,
    frm: str | None,
    line: str | None,
    ring: tuple[float, float] | None,
    threshold: int,
) -> Image.Image:
    """Repaint the fill colour inside an annulus (a chip's outer ring).

    Each pixel is modelled as a blend between the fill colour and the line
    colour, so anti-aliased edges against the outline are recoloured too and
    the outline, tick marks and the centre (inside `ring[0]`) are kept.
    With `ring=None` the inner edge is the darkest circle between 0.3 and
    0.9 of the radius (the line separating the ring from the centre).
    """
    arr = np.asarray(img).astype(np.float32)
    rgb, a = arr[..., :3], arr[..., 3]
    bbox = content_bbox(img, threshold)
    if bbox is None:
        return img
    x0, y0, x1, y1 = bbox
    cx, cy, radius = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) / 2
    yy, xx = np.mgrid[0:img.height, 0:img.width]
    r = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) / radius
    if ring is None:
        ring = (_darkest_radius(rgb, a, r), 1.0)
    region = (r >= ring[0]) & (r <= ring[1]) & (a > 0)
    if not region.any():
        return img

    if frm:
        fill = _hex(frm)
    else:  # most common bright colour in the ring
        px = rgb[region & (a == 255)].astype(np.int32) // 8
        keys, counts = np.unique(px[:, 0] * 1024 + px[:, 1] * 32 + px[:, 2], return_counts=True)
        k = keys[np.argmax(counts)]
        fill = np.array([k // 1024, (k // 32) % 32, k % 32], dtype=np.float32) * 8 + 4
    ink = _hex(line) if line else np.percentile(rgb[region], 1, axis=0).astype(np.float32)
    target = _hex(to)

    axis = fill - ink
    denom = float((axis**2).sum()) or 1.0
    t = np.clip(((rgb - ink) @ axis) / denom, 0, 1)
    residual = np.linalg.norm(rgb - (ink + t[..., None] * axis), axis=-1)
    on_axis = region & (residual < 40)
    new = ink + t[..., None] * (target - ink)
    rgb[on_axis] = new[on_axis]
    arr[..., :3] = np.clip(rgb, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def _darkest_radius(rgb: np.ndarray, a: np.ndarray, r: np.ndarray) -> float:
    lum = rgb.mean(axis=-1)
    best, best_r = None, 0.70
    for lo in np.arange(0.30, 0.90, 0.005):
        band = (r >= lo) & (r < lo + 0.005) & (a > 200)
        if band.sum() < 16:
            continue
        v = float(np.median(lum[band]))
        if best is None or v < best:
            best, best_r = v, float(lo)
    return best_r


# ------------------------------------------------------------------------- plan


def cmd_plan(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    base = plan_path.parent
    defaults = plan.get("defaults", {})
    specs = load_specs()
    results = []
    for entry in plan["assets"]:
        opts = {**defaults, **entry}
        job = _job_from_dict(opts, base, force=args.force, dry_run=args.dry_run)
        if args.only and job.id not in args.only:
            continue
        results.append(process(job, specs))
    _print_results(results, args.json)
    return 0


def _job_from_dict(d: dict, base: Path, *, force: bool, dry_run: bool) -> Job:
    def path(p: str) -> Path:
        q = Path(p)
        if q.is_absolute():
            return q
        # Plan paths are relative to the repo root first, then to the plan file.
        return (ROOT / q) if (ROOT / q).exists() or not (base / q).exists() else base / q

    return Job(
        id=d["id"],
        src=path(d["src"]),
        out_dir=path(d.get("out_dir", "assets")),
        fit=d.get("fit", "auto"),
        margin=d.get("margin"),
        anchor=tuple(d.get("anchor", (0.5, 0.5))),
        allow_upscale=bool(d.get("allow_upscale", False)),
        alpha_floor=int(d.get("alpha_floor", 8)),
        alpha_snap=int(d.get("alpha_snap", 250)),
        trim_threshold=int(d.get("trim_threshold", 16)),
        recolor_to=d.get("recolor_to"),
        recolor_from=d.get("recolor_from"),
        recolor_line=d.get("recolor_line"),
        ring=tuple(d["ring"]) if d.get("ring") else None,
        max_kb=int(d.get("max_kb", 2048)),
        force=force or bool(d.get("force", False)),
        dry_run=dry_run,
    )


def cmd_process(args: argparse.Namespace) -> int:
    job = Job(
        id=args.id,
        src=Path(args.src),
        out_dir=Path(args.out_dir),
        fit=args.fit,
        margin=args.margin,
        anchor=tuple(float(v) for v in args.anchor.split(",")),
        allow_upscale=args.allow_upscale,
        alpha_floor=args.alpha_floor,
        alpha_snap=args.alpha_snap,
        trim_threshold=args.trim_threshold,
        recolor_to=args.recolor_to,
        recolor_from=args.recolor_from,
        recolor_line=args.recolor_line,
        ring=None if args.ring == "auto" else tuple(float(v) for v in args.ring.split(",")),
        max_kb=args.max_kb,
        force=args.force,
        dry_run=args.dry_run,
    )
    _print_results([process(job, load_specs())], args.json)
    return 0


def _print_results(results: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    for r in results:
        state = "wrote" if r["written"] else "dry-run"
        print(f"[{state}] {r['id']}: {r['src']} -> {r['out']} {r['size'][0]}×{r['size'][1]} {r['mode']} "
              f"{r['kb']} KB, transparent {r['transparent']:.1%}")
        for n in r["notes"]:
            print(f"    - {n}")


# -------------------------------------------------------------------- helpers


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def _is_under(p: Path, d: Path) -> bool:
    try:
        p.resolve().relative_to(d.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    inv = sub.add_parser("inventory", help="list candidate files per asset id")
    inv.add_argument("dirs", nargs="*", help="folders to scan (default: art repo, assets/, output/)")
    inv.add_argument("--json", action="store_true")
    inv.set_defaults(fn=cmd_inventory)

    pr = sub.add_parser("process", help="export one source image as <id>.png")
    pr.add_argument("--id", required=True, help="asset id from the manifest")
    pr.add_argument("--src", required=True, help="source image (left untouched)")
    pr.add_argument("--out-dir", default=str(GAME_ASSETS), help="default: assets/")
    pr.add_argument("--fit", choices=("auto", "contain", "cover"), default="auto",
                    help="auto = cover for backgrounds, contain (trim + centre) otherwise")
    pr.add_argument("--margin", type=float, help="contain: transparent margin as a fraction of the target")
    pr.add_argument("--anchor", default="0.5,0.5", help="cover: crop focus x,y in 0..1")
    pr.add_argument("--allow-upscale", action="store_true", help="permit enlarging a too-small source")
    pr.add_argument("--alpha-floor", type=int, default=8, help="alpha <= this becomes 0 (0 disables)")
    pr.add_argument("--alpha-snap", type=int, default=250, help="alpha >= this becomes 255 (255 disables)")
    pr.add_argument("--trim-threshold", type=int, default=16, help="alpha above this counts as subject")
    pr.add_argument("--recolor-to", help="#RRGGBB: repaint the ring fill (chip colour variants)")
    pr.add_argument("--recolor-from", help="#RRGGBB fill colour to replace (default: auto)")
    pr.add_argument("--recolor-line", help="#RRGGBB outline colour (default: auto)")
    pr.add_argument("--ring", default="auto",
                    help="recolour annulus as inner,outer radius fractions (default: auto-detect inner line)")
    pr.add_argument("--max-kb", type=int, default=2048, help="quantize if the PNG is larger")
    pr.add_argument("--force", action="store_true", help="replace an existing output file")
    pr.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(fn=cmd_process)

    pl = sub.add_parser("plan", help="process every entry of a JSON export plan")
    pl.add_argument("plan", help='JSON: {"defaults": {...}, "assets": [{"id": ..., "src": ..., ...}]}')
    pl.add_argument("--only", nargs="*", help="limit to these ids")
    pl.add_argument("--force", action="store_true")
    pl.add_argument("--dry-run", action="store_true")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(fn=cmd_plan)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
