"""Draw the five membership badges (assets/membership/member_<level>.png).

Chip-edged medallions whose metal and emblem grow with the level: bronze chip,
silver star, gold shield, emerald crown, magenta crown in a laurel. Original
geometric drawing with Pillow (no third-party art). Run from the repository
root: python scripts/draw_membership_badges.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "membership"
S = 1024              # drawn at 4x, saved at 256
C = S // 2

# level: (rim, face, emblem, accent)
PALETTE = {
    1: ((0x8C, 0x64, 0x3C), (0x2A, 0x22, 0x1C), (0xC0, 0x8E, 0x5A), (0x6E, 0x4E, 0x30)),
    2: ((0xA8, 0xB0, 0xB6), (0x22, 0x27, 0x2A), (0xDD, 0xE4, 0xE8), (0x7C, 0x86, 0x8C)),
    3: ((0xB7, 0xA4, 0x77), (0x26, 0x22, 0x18), (0xE8, 0xD2, 0x8E), (0x8A, 0x76, 0x46)),
    4: ((0x3E, 0x8E, 0x6E), (0x14, 0x26, 0x20), (0xE8, 0xD2, 0x8E), (0x2A, 0x62, 0x4C)),
    5: ((0xC8, 0x6A, 0xA0), (0x24, 0x16, 0x22), (0xF2, 0xD8, 0x8E), (0x8E, 0x3E, 0x6E)),
}


def star(cx, cy, r_out, r_in, points=5, rotation=-90):
    pts = []
    for i in range(points * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rotation + i * 180 / points)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def medallion(level: int) -> Image.Image:
    rim, face, emblem, accent = PALETTE[level]
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = 440
    d.ellipse((C - r, C - r, C + r, C + r), fill=rim)
    # chip edge: light notches around the rim
    for i in range(12):
        a = math.radians(i * 30)
        x, y = C + 404 * math.cos(a), C + 404 * math.sin(a)
        d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=accent)
    d.ellipse((C - 350, C - 350, C + 350, C + 350), fill=face)
    d.ellipse((C - 350, C - 350, C + 350, C + 350), outline=rim, width=14)
    d.ellipse((C - 316, C - 316, C + 316, C + 316), outline=accent, width=6)
    return img


def emblem(img: Image.Image, level: int) -> None:
    _, face, color, accent = PALETTE[level]
    d = ImageDraw.Draw(img)
    if level == 1:                                    # a single chip
        d.ellipse((C - 150, C - 150, C + 150, C + 150), fill=color)
        d.ellipse((C - 104, C - 104, C + 104, C + 104), fill=face)
        d.ellipse((C - 70, C - 70, C + 70, C + 70), fill=color)
    elif level == 2:                                  # a star
        d.polygon(star(C, C + 10, 210, 88), fill=color)
    elif level == 3:                                  # a shield with a spade
        shield = [(C - 170, C - 190), (C + 170, C - 190), (C + 170, C + 10), (C + 120, C + 120), (C, C + 210),
                  (C - 120, C + 120), (C - 170, C + 10)]
        d.polygon(shield, fill=color)
        d.ellipse((C - 62, C - 70, C + 2, C - 6), fill=face)
        d.ellipse((C - 2, C - 70, C + 62, C - 6), fill=face)
        d.polygon([(C - 70, C - 44), (C + 70, C - 44), (C, C - 150)], fill=face)
        d.polygon([(C - 26, C + 60), (C + 26, C + 60), (C, C - 20)], fill=face)
    else:                                             # a crown (and a laurel at the top level)
        base_y = C + 110
        crown = [(C - 210, base_y), (C - 230, C - 120), (C - 110, C - 10), (C, C - 190), (C + 110, C - 10),
                 (C + 230, C - 120), (C + 210, base_y)]
        d.polygon(crown, fill=color)
        d.rectangle((C - 210, base_y, C + 210, base_y + 60), fill=color)
        for x in (C - 230, C, C + 230):
            y = C - 120 if x != C else C - 190
            d.ellipse((x - 34, y - 34, x + 34, y + 34), fill=color)
        for x in (C - 120, C, C + 120):
            d.ellipse((x - 22, base_y + 8, x + 22, base_y + 52), fill=accent)
        if level == 5:
            for side in (-1, 1):
                for i in range(6):
                    a = math.radians(115 + i * 20) if side < 0 else math.radians(65 - i * 20)
                    x, y = C + 270 * math.cos(a), C + 270 * math.sin(a) + 30
                    d.ellipse((x - 40, y - 22, x + 40, y + 22), fill=color)


def save(img: Image.Image, path: Path) -> None:
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(img.getchannel("A").filter(ImageFilter.GaussianBlur(18)).point(lambda a: a * 0.45))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, 14))
    out.alpha_composite(img)
    out.resize((256, 256), Image.LANCZOS).save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for level in PALETTE:
        img = medallion(level)
        emblem(img, level)
        save(img, OUT / f"member_{level}.png")
        print("wrote", OUT / f"member_{level}.png")


if __name__ == "__main__":
    main()
