"""Draw original SVG studies for five unassigned Poker Head item icons.

Uses geometric silhouettes, original vector lettering, and transparent
cutouts. Existing Game Icons are only shown alongside as style references;
their path data is never embedded in these original drawings.

Run from the repository root: python scripts/draw_poker_head_icons.py
Review output stays under output/, and original SVGs stay in the art repo.
No runtime assets or candidate approvals are changed.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from xml.etree import ElementTree

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/poker_head_icons/code_studies_v2"
RAW = ROOT / "black-jack-assets/source/code-icons/poker-head-v2"
GOLD = "#B7A477"
BG = "#171C1B"
INK = "#E6E0D2"
MUTED = "#949F98"


class Drawing:
    def __init__(self):
        self.body = []
        self.holes = []
        self.operations = []

    def add(self, tag, cut=False, **attrs):
        attrs = {key.replace("_", "-"): str(value) for key, value in attrs.items()}
        attrs.setdefault("fill", "black" if cut else GOLD)
        element = ElementTree.Element(tag, attrs)
        fragment = ElementTree.tostring(element, encoding="unicode")
        (self.holes if cut else self.body).append(fragment)
        self.operations.append((cut, fragment))

    def path(self, d, cut=False, **attrs):
        self.add("path", cut, d=d, **attrs)

    def rect(self, x, y, width, height, radius=0, cut=False, **attrs):
        self.add("rect", cut, x=x, y=y, width=width, height=height, rx=radius, **attrs)

    def circle(self, x, y, radius, cut=False, **attrs):
        self.add("circle", cut, cx=x, cy=y, r=radius, **attrs)

    def line(self, d, width=16, cut=False, **attrs):
        self.path(d, cut, fill="none", stroke="black" if cut else GOLD,
                  stroke_width=width, stroke_linecap="round", stroke_linejoin="round", **attrs)

    def glyph(self, text, x, y, height, cut=True):
        # Hand-drawn single-stroke glyphs; no system font dependency in SVGs.
        paths = {
            "A": "M 5,68 L 27,3 L 49,68 M 13,46 H 41 M 0,68 H 17 M 37,68 H 54",
            "1": "M 12,15 L 31,3 V 68 M 14,68 H 48",
            "2": "M 5,16 Q 7,3 26,3 Q 48,3 48,20 Q 48,30 30,44 L 5,68 H 49",
            "4": "M 39,3 L 5,44 H 51 M 39,3 V 68",
            "x": "M 9,19 L 45,55 M 45,19 L 9,55",
            "+": "M 7,36 H 47 M 27,16 V 56",
        }
        scale = height / 72
        for index, char in enumerate(text):
            self.line(paths[char], width=9, cut=cut,
                      transform=f"translate({x + index * 66 * scale} {y}) scale({scale})")

    def card(self, x, y, width, height, mark="", mark_height=80):
        self.rect(x, y, width, height, 14)
        if mark:
            text_width = (len(mark) * 66 - 12) * mark_height / 72
            self.glyph(mark, x + (width - text_width) / 2, y + (height - mark_height) / 2,
                       mark_height)

    def coin(self, x, y, radius):
        self.circle(x, y, radius)
        self.circle(x, y, radius - 14, cut=True)
        self.circle(x, y, radius - 24)

    def svg(self):
        masks = []
        scene = ""
        for index, (cut, fragment) in enumerate(self.operations):
            if cut:
                mask_id = f"cut{index}"
                masks.append(f'<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="0" y="0" '
                             'width="512" height="512"><rect width="512" height="512" '
                             f'fill="white"/>{fragment}</mask>')
                scene = f'<g mask="url(#{mask_id})">{scene}</g>'
            else:
                scene += fragment
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
                'viewBox="0 0 512 512"><defs>' + ''.join(masks) + '</defs>' + scene + '</svg>\n')


def hand(d, x=228, y=290, scale=1):
    d.path("M 0,88 L 45,70 C 74,58 89,68 112,61 L 165,37 "
           "C 181,29 189,37 178,48 L 133,77 L 185,57 "
           "C 199,52 207,64 192,74 L 144,105 C 115,125 93,131 65,123 "
           "L 40,116 L 0,137 Z", transform=f"translate({x} {y}) scale({scale})")


def crown(d, x, y, scale=1):
    d.path("M 0,15 L 30,39 L 53,0 L 78,39 L 108,15 L 94,76 H 14 Z",
           transform=f"translate({x} {y}) scale({scale})")
    d.rect(x + 13 * scale, y + 86 * scale, 82 * scale, 13 * scale, 3 * scale)


def studies():
    drawings = []
    # Borrowed Blossom: victory travels to the receiver, not card exchange.
    d = Drawing()
    d.path("M 71,63 H 223 L 210,132 Q 202,172 162,182 V 215 H 205 V 238 H 87 V 215 H 130 V 182 Q 92,173 84,133 Z")
    d.line("M 76,82 H 47 Q 31,141 94,150 M 218,82 H 247 Q 262,141 198,150", 17)
    d.line("M 243,188 Q 324,186 352,270", 26)
    d.path("M 310,259 L 356,309 L 380,245 Z")
    hand(d, 214, 318, 1.18)
    crown(d, 289, 305, .52)
    drawings.append(("borrowed_blossom", "a", "Victory cup to receiving hand", d))

    d = Drawing()
    d.card(43, 70, 174, 224, "21", 82)
    d.line("M 243,126 Q 355,106 388,212", 24)
    d.path("M 349,209 L 392,254 L 416,189 Z")
    crown(d, 309, 270, 1.15)
    hand(d, 222, 340, 1.05)
    drawings.append(("borrowed_blossom", "b", "Natural 21 transfers a victory crown", d))

    # Risk Sharing: four portions, with just one protected by the agreement.
    d = Drawing()
    for x, y in [(123, 126), (123, 344), (350, 344)]:
        d.coin(x, y, 64)
    d.path("M 270,52 Q 354,32 438,52 V 132 Q 435,201 354,250 Q 273,201 270,132 Z")
    d.path("M 290,70 Q 354,55 418,70 V 131 Q 416,185 354,225 Q 292,185 290,131 Z", cut=True)
    d.circle(354, 127, 39)
    d.circle(354, 127, 24, cut=True)
    drawings.append(("risk_sharing", "a", "One of four loss portions protected", d))

    d = Drawing()
    d.circle(220, 282, 164)
    d.circle(220, 282, 145, cut=True)
    d.path("M 220,282 V 157 A 125,125 0 1,0 345,282 Z")
    d.line("M 220,163 V 279 H 340 M 220,279 L 132,366 M 220,279 L 128,190", 15, cut=True)
    d.path("M 274,42 Q 352,27 430,42 V 125 Q 427,188 352,231 Q 277,188 274,125 Z")
    d.path("M 294,59 Q 352,49 410,59 V 125 Q 407,170 352,205 Q 297,170 294,125 Z", cut=True)
    d.line("M 322,123 L 346,148 L 382,94", 17)
    drawings.append(("risk_sharing", "b", "Quarter shield and three exposed portions", d))

    # Grace Approval: explicit +2 authorization and a lifted bust ceiling.
    d = Drawing()
    d.path("M 73,157 H 286 L 350,219 V 451 H 73 Z")
    d.path("M 282,159 V 224 H 348", cut=True)
    d.glyph("+2", 114, 286, 116)
    d.line("M 88,219 H 224", 15, cut=True)
    d.rect(68, 91, 204, 19, 5)
    d.rect(333, 115, 33, 171, 7)
    d.path("M 289,127 L 350,52 L 411,127 Z")
    drawings.append(("grace_approval", "a", "+2 approval document and raised ceiling", d))

    d = Drawing()
    d.rect(59, 264, 262, 174, 18)
    d.glyph("+2", 101, 298, 101)
    d.rect(58, 153, 232, 21, 7)
    d.rect(58, 206, 232, 18, 7)
    d.rect(353, 141, 34, 276, 7)
    d.path("M 307,157 L 370,77 L 433,157 Z")
    d.line("M 76,91 H 270", 17)
    drawings.append(("grace_approval", "b", "Temporary +2 pass with an expanded limit", d))

    # Aces to Top: plural aces, a deck silhouette and one upward direction.
    d = Drawing()
    d.rect(91, 102, 187, 261, 14)
    d.rect(65, 130, 187, 261, 14)
    d.rect(40, 157, 187, 261, 14)
    d.line("M 92,119 H 267 M 65,146 H 239", 13, cut=True)
    d.glyph("A", 96, 215, 123)
    d.rect(343, 160, 44, 196, 6)
    d.path("M 291,177 L 365,81 L 439,177 Z")
    d.line("M 317,385 H 409 M 317,415 H 409", 18)
    drawings.append(("aces_to_top", "a", "Ace stack moving above the deck", d))

    d = Drawing()
    d.rect(96, 330, 320, 46, 10)
    d.rect(109, 389, 294, 23, 8)
    d.rect(122, 427, 268, 21, 7)
    d.rect(72, 130, 180, 177, 12)
    d.rect(93, 102, 180, 177, 12)
    d.rect(114, 73, 180, 177, 12)
    d.line("M 84,281 H 237 M 104,254 H 258", 13, cut=True)
    d.glyph("A", 165, 108, 102)
    d.rect(346, 159, 34, 143, 6)
    d.path("M 300,175 L 363,84 L 426,175 Z")
    drawings.append(("aces_to_top", "b", "Aces lifted out of the deck to its top", d))

    # Quadruple Bet Ticket: numeric identity instead of an unrelated die.
    d = Drawing()
    d.rect(49, 139, 408, 243, 19)
    d.circle(49, 260, 28, cut=True)
    d.circle(457, 260, 28, cut=True)
    for y in [165, 204, 296, 335]:
        d.rect(103, y, 12, 22, 3, cut=True)
    d.glyph("x4", 154, 190, 140)
    d.line("M 410,166 V 354", 12, cut=True)
    drawings.append(("quadruple_bet_ticket", "a", "Fourfold stake preparation ticket", d))

    d = Drawing()
    d.circle(256, 256, 197)
    d.circle(256, 256, 174, cut=True)
    d.circle(256, 256, 153)
    for rotation in range(0, 360, 45):
        d.rect(247, 61, 18, 21, 2, cut=True, transform=f"rotate({rotation} 256 256)")
    d.glyph("x4", 139, 176, 157)
    drawings.append(("quadruple_bet_ticket", "b", "Fourfold wager casino chip", d))
    return drawings


def render(drawing):
    ElementTree.fromstring(drawing.svg())
    frame = '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">{}</svg>'

    def raster(fragment):
        surface = pygame.image.load(io.BytesIO(frame.format(fragment).encode("utf-8")), "icon.svg")
        return Image.frombytes("RGBA", surface.get_size(), pygame.image.tobytes(surface, "RGBA"))

    # pygame's SVG loader silently ignores masks. Apply the original vector
    # drawing operations in order: cuts affect earlier shapes only, so a coin
    # interior can be drawn again after cutting its surrounding ring.
    image = Image.new("RGBA", (512, 512))
    for cut, fragment in drawing.operations:
        layer = raster(fragment)
        if cut:
            image.putalpha(ImageChops.multiply(image.getchannel("A"), ImageChops.invert(layer.getchannel("A"))))
        else:
            image = Image.alpha_composite(image, layer)
    assert image.size == (512, 512) and image.getbbox()
    assert all(image.getpixel(p)[3] == 0 for p in [(0, 0), (511, 0), (0, 511), (511, 511)])
    return image


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    pygame.init()
    drawings = studies()
    images = {}
    records = []
    for key, variant, concept, drawing in drawings:
        asset_id = f"{key}_{variant}"
        svg = drawing.svg()
        raw_path = RAW / f"{asset_id}.svg"
        if raw_path.exists():
            if raw_path.read_text(encoding="utf-8") != svg:
                raise SystemExit(f"Refusing to replace original SVG: {raw_path}; use a new version directory.")
        else:
            raw_path.write_text(svg, encoding="utf-8")
        image = render(drawing)
        images[asset_id] = image
        image.resize((256, 256), Image.Resampling.LANCZOS).save(OUT / f"{asset_id}.png")
        records.append({"key": key, "variant": variant, "concept": concept,
                        "source": str(raw_path.relative_to(ROOT)),
                        "preview": f"{asset_id}.png", "status": "Unapproved original code-drawn study"})

    # Labels belong to this review artifact, not to the game's UI strings.
    labels = ["\u501f\u82b1\u732e\u4f5b", "\u98ce\u9669\u5206\u62c5", "\u5bbd\u9650\u6279\u6761",
              "\u738b\u724c\u5f52\u4f4d", "\u56db\u500d\u62bc\u6ce8\u5238"]
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 23)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
    title = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 30)
    roman = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
    sheet = Image.new("RGB", (1220, 220 + 5 * 230), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((28, 18), "Poker Head / SVG CODE STUDIES", font=title, fill=INK)
    draw.text((28, 64), "#B7A477 / transparent silhouettes / A & B variants / 128px + 48px + 32px", font=roman, fill=MUTED)
    references = ["card-exchange", "coins-pile", "price-tag", "wax-seal", "card-ace-hearts"]
    draw.text((28, 119), "API style references", font=roman, fill=MUTED)
    for i, name in enumerate(references):
        ref = Image.open(ROOT / "output/poker_head_icons/png" / f"{name}.png").convert("RGBA")
        ref.thumbnail((64, 64), Image.Resampling.LANCZOS)
        sheet.paste(ref, (247 + i * 171, 103), ref)
    for row in range(5):
        key = drawings[row * 2][0]
        y = 213 + row * 230
        draw.text((28, y + 52), labels[row], font=font, fill=INK)
        draw.text((28, y + 91), key.replace("_", " "), font=roman, fill=MUTED)
        for column, variant in enumerate(["a", "b"]):
            x = 254 + column * 476
            draw.rounded_rectangle((x, y + 8, x + 452, y + 218), radius=12,
                                   fill="#1E2523", outline="#4A5048", width=2)
            draw.text((x + 15, y + 15), variant.upper(), font=font, fill=GOLD)
            for size, offset in [(128, (55, 36)), (48, (230, 79)), (32, (338, 86))]:
                icon = images[f"{key}_{variant}"].resize((size, size), Image.Resampling.LANCZOS)
                sheet.paste(icon, (x + offset[0], y + offset[1]), icon)
                draw.text((x + offset[0], y + 175), f"{size}px", font=roman, fill=MUTED)
    sheet.save(OUT / "comparison.png")

    matte = Image.new("RGB", (1050, 750), BG)
    md = ImageDraw.Draw(matte)
    md.text((20, 15), "TRANSPARENCY CHECK / A VARIANTS", font=roman, fill=INK)
    for row, color in enumerate(["#171C1B", "#174336", "#F3EEE2"]):
        for column in range(5):
            x = column * 210
            y = 55 + row * 230
            md.rectangle((x + 6, y, x + 204, y + 208), fill=color)
            icon = images[f"{drawings[column * 2][0]}_a"].resize((160, 160), Image.Resampling.LANCZOS)
            matte.paste(icon, (x + 25, y + 24), icon)
    matte.save(OUT / "matte.png")
    (OUT / "manifest.json").write_text(json.dumps({"color": GOLD, "provenance": "Original geometric SVG paths authored in scripts/draw_poker_head_icons.py; no upstream icon paths copied.", "entries": records}, indent=2) + "\n", encoding="utf-8")
    (RAW / "README.md").write_text("# Poker Head original code icon studies\n\nTen unapproved SVG studies for five missing item identities. Source: `scripts/draw_poker_head_icons.py`. All geometric paths and glyphs are original. Existing API artwork is used only as a separate style reference in the review sheet. No runtime integration or selection approval is implied.\n", encoding="utf-8")
    print(f"Rendered and validated {len(records)} transparent 256px studies.")
    print(f"Review sheet: {OUT / 'comparison.png'}")


if __name__ == "__main__":
    main()
