"""Draw a small red-and-black casino asset candidate pack with Pillow.

Run from the repository root:
    python scripts/generate_casino_assets.py --out output/casino_red_black_v4

The candidate pack stays separate from installed game art. Originals are never
overwritten. Text and chip denominations appear only in the presentation sheet.
"""

from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BLACK = "#181719"
CHARCOAL = "#292529"
RED = "#9C2937"
RUBY = "#72212C"
OXBLOOD = "#35171E"
IVORY = "#EEE5D5"
MUTED = "#B5A699"
SCALE = 3


class Canvas:
    """Draw at triple resolution, then reduce for clean transparent edges."""

    def __init__(self, size, color=(0, 0, 0, 0), scale=SCALE):
        self.size = size
        self.scale = scale
        self.image = Image.new("RGBA", tuple(v * scale for v in size), color)
        self.draw = ImageDraw.Draw(self.image)

    def box(self, rect):
        return tuple(round(v * self.scale) for v in rect)

    def rounded(self, rect, radius, fill=None, outline=None, width=1):
        self.draw.rounded_rectangle(self.box(rect), round(radius * self.scale),
                                    fill=fill, outline=outline, width=round(width * self.scale))

    def ellipse(self, rect, fill=None, outline=None, width=1):
        self.draw.ellipse(self.box(rect), fill=fill, outline=outline,
                          width=max(1, round(width * self.scale)))

    def line(self, points, fill, width=1):
        self.draw.line([self.box(p) for p in points], fill=fill,
                       width=max(1, round(width * self.scale)), joint="curve")

    def polygon(self, points, fill):
        self.draw.polygon([self.box(p) for p in points], fill=fill)

    def finish(self):
        image = self.image.resize(self.size, Image.Resampling.LANCZOS)
        # Keep fully transparent pixels black for predictable compression.
        clean = Image.new("RGBA", self.size)
        clean.paste(image, mask=image.getchannel("A").point(lambda a: 255 if a else 0))
        return clean


def diamond(c, x, y, r, color):
    c.polygon([(x, y - r), (x + r * .65, y), (x, y + r), (x - r * .65, y)], color)


def suit(c, kind, x, y, size, color):
    r = size / 2
    if kind == "diamond":
        diamond(c, x, y, r, color)
    elif kind in ("heart", "spade"):
        direction = 1 if kind == "heart" else -1
        ly = y - direction * r * .38
        for dx in (-.46, .46):
            c.ellipse((x + r * dx - r * .5, ly - r * .5,
                       x + r * dx + r * .5, ly + r * .5), color)
        c.polygon([(x - r * .95, ly), (x + r * .95, ly),
                   (x, y + direction * r * .95)], color)
        if kind == "spade":
            c.polygon([(x, y + r * .15), (x - r * .36, y + r),
                       (x + r * .36, y + r)], color)
    else:
        for dx, dy in ((0, -.45), (-.48, .08), (.48, .08)):
            c.ellipse((x + dx * r - .44 * r, y + dy * r - .44 * r,
                       x + dx * r + .44 * r, y + dy * r + .44 * r), color)
        c.polygon([(x, y), (x - .33 * r, y + r), (x + .33 * r, y + r)], color)


def card(back):
    c = Canvas((512, 768))
    c.rounded((11, 16, 500, 751), 32, IVORY)
    c.rounded((19, 24, 492, 743), 26, outline=MUTED, width=1)
    if back:
        c.rounded((26, 31, 485, 736), 21, BLACK)
        c.rounded((34, 39, 477, 728), 15, outline=RED, width=3)
        c.rounded((45, 50, 466, 717), 8, RUBY)
        # A repeated diamond weave, rotationally symmetric about the card centre.
        for j in range(-9, 10):
            y = 383.5 + j * 48
            for i in range(-6, 7):
                x = 255.5 + i * 48
                c.line([(x, y - 24), (x + 24, y), (x, y + 24),
                        (x - 24, y), (x, y - 24)], "#9E4550", 1.1)
                suit(c, "diamond", x, y, 9, "#C18B86")
                c.ellipse((x + 22, y + 22, x + 26, y + 26), "#B06A6F")
        # Clip the weave into the inset; preserve the border underneath.
        inset = Image.new("L", c.image.size)
        ImageDraw.Draw(inset).rounded_rectangle(c.box((45, 50, 466, 717)), 8 * c.scale, fill=255)
        border = Canvas((512, 768))
        border.rounded((11, 16, 500, 751), 32, IVORY)
        border.rounded((19, 24, 492, 743), 26, outline=MUTED, width=1)
        border.rounded((26, 31, 485, 736), 21, BLACK)
        border.rounded((34, 39, 477, 728), 15, outline=RED, width=3)
        border.image.paste(c.image, (0, 0), inset)
        c = border
        for x, y in ((37, 42), (474, 725)):
            diamond(c, x, y, 3.2, IVORY)
    else:
        # Indices are painted by the game at the corners; leave those areas open.
        c.rounded((26, 31, 485, 736), 21, outline="#D8CCBC", width=1)
    return c.finish()


def chip(value):
    body, marks, inner, groups = {
        1: (IVORY, BLACK, CHARCOAL, 1),
        5: (RED, IVORY, RUBY, 2),
        10: (BLACK, IVORY, RED, 3),
        25: (RUBY, IVORY, BLACK, 2),
    }[value]
    c = Canvas((256, 256))
    c.ellipse((11, 11, 245, 245), BLACK)
    c.ellipse((14, 14, 242, 242), body)
    c.ellipse((18, 18, 238, 238), outline=marks, width=1)
    for i in range(8):
        theta = i * math.tau / 8
        offsets = [0] if groups == 1 else ([-.085, .085] if groups == 2 else [-.12, 0, .12])
        for offset in offsets:
            a = theta + offset
            span = .062 if groups == 1 else .033
            points = [(128 + r * math.cos(t), 128 + r * math.sin(t))
                      for r, t in ((91, a - span), (111, a - span),
                                   (111, a + span), (91, a + span))]
            c.polygon(points, marks)
        if value == 25:
            a = theta + math.pi / 8
            c.polygon([(128 + r * math.cos(t), 128 + r * math.sin(t))
                       for r, t in ((91, a - .09), (112, a - .09),
                                    (112, a + .09), (91, a + .09))], BLACK)
    c.ellipse((42, 42, 214, 214), inner)
    c.ellipse((46, 46, 210, 210), outline=marks, width=1)
    c.ellipse((51, 51, 205, 205), body)
    for i in range(16):
        a = i * math.tau / 16
        c.ellipse((127 + 69 * math.cos(a), 127 + 69 * math.sin(a),
                   129 + 69 * math.cos(a), 129 + 69 * math.sin(a)), marks)
    c.ellipse((67, 67, 189, 189), BLACK)
    c.ellipse((70, 70, 186, 186), IVORY)
    c.ellipse((75, 75, 181, 181), outline="#CFC1AE", width=1)
    return c.finish()


def table():
    # Design in the game's 1280 x 720 logical coordinates. Side panels cover
    # x=16..256 and x=1024..1264; hands may extend to x=312..968.
    # Keep the table and its visible trim inside the 272..1008 centre column.
    # The lower rail sits below the action buttons and the betting hint.
    c = Canvas((1280, 720), "#141316")
    c.rounded((266, 52, 1014, 704), 32, "#0D0C0F")
    c.rounded((272, 58, 1008, 698), 28, CHARCOAL)
    c.rounded((273, 59, 1007, 697), 27, outline="#594049", width=1)
    c.rounded((279, 65, 1001, 691), 22, RED)
    c.rounded((281, 67, 999, 689), 20, outline="#BC727A", width=1)
    c.rounded((293, 79, 987, 677), 12, "#130F14")
    c.rounded((297, 83, 983, 673), 9, "#211C21")

    # A curved two-tone field gives the skin a recognizable shape even when
    # cards cover the centre. The wager stays on the upper charcoal surface.
    field = Canvas((1280, 720))
    arc = [(x, 311 + 64 * (1 - ((x - 640) / 343) ** 2))
           for x in range(297, 984, 2)]
    field.polygon(arc + [(983, 673), (297, 673)], "#50212E")
    field.line(arc, "#A05666", 1.3)
    field.line([(x, y + 5) for x, y in arc], "#733442", 1)
    mask = Image.new("L", c.image.size)
    ImageDraw.Draw(mask).rounded_rectangle(c.box((297, 83, 983, 673)),
                                           9 * c.scale, fill=255)
    layer = field.image.copy()
    # Clip the field's alpha as well as its rounded outline.
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    c.image.alpha_composite(layer)
    c.draw = ImageDraw.Draw(c.image)
    c.rounded((297, 83, 983, 673), 9, outline="#9B4F5F", width=1)

    # These rails sit outside the widest possible hand, so the diamond weave
    # remains visible throughout play. Match the card back's geometric motif.
    for x in (287, 993):
        for y in range(111, 662, 29):
            diamond(c, x, y, 6.5, "#D1A2A0")
            diamond(c, x, y, 3.7, RUBY)
            c.ellipse((x - .8, y + 13.7, x + .8, y + 15.3), "#D1A2A0")
    # Corner inlays frame the cards without occupying their index areas.
    for x, y in ((310, 96), (970, 96)):
        diamond(c, x, y, 5, "#B3727D")
    # A narrow bottom apron distinguishes the skin during both betting and play.
    c.line([(310, 686), (574, 686)], "#D1A2A0", .8)
    c.line([(706, 686), (970, 686)], "#D1A2A0", .8)
    for kind, x in zip(("spade", "heart", "club", "diamond"), (595, 625, 655, 685)):
        suit(c, kind, x, 686, 8, IVORY)
    # Export directly from the supersampled canvas at the manifest size.
    return c.image.resize((1920, 1080), Image.Resampling.LANCZOS).convert("RGB")


def write_png(image, path):
    # Compare exact RGB(A) PNG against palette PNG. Keep smooth alpha edges.
    options = []
    indexed = image.quantize(colors=192, method=Image.Quantize.FASTOCTREE,
                             dither=Image.Dither.NONE)
    if indexed.palette.mode == "RGBA":
        palette = indexed.getpalette("RGBA")
        # Quantization can average edge alpha into an otherwise solid fill.
        # Snap only the extremes; retain intermediate alpha for antialiasing.
        for i in range(3, len(palette), 4):
            if palette[i] >= 250:
                palette[i] = 255
            elif palette[i] <= 8:
                palette[i] = 0
        indexed.putpalette(palette, rawmode="RGBA")
    for candidate in (image, indexed):
        buf = io.BytesIO()
        candidate.save(buf, format="PNG", optimize=True, compress_level=9)
        options.append(buf.getvalue())
    path.write_bytes(min(options, key=len))


def font(size, display=False):
    fonts = ROOT / "assets" / "fonts"
    choices = sorted(fonts.glob("display*" if display else "ui-bold*"))
    if not choices:
        choices = sorted(fonts.glob("*.ttf"))
    return ImageFont.truetype(str(choices[0]), size) if choices else ImageFont.load_default(size=size)


def overview(images, out):
    image = Image.new("RGB", (1600, 1110), "#151416")
    d = ImageDraw.Draw(image)
    d.text((54, 32), "CASINO / RED & BLACK", font=font(43, True), fill=IVORY)
    d.text((56, 93), "PROCEDURAL ASSET STUDY    /    CENTRE TABLE", font=font(17), fill=MUTED)
    for i, color in enumerate((BLACK, RUBY, RED, IVORY)):
        d.rounded_rectangle((1338 + i * 49, 40, 1374 + i * 49, 76), radius=5, fill=color)
    d.line((54, 135, 1546, 135), fill="#483039", width=1)
    image.paste(images["table_background"].resize((960, 540), Image.Resampling.LANCZOS), (54, 171))
    d.text((54, 731), "01  /  CHARCOAL & RUBY FELT", font=font(22), fill=IVORY)
    d.text((54, 766), "1920 x 1080  /  Trim inside the visible centre column", font=font(17), fill=MUTED)
    for i, asset_id in enumerate(("card_back", "card_front_blank")):
        card_img = images[asset_id].resize((226, 339), Image.Resampling.LANCZOS)
        image.paste(card_img, (1066 + i * 248, 190), card_img)
    d.text((1075, 555), "02  /  DIAMOND WEAVE", font=font(22), fill=IVORY)
    d.text((1075, 590), "512 x 768  /  Matched front & back", font=font(17), fill=MUTED)
    d.text((1075, 620), "No baked ranks or lettering", font=font(17), fill=MUTED)
    d.line((54, 824, 1546, 824), fill="#483039", width=1)
    d.text((54, 861), "03 / HOUSE CHIPS", font=font(22), fill=IVORY)
    d.text((54, 902), "256 x 256 / Transparent PNG", font=font(17), fill=MUTED)
    d.text((54, 934), "Values below are preview overlays.", font=font(17), fill=MUTED)
    for i, value in enumerate((1, 5, 10, 25)):
        x = 620 + i * 235
        rendered = images[f"chip_{value}"].resize((180, 180), Image.Resampling.LANCZOS)
        image.paste(rendered, (x, 857), rendered)
        d.text((x + 90, 947), str(value), anchor="mm", font=font(29), fill=BLACK)
        d.text((x + 90, 1053), f"CHIP {value}", anchor="mm", font=font(15), fill=MUTED)
    image.save(out / "overview.png", optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "casino_red_black_v4")
    args = ap.parse_args()
    out = args.out.resolve()
    # Refuse any existing folder, preventing accidental changes to source art.
    if out.exists():
        ap.error(f"Output already exists; choose a new candidate folder: {out}")
    out.mkdir(parents=True)
    assets = out / "assets"
    assets.mkdir()
    images = {"card_back": card(True), "card_front_blank": card(False),
              **{f"chip_{v}": chip(v) for v in (1, 5, 10, 25)}, "table_background": table()}
    rows = []
    for asset_id, image in images.items():
        path = assets / f"{asset_id}.png"
        write_png(image, path)
        # Present exactly the saved files, including their chosen encoding.
        images[asset_id] = Image.open(path).convert("RGBA" if asset_id != "table_background" else "RGB")
        rows.append({"id": asset_id, "size": list(image.size), "bytes": path.stat().st_size})
    overview(images, out)
    report = {"palette": {"black": BLACK, "red": RED, "ruby": RUBY, "ivory": IVORY},
              "source": "scripts/generate_casino_assets.py", "assets": rows,
              "total_bytes": sum(row["bytes"] for row in rows)}
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
