"""Complete Poker Head's classic theme in a new, independent preview folder.

    python scripts/generate_poker_head_theme.py --out output/poker_head_theme_v1

The installed floral back and blank front are copied byte-for-byte. Other
art is proposed in the output folder; no game catalog or saves are changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import zipfile

from PIL import Image, ImageDraw

from generate_casino_assets import Canvas, diamond, font, write_png
from generate_cosmetic_assets import clipped, flower

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "assets/cosmetics/procedural"
INK = "#171C1B"
GREEN = "#1D3029"
GOLD = "#B7A477"
BRIGHT_GOLD = "#D5B975"
IVORY = "#F1E6D2"
ALIASES = {"card_back": "card_back_poker_head",
           "card_front_blank": "card_front_poker_head",
           "table_background": "table_poker_head", "avatar": "avatar_poker_head_j",
           **{f"chip_{v}": f"chips_poker_head_{v}" for v in (1, 5, 10, 25)}}
ASSET_BASES = {asset: base for base, asset in ALIASES.items()} | {
    "card_back_poker_head_gold": "card_back"}


def curve(c, points, color=GOLD, width=1):
    a, b, cc, d = points
    samples = []
    for i in range(33):
        t = i / 32
        samples.append(tuple((1-t)**3*a[k] + 3*(1-t)**2*t*b[k]
                             + 3*(1-t)*t*t*cc[k] + t**3*d[k] for k in (0, 1)))
    c.line(samples, color, width)


def decorated_table():
    """Add just two small floral corners and two quiet side ornaments."""
    base = Image.open(SOURCE / "table_poker_head.png").convert("RGBA")
    c = Canvas((1280, 720))
    for mirror in (False, True):
        point = lambda x, y: (1280-x if mirror else x, y)
        curve(c, [point(319, 149), point(319, 120), point(348, 112), point(385, 112)], GOLD, 1)
        for x, y, tilt in ((327, 130, -1), (345, 117, 1), (365, 112, -1)):
            c.polygon([point(x-6, y-tilt*3), point(x, y-6),
                       point(x+5, y+tilt*2), point(x, y+2)], GOLD)
        x, y = point(337, 137)
        flower(c, x, y, 5, BRIGHT_GOLD, GREEN)
        x, y = point(383, 112)
        diamond(c, x, y, 3.5, GOLD)
        x, y = point(318, 394)
        flower(c, x, y, 5.5, GOLD, GREEN)
        c.line([point(318, 407), point(318, 419)], GOLD, .8)
        diamond(c, *point(318, 423), 2.8, GOLD)
    overlay = c.finish().resize(base.size, Image.Resampling.LANCZOS)
    base.alpha_composite(overlay)
    return base.convert("RGB")


def gilt_back():
    """A plain rose field with a gold lattice and a broad gilded frame."""
    base = Image.open(SOURCE / "card_back_poker_head.png").convert("RGBA")
    c = Canvas(base.size)
    c.rounded((34, 34, 477, 733), 11, "#8E3C59")
    lattice = Canvas(base.size)
    # Retain the approved lattice spacing over an uninterrupted rose field.
    for index in range(-20, 21):
        total = 255.5+383.5+31+index*62
        difference = 255.5-383.5+31+index*62
        lattice.line([(0, total), (511, total-511)], BRIGHT_GOLD, 3.2)
        lattice.line([(0, -difference), (511, 511-difference)], BRIGHT_GOLD, 3.2)
    clipped(c, lattice, (44, 44, 467, 723), 8)
    c.rounded((8, 8, 503, 759), 34, outline=GOLD, width=2.4)
    c.rounded((18, 18, 493, 749), 25, outline=BRIGHT_GOLD, width=26)
    c.rounded((22, 22, 489, 745), 21, outline=GOLD, width=1.5)
    c.rounded((42, 42, 469, 725), 10, outline=INK, width=3)
    for flip_x, flip_y in ((False, False), (True, False), (False, True), (True, True)):
        point = lambda x, y: (511-x if flip_x else x, 767-y if flip_y else y)
        c.line([point(48, 111), point(48, 48), point(111, 48)], BRIGHT_GOLD, 2.5)
        curve(c, [point(54, 91), point(75, 96), point(96, 75), point(91, 54)], BRIGHT_GOLD, 2)
        for x, y in ((64, 87), (85, 67)):
            c.polygon([point(x-6, y-2), point(x+1, y-5),
                       point(x+6, y+2), point(x-1, y+5)], BRIGHT_GOLD)
        diamond(c, *point(53, 53), 4, BRIGHT_GOLD)
    base.alpha_composite(c.finish())
    return base


def classic_chip(value):
    body = {1: IVORY, 5: "#A23D43", 10: "#344B72", 25: "#3B6552"}[value]
    stripe = "#355144" if value == 1 else IVORY
    c = Canvas((256, 256))
    c.ellipse((11, 11, 245, 245), INK)
    c.ellipse((15, 15, 241, 241), body)
    # Eight broad inlays, clipped naturally by the outer circumference.
    for i in range(8):
        angle = i * math.tau / 8
        outer = [(128+113*math.cos(angle-.105+j*.21/8),
                  128+113*math.sin(angle-.105+j*.21/8)) for j in range(9)]
        inner = [(128+89*math.cos(angle+.105-j*.21/8),
                  128+89*math.sin(angle+.105-j*.21/8)) for j in range(9)]
        c.polygon(outer+inner, stripe)
    c.ellipse((19, 19, 237, 237), outline=INK, width=1)
    c.ellipse((45, 45, 211, 211), outline=INK, width=2)
    c.ellipse((51, 51, 205, 205), outline=stripe, width=1.5)
    c.ellipse((69, 69, 187, 187), GOLD)
    c.ellipse((73, 73, 183, 183), IVORY)
    return c.finish()


def monogram_avatar():
    c = Canvas((256, 256))
    c.ellipse((10, 10, 246, 246), INK)
    c.ellipse((15, 15, 241, 241), GOLD)
    c.ellipse((19, 19, 237, 237), GREEN)
    c.ellipse((26, 26, 230, 230), outline=GOLD, width=1)
    # The requested J is the identity of the avatar, not a UI label.
    face = font(172*c.scale, display=True)
    bounds = c.draw.textbbox((0, 0), "J", font=face)
    x = 128*c.scale - (bounds[0]+bounds[2])/2
    y = 126*c.scale - (bounds[1]+bounds[3])/2
    c.draw.text((round(x), round(y)), "J", font=face, fill=BRIGHT_GOLD)
    flower(c, 128, 211, 5, GOLD, GREEN)
    return c.finish()


def presentation(images, out):
    sheet = Image.new("RGB", (1800, 1420), INK)
    d = ImageDraw.Draw(sheet)
    d.text((48, 28), "POKER HEAD / THE HOUSE COLLECTION", font=font(40, True), fill=IVORY)
    d.text((50, 90), "FOREST FELT / ROSE FLORALS / OLD GOLD / CLASSIC CASINO CHIPS",
           font=font(18), fill=GOLD)
    d.line((48, 130, 1752, 130), fill="#455044")
    for i, (asset, label) in enumerate((("card_back_poker_head", "ORIGINAL / UNCHANGED"),
                                       ("card_back_poker_head_gold", "NEW / GOLD LATTICE EDITION"),
                                       ("card_front_poker_head", "SHARED FRONT / UNCHANGED"))):
        x = 48+i*360
        image = images[asset].resize((256, 384), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, 165), image)
        d.text((x, 573), label, font=font(18), fill=IVORY)
    d.text((1210, 167), "GOLD J / PLAYER AVATAR", font=font(21), fill=IVORY)
    for x, y, size in ((1265, 220, 256), (1580, 292, 64), (1678, 300, 48)):
        image = images["avatar_poker_head_j"].resize((size, size), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y), image)
        d.text((x+size/2, y+size+16), str(size), anchor="mt", font=font(17), fill=GOLD)
    d.line((48, 630, 1752, 630), fill="#455044")
    d.text((48, 658), "GREEN TABLE / A FEW GOLDEN FLOURISHES", font=font(23), fill=IVORY)
    image = images["table_poker_head"].resize((1110, 624), Image.Resampling.LANCZOS)
    sheet.paste(image, (48, 705))
    d.text((1210, 658), "CLASSIC STRIPED CHIPS", font=font(23), fill=IVORY)
    for i, value in enumerate((1, 5, 10, 25)):
        x, y = 1220+(i%2)*275, 740+(i//2)*290
        image = images[f"chips_poker_head_{value}"].resize((214, 214), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y), image)
        d.text((x+107, y+107), str(value), anchor="mm", font=font(34), fill=INK)
        d.text((x+107, y+239), f"CHIP {value}", anchor="mm", font=font(17), fill=GOLD)
    d.text((48, 1370), "Independent preview / Original assets preserved / Values on chips are runtime overlays",
           font=font(19), fill=GOLD)
    sheet.save(out / "overview.png", optimize=True)

    detail = Image.new("RGB", (1180, 870), "#222824")
    draw = ImageDraw.Draw(detail)
    draw.text((35, 24), "POKER HEAD / AVATAR & CLASSIC CHIPS", font=font(29, True), fill=IVORY)
    for x, y, size in ((50, 100, 256), (380, 160, 128), (590, 190, 64), (735, 198, 48)):
        image = images["avatar_poker_head_j"].resize((size, size), Image.Resampling.LANCZOS)
        detail.paste(image, (x, y), image)
        draw.text((x+size/2, y+size+18), str(size), anchor="mt", font=font(17), fill=GOLD)
    draw.text((860, 196), "GOLD J", font=font(32, True), fill=BRIGHT_GOLD)
    draw.text((860, 250), "256 x 256 / Transparent", font=font(17), fill=GOLD)
    draw.line((35, 419, 1145, 419), fill="#455044")
    for i, value in enumerate((1, 5, 10, 25)):
        x = 40+i*290
        for dx, y, size in ((0, 455, 200), (55, 716, 76)):
            image = images[f"chips_poker_head_{value}"].resize((size, size), Image.Resampling.LANCZOS)
            detail.paste(image, (x+dx, y), image)
            draw.text((x+dx+size/2, y+size/2), str(value), anchor="mm",
                      font=font(32 if size==200 else 20), fill=INK)
        draw.text((x+100, 679), f"CHIP {value}", anchor="mm", font=font(19), fill=IVORY)
        draw.text((x+93, 815), "76 x 76", anchor="mm", font=font(15), fill=GOLD)
    detail.save(out / "avatars_chips_preview.png", optimize=True)
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    from chaos_blackjack.gui.components.cards import CARD_SIZE
    cards = Image.new("RGB", (1180, 610), "#222824")
    draw = ImageDraw.Draw(cards)
    draw.text((35, 24), "POKER HEAD / GOLD LATTICE EDITION", font=font(30, True), fill=IVORY)
    draw.line((590, 100, 590, 565), fill="#455044")
    for x, asset, label in ((45, "card_back_poker_head", "ORIGINAL / UNCHANGED"),
                            (625, "card_back_poker_head_gold", "WIDE GOLD FRAME & LATTICE")):
        for dx, y, size in ((0, 110, (256, 384)), (309, 230, CARD_SIZE)):
            image = images[asset].resize(size, Image.Resampling.LANCZOS)
            cards.paste(image, (x+dx, y), image)
        draw.text((x, 533), label, font=font(19), fill=IVORY)
        draw.text((x+309, 438), f"{CARD_SIZE[0]} x {CARD_SIZE[1]}", font=font(17), fill=GOLD)
    cards.save(out / "card_backs_preview.png", optimize=True)


def runtime_previews(out):
    os.environ.update(PYGAME_HIDE_SUPPORT_PROMPT="1", SDL_VIDEODRIVER="dummy",
                      SDL_AUDIODRIVER="dummy", CHAOS_USE_LLM="0", CHAOS_DB=":memory:")
    import pygame
    from chaos_blackjack.gui.assets.manifest import MANIFEST, AssetSpec
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.view import TablePhase
    from chaos_blackjack.data.balance import default_balance
    from chaos_blackjack.modes import get_mode
    from preview_assets import render_scene, matte_sheet, zoom_cards, zoom_chips
    from validate_assets import check, subject_rect
    import chaos_blackjack.gui.scenes  # noqa: F401

    pygame.init()
    rows = []
    for asset, base in ASSET_BASES.items():
        spec = MANIFEST[base]
        MANIFEST[asset] = AssetSpec(asset, spec.category, spec.size, spec.placeholder)
        rows.append(check(asset, [out / "assets" / f"{asset}.png"], 64))
    front = subject_rect(out / "assets/card_front_poker_head.png")
    for asset in ("card_back_poker_head", "card_back_poker_head_gold"):
        back = subject_rect(out / "assets" / f"{asset}.png")
        if back is None or front is None or max(abs(a-b) for a, b in zip(back, front)) > 2:
            raise RuntimeError(f"Card outlines differ: {asset}")
    (out / "validation.json").write_text(json.dumps(rows, indent=2)+"\n", encoding="utf-8")
    if any(row["status"] != "OK" for row in rows):
        raise RuntimeError(f"Asset validation failed: {rows}")
    app = App(GuiSettings(asset_dirs=(out / "assets", ROOT / "assets")))
    previews = out / "previews"
    previews.mkdir()
    mode = get_mode("chaos")

    def controller_for(seed):
        config = mode.apply(RunConfig.from_balance(default_balance(), seed=seed, use_llm=False))
        controller = GameController(config)
        # Use the offered opening choices just as the player does.
        if controller.choice is not None:
            controller.choose(controller.choice.options[0].id)
        return controller

    def settle_fx(scene):
        scene._pump_notices()
        scene._sync_widgets()
        scene.fx.update(2.0)

    for variant, back in (("original", "card_back_poker_head"), ("gold", "card_back_poker_head_gold")):
        app.assets.set_aliases(ALIASES | {"card_back": back})
        controller = controller_for(7)
        pygame.image.save(render_scene(app, "table", controller=controller, setup=settle_fx),
                          str(previews / f"table_betting_{variant}.png"))
        for seed in range(1, 100):
            controller = controller_for(seed)
            controller.place_bet(controller.view().bet_min)
            if controller.phase == TablePhase.CHAOS:
                controller.resolve_chaos()
            if controller.phase == TablePhase.PLAYER_TURN:
                break
        else:
            raise RuntimeError("No seeded player-turn preview")
        pygame.image.save(render_scene(app, "table", controller=controller, setup=settle_fx),
                          str(previews / f"table_play_{variant}.png"))
        pygame.image.save(zoom_cards(app), str(previews / f"zoom_cards_{variant}.png"))
    app.assets.set_aliases(ALIASES)
    pygame.image.save(zoom_chips(app), str(previews / "zoom_chips.png"))
    for asset in ASSET_BASES:
        pygame.image.save(matte_sheet(app, asset), str(previews / f"matte_{asset}.png"))
    checks = Image.new("RGB", (1500, 1900), INK)
    draw = ImageDraw.Draw(checks)
    for index, asset in enumerate(ASSET_BASES):
        x, y = (index%2)*750, (index//2)*380
        draw.text((x+20, y+15), asset, font=font(19), fill=IVORY)
        with Image.open(previews / f"matte_{asset}.png") as matte:
            matte.thumbnail((710, 315), Image.Resampling.LANCZOS)
            checks.paste(matte, (x+20, y+50))
    checks.save(out / "quality_checks.png", optimize=True)
    app.audio.close()
    pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out.resolve()
    if out.exists():
        parser.error(f"Output already exists; choose a new folder: {out}")
    (out / "assets").mkdir(parents=True)
    originals = ("card_back_poker_head", "card_front_poker_head")
    images = {asset: Image.open(SOURCE / f"{asset}.png").convert("RGBA") for asset in originals}
    images.update({"table_poker_head": decorated_table(), "card_back_poker_head_gold": gilt_back(),
                   "avatar_poker_head_j": monogram_avatar(),
                   **{f"chips_poker_head_{v}": classic_chip(v) for v in (1, 5, 10, 25)}})
    rows = []
    for asset, image in images.items():
        path = out / "assets" / f"{asset}.png"
        if asset in originals:
            shutil.copy2(SOURCE / path.name, path)
            assert path.read_bytes() == (SOURCE / path.name).read_bytes()
        else:
            write_png(image, path)
        images[asset] = Image.open(path).convert("RGB" if asset=="table_poker_head" else "RGBA")
        rows.append({"id": asset, "size": list(image.size), "bytes": path.stat().st_size,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "unchanged_copy": asset in originals})
    report = {"source": "scripts/generate_poker_head_theme.py",
              "status": "independent preview; not installed", "aliases": ALIASES,
              "asset_bases": ASSET_BASES, "assets": rows,
              "total_bytes": sum(row["bytes"] for row in rows),
              "source_art": {asset: str((SOURCE / f"{asset}.png").relative_to(ROOT)).replace("\\", "/")
                             for asset in (*originals, "table_poker_head")}}
    (out / "manifest.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    presentation(images, out)
    runtime_previews(out)
    (out / "README.md").write_text("""# Poker Head: the House Collection

Independent procedural preview, not installed or registered in the game.

- The original floral card back and blank front are copied byte-for-byte.
- The green table gains only two floral corners and two quiet side ornaments.
- The extra gold card back uses plain rose beneath a gold diamond lattice,
  with a broad 26-pixel gilded frame and four small leaf ornaments. The old
  four-petal repeat is absent from this variant.
- The player avatar is a gold serif J on dark green.
- The four classic chips use white, red, deep blue and green bodies, broad
  contrasting edge inlays and an ivory centre. Values remain game overlays.

`overview.png` presents all nine PNGs; `avatars_chips_preview.png` compares
the J avatar at 256, 128, 64 and 48 pixels and chips at 200 and 76 pixels.
`card_backs_preview.png` compares the original and gold-lattice backs at
256 x 384 and the game's actual card size.
`previews/` contains actual Poker Head betting/play screens and card close-ups
for both back variants, chip close-ups and dark/felt/white matte checks.
`validation.json` checks delivery sizes, transparency and card outlines.
The installed artwork, game catalog, character portraits and saves are unchanged.

Reproduce with a new output directory:
`python scripts/generate_poker_head_theme.py --out output/poker_head_theme_preview`
""", encoding="utf-8")
    with zipfile.ZipFile(out / "poker_head_theme_preview.zip", "w", zipfile.ZIP_DEFLATED) as pack:
        for path in sorted(out.rglob("*")):
            if path.is_file() and path.suffix!=".zip":
                pack.write(path, path.relative_to(out).as_posix())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
