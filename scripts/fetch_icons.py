"""Fetch stand-in icons from game-icons.net (CC BY 3.0) via the Iconify API.

No API key is needed. Icons are single-colour silhouettes, recoloured to the
palette: item icons in old gold, chaos rule icons in grey rose.

  sheet   render a contact sheet of candidates per asset id (to pick from)
  export  download the chosen icon per id as a 1024 px PNG into the art
          repo (default black-jack-assets/source/game-icons/) and write a
          CREDITS.md with author and licence for each icon; a copy goes to
          assets/CREDITS.md so the attribution ships with the game

The candidate list lives in scripts/icon_candidates.json: {"id": ["name", ...]};
the first name is the default choice. Override with --pick id=name.
Exported PNGs then go through `asset_tools.py process` like any other art.

  python scripts/fetch_icons.py sheet --out output/icon_candidates.png
  python scripts/fetch_icons.py export --pick swap=card-random
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from chaos_blackjack.gui.assets.manifest import MANIFEST  # noqa: E402

API = "https://api.iconify.design"
PREFIX = "game-icons"
# Author folders of the upstream repo, used for per-icon credit lines.
TREE_API = "https://api.github.com/repos/game-icons/icons/git/trees/master?recursive=1"
LICENSE = "CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/)"
CANDIDATES = ROOT / "scripts" / "icon_candidates.json"
ART_REPO = Path(os.environ.get("CHAOS_ART_REPO", ROOT / "black-jack-assets"))
CATEGORY_COLOR = {"item": "#B7A477", "rule": "#A4788F"}
UA = {"User-Agent": "chaos-blackjack-asset-tools"}


REQUEST_GAP = 0.4  # seconds between requests; Iconify rate-limits bursts


def fetch(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries + 1):
        time.sleep(REQUEST_GAP)
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_ARGS = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}


def normalize_path(d: str) -> str:
    """Re-space minified path data so pygame's SVG parser reads it.

    Minifiers glue arc flags to the next number ("a5 5 0 0110 10"); the
    flags are single digits, so they are split out here.
    """
    out: list[str] = []
    i, n, cmd, k = 0, len(d), "", 0
    while i < n:
        ch = d[i]
        if ch.isspace() or ch == ",":
            i += 1
        elif ch.lower() in _ARGS:
            cmd, k = ch, 0
            out.append(ch)
            i += 1
        else:
            if cmd.lower() == "a" and k % 7 in (3, 4) and ch in "01":
                out.append(ch)
                i += 1
            else:
                m = _NUM.match(d, i)
                if not m:
                    raise ValueError(f"bad path data near {d[i:i + 20]!r}")
                out.append(m.group())
                i = m.end()
            k += 1
    return " ".join(out)


def normalize_svg(text: str) -> str:
    return re.sub(r'\bd="([^"]*)"', lambda m: f'd="{normalize_path(m.group(1))}"', text)


def svg_url(name: str, color: str, size: int) -> str:
    q = urllib.parse.urlencode({"color": color, "width": size, "height": size})
    return f"{API}/{PREFIX}/{name}.svg?{q}"


def load_svg(name: str, color: str, size: int, cache: Path) -> tuple[pygame.Surface, Path]:
    """Rasterize an icon at `size` px; each icon is downloaded once (1024 px)."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{name}_{color.lstrip('#')}.svg"
    if not path.exists():
        raw = fetch(svg_url(name, color, 1024)).decode("utf-8")
        path.write_text(normalize_svg(raw), encoding="utf-8")
    surf = pygame.image.load(str(path))
    if surf.get_width() != size:
        surf = pygame.transform.smoothscale(surf, (size, size))
    return surf, path


def color_for(asset_id: str) -> str:
    return CATEGORY_COLOR.get(MANIFEST[asset_id].category, "#B7A477")


def authors() -> dict[str, str]:
    """icon name -> author folder, from the upstream repo tree (best effort)."""
    try:
        tree = json.loads(fetch(TREE_API))["tree"]
    except Exception as e:  # noqa: BLE001 - credits still list the icon and licence
        print(f"warning: could not look up authors ({e})", file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for node in tree:
        parts = node["path"].split("/")
        if len(parts) == 2 and parts[1].endswith(".svg"):
            out[parts[1][:-4]] = parts[0]
    return out


def load_candidates(picks: list[str]) -> dict[str, list[str]]:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    for pick in picks:
        asset_id, _, name = pick.partition("=")
        if asset_id not in data or not name:
            raise SystemExit(f"bad --pick {pick!r}; use id=icon-name with an id from {CANDIDATES.name}")
        data[asset_id] = [name] + [n for n in data[asset_id] if n != name]
    for asset_id in data:
        if asset_id not in MANIFEST:
            raise SystemExit(f"{asset_id!r} is not an asset id in the manifest")
    return data


# ------------------------------------------------------------------- sheet


def cmd_sheet(args: argparse.Namespace) -> int:
    pygame.init()
    font = pygame.font.SysFont("segoeui,arial", 15)
    bold = pygame.font.SysFont("segoeui,arial", 17, bold=True)
    data = load_candidates([])
    cols = max(len(v) for v in data.values())
    cell_w, cell_h, label_w = 190, 150, 190
    sheet = pygame.Surface((label_w + cols * cell_w, len(data) * cell_h))
    sheet.fill((0x17, 0x1C, 0x1B))
    cache = Path(args.cache)
    for row, (asset_id, names) in enumerate(data.items()):
        y = row * cell_h
        pygame.draw.line(sheet, (0x3A, 0x40, 0x3E), (0, y), (sheet.get_width(), y))
        sheet.blit(bold.render(asset_id, True, (0xE6, 0xE0, 0xD2)), (12, y + 12))
        sheet.blit(font.render(MANIFEST[asset_id].category, True, (0x8E, 0x96, 0x90)), (12, y + 36))
        for col, name in enumerate(names):
            x = label_w + col * cell_w
            panel = pygame.Rect(x + 8, y + 8, cell_w - 16, cell_h - 16)
            pygame.draw.rect(sheet, (0x1E, 0x25, 0x23), panel, border_radius=10)
            if col == 0:
                pygame.draw.rect(sheet, (0xC2, 0xAE, 0x7E), panel, 2, border_radius=10)
            try:
                big, _ = load_svg(name, color_for(asset_id), 96, cache)
                small, _ = load_svg(name, color_for(asset_id), 32, cache)
            except Exception as e:  # noqa: BLE001
                sheet.blit(font.render(f"error: {e}", True, (0xD0, 0x7C, 0x70)), (x + 14, y + 20))
                continue
            sheet.blit(big, (x + 16, y + 14))
            sheet.blit(small, (x + 128, y + 46))
            sheet.blit(font.render(name, True, (0xE6, 0xE0, 0xD2)), (x + 16, y + cell_h - 34))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, str(out))
    print(f"wrote {out} ({len(data)} ids; framed = current pick)")
    return 0


# ------------------------------------------------------------------ export


def cmd_export(args: argparse.Namespace) -> int:
    pygame.init()
    data = load_candidates(args.pick)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    who = authors()
    lines = [
        "# Stand-in icons from game-icons.net",
        "",
        f"Licence: {LICENSE}. Fetched through the Iconify API and recoloured.",
        "",
        "| Asset id | Icon | Author | Source |",
        "|---|---|---|---|",
    ]
    for asset_id, names in data.items():
        name = names[0]
        dest = out_dir / f"{asset_id}_v1.png"
        if dest.exists() and not args.force:
            print(f"skip {dest.name} (exists; --force to replace)")
        else:
            surf, _ = load_svg(name, color_for(asset_id), args.size, Path(args.cache))
            pygame.image.save(surf, str(dest))
            print(f"wrote {dest.name} <- {PREFIX}:{name}")
        author = who.get(name, "unknown")
        url = f"https://game-icons.net/1x1/{author}/{name}.html" if author != "unknown" else "https://game-icons.net"
        lines.append(f"| {asset_id} | {name} | {author} | {url} |")
    text = "\n".join(lines) + "\n"
    for path in (out_dir / "CREDITS.md", Path(args.credits)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default=str(ROOT / "output" / "icon_cache"), help="downloaded SVGs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sh = sub.add_parser("sheet", help="contact sheet of candidates")
    sh.add_argument("--out", default=str(ROOT / "output" / "icon_candidates.png"))
    sh.set_defaults(fn=cmd_sheet)
    ex = sub.add_parser("export", help="download the picked icons as PNG")
    ex.add_argument("--out-dir", default=str(ART_REPO / "source" / "game-icons"))
    ex.add_argument("--pick", action="append", default=[], help="override a choice: id=icon-name")
    ex.add_argument("--size", type=int, default=1024)
    ex.add_argument("--credits", default=str(ROOT / "assets" / "CREDITS.md"),
                    help="second copy of the credits, shipped with the game (CC BY needs it)")
    ex.add_argument("--force", action="store_true")
    ex.set_defaults(fn=cmd_export)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
