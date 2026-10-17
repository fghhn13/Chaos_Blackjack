"""Draw J-54's v2 table icons: conditions, firmwares, operations and badges.

Deterministic PIL drawing, no network and no source images. Every icon is
drawn at 1024 px from flat shapes and a 5x7 pixel font (J-54's pixel face),
then reduced to the manifest's 256 px with premultiplied alpha.

Language (docs/design/J54_ART.md):
- conditions: J-54's dark card stock with a red rim and a clipped corner; a
  red mark on top (what the condition reads) and the number below;
- firmwares: the same construction as a green cartridge with contact
  fingers (the player's rule);
- operations and badges: solid one-colour silhouettes with transparent
  cutouts, as J-54's v1 icons, bold enough for the 20 px badges.

Run from the repository root:
    python scripts/draw_j54_icons.py                 # review copy + sheet in output/j54_icons/
    python scripts/draw_j54_icons.py --out assets/j54 --force
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
S = 1024  # working size; the delivered PNG is S / 4
OUT_SIZE = 256

RED = (0xC8, 0x3A, 0x3A)      # _J54_RED in the GUI manifest
STOCK = (0x17, 0x17, 0x19)    # _J54_BLACK: J-54's card stock
GREEN = (0x9C, 0xC2, 0x96)    # the player's firmware green (placeholder colour)
GOLD = (0xC2, 0xAE, 0x7E)     # theme.GOLD, as the v1 badges
AMBER = (0xE0, 0xB0, 0x60)    # the "warn" tone of the next-condition badge

FONT = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "x": ("00000", "10001", "01010", "00100", "01010", "10001", "00000"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
}


class Icon:
    """Flat layers in order: a fill paints a colour, a cut clears everything below it."""

    def __init__(self) -> None:
        self.image = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    @staticmethod
    def mask() -> tuple[Image.Image, ImageDraw.ImageDraw]:
        m = Image.new("L", (S, S), 0)
        return m, ImageDraw.Draw(m)

    def fill(self, m: Image.Image, color: tuple[int, int, int]) -> None:
        layer = Image.new("RGBA", (S, S), color + (255,))
        self.image = Image.composite(layer, self.image, m)

    def cut(self, m: Image.Image) -> None:
        self.image.putalpha(ImageChops.multiply(self.image.getchannel("A"), ImageChops.invert(m)))

    def final(self) -> Image.Image:
        small = self.image.convert("RGBa").resize((OUT_SIZE, OUT_SIZE), Image.Resampling.LANCZOS).convert("RGBA")
        px = small.load()
        for y in range(OUT_SIZE):
            for x in range(OUT_SIZE):
                r, g, b, a = px[x, y]
                if a <= 8:
                    px[x, y] = (0, 0, 0, 0)
                elif a >= 250:
                    px[x, y] = (r, g, b, 255)
        return small


# ------------------------------------------------------------------ shapes


def rotated(points, angle, cx, cy):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in points]


def card_mask(x0, y0, x1, y1, radius, clip=0):
    """Rounded card; `clip` chamfers the top-right corner (J-54's punch-card notch)."""
    m, d = Icon.mask()
    d.rounded_rectangle((x0, y0, x1, y1), radius, fill=255)
    if clip:
        d.polygon([(x1 - clip, y0 - 2), (x1 + 2, y0 - 2), (x1 + 2, y0 + clip)], fill=0)
    return m


def poly_mask(points):
    m, d = Icon.mask()
    d.polygon(points, fill=255)
    return m


def text_mask(text, cx, cy, unit):
    """5x7 pixel lettering centred on (cx, cy), one column of space between glyphs."""
    m, d = Icon.mask()
    width = (len(text) * 6 - 1) * unit
    x0, y0 = cx - width / 2, cy - 7 * unit / 2
    for i, ch in enumerate(text):
        for row, bits in enumerate(FONT[ch]):
            for col, bit in enumerate(bits):
                if bit == "1":
                    x = x0 + (i * 6 + col) * unit
                    y = y0 + row * unit
                    d.rectangle((round(x), round(y), round(x + unit) - 1, round(y + unit) - 1), fill=255)
    return m


def fit_unit(text, width, cap):
    return min(cap, width // (len(text) * 6 - 1))


def spade_mask(cx, cy, size):
    m, d = Icon.mask()
    r = size * 0.27
    d.polygon([(cx, cy - size * 0.5), (cx - size * 0.5, cy + size * 0.06), (cx + size * 0.5, cy + size * 0.06)], fill=255)
    d.ellipse((cx - size * 0.5, cy - size * 0.12, cx - size * 0.5 + 2 * r, cy - size * 0.12 + 2 * r), fill=255)
    d.ellipse((cx + size * 0.5 - 2 * r, cy - size * 0.12, cx + size * 0.5, cy - size * 0.12 + 2 * r), fill=255)
    d.polygon([(cx, cy + size * 0.05), (cx - size * 0.2, cy + size * 0.5), (cx + size * 0.2, cy + size * 0.5)], fill=255)
    return m


def club_mask(cx, cy, size):
    m, d = Icon.mask()
    r = size * 0.24
    for x, y in ((cx, cy - size * 0.26), (cx - size * 0.26, cy + size * 0.06), (cx + size * 0.26, cy + size * 0.06)):
        d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    d.rectangle((cx - size * 0.1, cy - size * 0.1, cx + size * 0.1, cy + size * 0.2), fill=255)
    d.polygon([(cx, cy + size * 0.05), (cx - size * 0.22, cy + size * 0.5), (cx + size * 0.22, cy + size * 0.5)], fill=255)
    return m


def heart_mask(cx, cy, size):
    m, d = Icon.mask()
    r = size * 0.27
    d.ellipse((cx - size * 0.5, cy - size * 0.45, cx - size * 0.5 + 2 * r, cy - size * 0.45 + 2 * r), fill=255)
    d.ellipse((cx + size * 0.5 - 2 * r, cy - size * 0.45, cx + size * 0.5, cy - size * 0.45 + 2 * r), fill=255)
    d.polygon([(cx - size * 0.49, cy - size * 0.1), (cx + size * 0.49, cy - size * 0.1), (cx, cy + size * 0.5)], fill=255)
    return m


def crown_mask(cx, cy, w, h):
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    m = poly_mask([(x0, y0 + h * 0.15), (x0 + w * 0.27, y0 + h * 0.5), (cx, y0), (x1 - w * 0.27, y0 + h * 0.5),
                   (x1, y0 + h * 0.15), (x1 - w * 0.08, y1 - h * 0.22), (x0 + w * 0.08, y1 - h * 0.22)])
    d = ImageDraw.Draw(m)
    d.rectangle((x0 + w * 0.08, y1 - h * 0.13, x1 - w * 0.08, y1), fill=255)
    return m


def jester_mask(cx, cy, w):
    """A three-pointed jester hat with bells, J-54's own Joker."""
    m, d = Icon.mask()
    u = w / 2
    d.rounded_rectangle((cx - 0.6 * u, cy + 0.25 * u, cx + 0.6 * u, cy + 0.6 * u), 0.08 * u, fill=255)
    d.polygon([(cx - 0.32 * u, cy + 0.3 * u), (cx + 0.32 * u, cy + 0.3 * u), (cx + 0.08 * u, cy - 0.72 * u)], fill=255)
    for side in (-1, 1):  # the outer points flop down past the band, unlike a crown's
        d.polygon([(cx + side * 0.6 * u, cy + 0.3 * u), (cx + side * 0.05 * u, cy + 0.3 * u),
                   (cx + side * 0.45 * u, cy - 0.38 * u), (cx + side * 0.98 * u, cy + 0.12 * u)], fill=255)
    for x, y in ((cx - 0.98 * u, cy + 0.26 * u), (cx + 0.08 * u, cy - 0.72 * u), (cx + 0.98 * u, cy + 0.26 * u)):
        d.ellipse((x - 0.17 * u, y - 0.17 * u, x + 0.17 * u, y + 0.17 * u), fill=255)
    return m


def threshold_mask(cx, cy, w, h):
    """A marker pointing down at a bar: "J-54 stops here"."""
    m = poly_mask([(cx - w * 0.28, cy - h / 2), (cx + w * 0.28, cy - h / 2), (cx, cy + h * 0.08)])
    ImageDraw.Draw(m).rectangle((cx - w / 2, cy + h * 0.24, cx + w / 2, cy + h / 2), fill=255)
    return m


def raised_bar_mask(cx, cy, w, h):
    """An upward arrow lifting a bar: the bust line moved up."""
    m, d = Icon.mask()
    d.rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy - h / 2 + h * 0.24), fill=255)
    d.polygon([(cx - w * 0.3, cy + h * 0.08), (cx + w * 0.3, cy + h * 0.08), (cx, cy - h * 0.18)], fill=255)
    d.rectangle((cx - w * 0.1, cy + h * 0.05, cx + w * 0.1, cy + h / 2), fill=255)
    return m


def dots_mask(cx, cy, size):
    """Four dots in two pairs: even ranks."""
    m, d = Icon.mask()
    r, off = size * 0.17, size * 0.3
    for dx in (-off, off):
        for dy in (-off, off):
            d.ellipse((cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r), fill=255)
    return m


def erode(m, px):
    return m.filter(ImageFilter.MinFilter(px * 2 + 1))


def outline(m, px):
    return ImageChops.subtract(m.filter(ImageFilter.MaxFilter(px * 2 + 1)), m)


# ------------------------------------------------------------------ families

CARD = (192, 112, 832, 912)  # the condition / firmware plate: 640 x 800 at 1024
RIM = 52


def condition(mark, number):
    """J-54's dark card stock, red rim, red mark above its number."""
    x0, y0, x1, y1 = CARD
    icon = Icon()
    icon.fill(card_mask(x0, y0, x1, y1, 64, clip=150), RED)
    inner = card_mask(x0 + RIM, y0 + RIM, x1 - RIM, y1 - RIM, 24, clip=150 - round(RIM * (2 - math.sqrt(2))))
    icon.fill(inner, STOCK)
    mark(icon, (x0 + x1) / 2, 345)
    unit = fit_unit(number, x1 - x0 - 2 * RIM - 70, 46)
    icon.fill(text_mask(number, (x0 + x1) / 2, 690, unit), RED)
    return icon


def firmware(top, bottom):
    """The player's cartridge: dark body, green rim, contact fingers, green lettering."""
    x0, y0, x1, y1 = CARD[0], CARD[1], CARD[2], 820
    icon = Icon()
    body, d = Icon.mask()
    d.rounded_rectangle((x0, y0, x1, y1), 64, fill=255)
    d.ellipse(((x0 + x1) / 2 - 70, y0 - 70, (x0 + x1) / 2 + 70, y0 + 70), fill=0)  # cartridge notch
    icon.fill(body, GREEN)
    icon.fill(erode(body, RIM), STOCK)
    fingers, d = Icon.mask()
    n, gap = 6, 28
    w = (x1 - x0 - 120 - (n - 1) * gap) / n
    for i in range(n):
        fx = x0 + 60 + i * (w + gap)
        d.rounded_rectangle((fx, y1 + 22, fx + w, 912), 10, fill=255)
    icon.fill(fingers, GREEN)
    inner_w = x1 - x0 - 2 * RIM - 70
    if isinstance(top, str):
        icon.fill(text_mask(top, (x0 + x1) / 2, 330, fit_unit(top, inner_w, 44)), GREEN)
    else:
        top(icon, (x0 + x1) / 2, 330)
    icon.fill(text_mask(bottom, (x0 + x1) / 2, 628, fit_unit(bottom, inner_w, 44)), GREEN)
    return icon


def hollow(shape):
    """A pip drawn as a red outline: one of the black suits on the dark stock."""
    def draw(icon, cx, cy):
        m = shape(cx, cy)
        icon.fill(m, RED)
        icon.fill(erode(m, 26), STOCK)
    return draw


def solid(shape, color=RED):
    def draw(icon, cx, cy):
        icon.fill(shape(cx, cy), color)
    return draw


def two_black_suits(icon, cx, cy):
    hollow(lambda x, y: spade_mask(x, y, 230))(icon, cx - 128, cy)
    hollow(lambda x, y: club_mask(x, y, 230))(icon, cx + 128, cy)


def card_shape(x0, y0, x1, y1, angle=0, pivot=None):
    w, h = x1 - x0, y1 - y0
    m = card_mask(x0, y0, x1, y1, min(w, h) * 0.12)
    if angle:
        px, py = pivot or ((x0 + x1) / 2, (y0 + y1) / 2)
        m = m.rotate(-angle, resample=Image.Resampling.BICUBIC, center=(px, py))
    return m


def stack_cards(icon, masks, color, gap=30):
    """Paint cards back to front, each cut free of the ones behind it."""
    for m in masks:
        icon.cut(outline(m, gap))
        icon.fill(m, color)


# ------------------------------------------------------------------ the 17 icons


def draw_all() -> dict[str, Icon]:
    icons: dict[str, Icon] = {}

    icons["j54_black_plus"] = condition(two_black_suits, "+1")
    icons["j54_even_plus"] = condition(solid(lambda x, y: dots_mask(x, y, 300)), "+2")
    icons["j54_hearts_scale"] = condition(solid(lambda x, y: heart_mask(x, y + 10, 280)), "x2")
    icons["j54_stand_19"] = condition(solid(lambda x, y: threshold_mask(x, y, 380, 250)), "19")
    icons["j54_stand_15"] = condition(solid(lambda x, y: threshold_mask(x, y, 380, 250)), "15")
    icons["j54_low_plus"] = condition(lambda icon, x, y: icon.fill(text_mask("2-6", x, y, 26), RED), "+3")
    icons["j54_faces_set"] = condition(solid(lambda x, y: crown_mask(x, y, 360, 250)), "=5")

    icons["fw_mid"] = firmware("4-6", "=10")
    icons["fw_fives"] = firmware("56", "=10")
    icons["fw_low"] = firmware("2-4", "=10")
    icons["fw_margin"] = firmware(lambda icon, x, y: icon.fill(raised_bar_mask(x, y, 360, 250), GREEN), "22")

    # Compute: a charge meter, three of four cells full (income in, cap on top).
    icon = Icon()
    m, d = Icon.mask()
    d.rounded_rectangle((132, 292, 812, 732), 70, fill=255)
    d.rounded_rectangle((812, 422, 900, 602), 24, fill=255)
    icon.fill(m, GOLD)
    m, d = Icon.mask()
    d.rounded_rectangle((192, 352, 752, 672), 30, fill=255)
    icon.cut(m)
    m, d = Icon.mask()
    gap, n = 34, 4
    w = (560 - (n + 1) * gap) / n
    for i in range(3):
        x = 192 + gap + i * (w + gap)
        d.rectangle((x, 352 + gap, x + w, 672 - gap), fill=255)
    icon.fill(m, GOLD)
    icons["j54_compute"] = icon

    # Next condition: "skip to next" — two arrowheads against a bar.
    icon = Icon()
    m, d = Icon.mask()
    d.polygon([(132, 232), (132, 792), (462, 512)], fill=255)
    d.polygon([(442, 232), (442, 792), (772, 512)], fill=255)
    d.rounded_rectangle((782, 232, 892, 792), 18, fill=255)
    icon.fill(m, AMBER)
    icons["j54_next"] = icon

    # Sample bounty: a card in the crosshairs.
    icon = Icon()
    m, d = Icon.mask()
    d.ellipse((132, 132, 892, 892), fill=255)
    d.ellipse((212, 212, 812, 812), fill=0)
    for box in ((472, 112, 552, 300), (472, 724, 552, 912), (112, 472, 300, 552), (724, 472, 912, 552)):
        d.rectangle(box, fill=255)
    icon.fill(m, GOLD)
    icon.fill(card_mask(392, 352, 632, 672, 32), GOLD)
    icon.cut(text_mask("+", 512, 512, 22))
    icons["j54_bounty"] = icon

    # Cut: one clean slice through a pair of cards, the top halves lifted off,
    # with a dashed guide on both sides (precise: this group, these two).
    cards = Icon()
    stack_cards(cards, [card_shape(192, 252, 492, 712), card_shape(532, 252, 832, 712)], RED)
    below = poly_mask([(0, 640), (S, 400), (S, S), (0, S)])
    above = poly_mask([(0, 580), (S, 340), (S, 0), (0, 0)])
    icon = Icon()
    lower = cards.image.copy()
    lower.putalpha(ImageChops.multiply(lower.getchannel("A"), below))
    upper = cards.image.copy()
    upper.putalpha(ImageChops.multiply(upper.getchannel("A"), above))
    icon.image = Image.alpha_composite(lower, upper.transform((S, S), Image.Transform.AFFINE, (1, 0, -30, 0, 1, 90)))
    m, d = Icon.mask()
    for x0, x1 in ((96, 166), (858, 928)):  # on the slice's centre line, clear of the cards
        d.line([(x0, 610 - x0 * 240 / S), (x1, 610 - x1 * 240 / S)], fill=255, width=36)
    icon.fill(m, RED)
    icons["j54_cut"] = icon

    # Hot purge: a fanned hand of three cards beside a hot thermometer
    # (coarse: three of one hot rank, the rank drawn by J-54).
    icon = Icon()
    pivot = (400, 940)
    stack_cards(icon, [card_shape(290, 380, 510, 740, a, pivot) for a in (-18, 18, 0)], RED)
    m, d = Icon.mask()
    d.rounded_rectangle((762, 150, 862, 740), 50, fill=255)
    d.ellipse((812 - 108, 772 - 108, 812 + 108, 772 + 108), fill=255)
    icon.cut(outline(m, 30))
    icon.fill(m, RED)
    m, d = Icon.mask()
    d.rounded_rectangle((790, 178, 834, 760), 22, fill=255)
    d.ellipse((812 - 80, 772 - 80, 812 + 80, 772 + 80), fill=255)
    icon.cut(m)
    m, d = Icon.mask()
    d.rounded_rectangle((800, 250, 824, 780), 12, fill=255)
    d.ellipse((812 - 56, 772 - 56, 812 + 56, 772 + 56), fill=255)
    icon.fill(m, RED)
    icons["j54_hot_purge"] = icon

    # Release: the Joker's card goes down into the deck.
    icon = Icon()
    icon.fill(card_shape(352, 112, 672, 532), GOLD)
    icon.cut(jester_mask(512, 330, 230))
    m, d = Icon.mask()
    d.rectangle((474, 552, 550, 652), fill=255)
    d.polygon([(382, 640), (642, 640), (512, 760)], fill=255)
    for y in (790, 860):
        d.rounded_rectangle((212, y, 812, y + 48), 16, fill=255)
    icon.fill(m, GOLD)
    icons["j54_release"] = icon

    return icons


# ------------------------------------------------------------------ review sheet


def review_sheet(images: dict[str, Image.Image], path: Path) -> None:
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    mattes = ((0x17, 0x17, 0x19), (0x1E, 0x25, 0x23), (0x26, 0x3B, 0x34), (0xE6, 0xE0, 0xD2))
    sizes = (128, 64, 36, 30, 20)
    row_h, label_w = 150, 170
    col_w = sum(sizes) + 12 * len(sizes) + 12
    sheet = Image.new("RGB", (label_w + col_w * len(mattes), 40 + row_h * len(images)), (0x12, 0x12, 0x14))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), "J-54 v2 icons  /  128 64 36 30 20 px  /  stock, panel, felt, ivory", font=font, fill=(0xE6, 0xE0, 0xD2))
    for row, (asset_id, image) in enumerate(images.items()):
        y = 40 + row * row_h
        draw.text((12, y + 60), asset_id, font=font, fill=(0xE6, 0xE0, 0xD2))
        for col, matte in enumerate(mattes):
            x = label_w + col * col_w
            draw.rectangle((x + 4, y + 4, x + col_w - 4, y + row_h - 4), fill=matte)
            cx = x + 12
            for size in sizes:
                icon = image.resize((size, size), Image.Resampling.LANCZOS)
                sheet.paste(icon, (cx, y + (row_h - size) // 2), icon)
                cx += size + 12
    sheet.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="output/j54_icons", help="folder for the 256 px PNGs")
    parser.add_argument("--force", action="store_true", help="replace existing PNGs in --out")
    parser.add_argument("--sheet", default="output/j54_icons/review.png", help="review sheet path ('' to skip)")
    args = parser.parse_args()

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    images = {asset_id: icon.final() for asset_id, icon in draw_all().items()}
    for asset_id, image in images.items():
        assert image.size == (OUT_SIZE, OUT_SIZE) and image.getbbox()
        assert all(image.getpixel(p)[3] == 0 for p in ((0, 0), (255, 0), (0, 255), (255, 255)))
        path = out / f"{asset_id}.png"
        if path.exists() and not args.force:
            raise SystemExit(f"Refusing to replace {path}; pass --force.")
        image.save(path, optimize=True)
    if args.sheet:
        sheet = ROOT / args.sheet
        sheet.parent.mkdir(parents=True, exist_ok=True)
        review_sheet(images, sheet)
        print(f"Review sheet: {sheet}")
    print(f"Wrote {len(images)} icons to {out}")


if __name__ == "__main__":
    main()
