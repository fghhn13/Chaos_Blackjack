"""Draw the ten existing unlockable cosmetics as small, original PNGs.

    python scripts/generate_cosmetic_assets.py --out output/cosmetic_redraw_v1

Output directories must be new. No originals, saves, prices or catalog entries
are modified. Runtime previews use the game's existing asset aliases.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from generate_casino_assets import Canvas, diamond, font, suit, write_png

ROOT = Path(__file__).resolve().parents[1]
IVORY = "#EEE5D5"
DARK = "#17161B"
GOLD = "#C5AD79"


def clipped(canvas, layer, rect, radius):
    mask = Image.new("L", canvas.image.size)
    ImageDraw.Draw(mask).rounded_rectangle(canvas.box(rect), radius * canvas.scale, fill=255)
    image = layer.image.copy()
    image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    canvas.image.alpha_composite(image)
    canvas.draw = ImageDraw.Draw(canvas.image)


def flower(c, x, y, radius, petals, centre):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        cx, cy = x + dx * radius * .66, y + dy * radius * .66
        c.ellipse((cx - radius * .5, cy - radius * .5,
                   cx + radius * .5, cy + radius * .5), petals)
    diamond(c, x, y, radius * .28, centre)


def deck(style, face=False):
    # Match the current default card face's full-canvas rounded silhouette.
    # Every deck's face and back therefore share the same flip geometry.
    c = Canvas((512, 768))
    paper = "#F1E6D2" if style == "poker_head" else IVORY
    c.rounded((0, 0, 511, 767), 42, paper)
    c.rounded((6, 6, 505, 761), 36, outline="#BDAF99", width=1)
    if face:
        # Corner indices are runtime overlays: keep their entire area clean.
        c.rounded((24, 24, 487, 743), 22, outline="#D3C4A7", width=1)
        c.rounded((29, 29, 482, 738), 18, outline="#E2D3BB", width=1)
        for x in (216, 255.5, 295):
            diamond(c, x, 22, 3, "#AA7C87")
            diamond(c, 511 - x, 745, 3, "#AA7C87")
        return c.finish()
    colors = {
        "crimson": ("#54151E", "#8F303D", "#C1A078"),
        "royal": ("#1D2439", "#34405A", "#C6AD78"),
        "poker_head": ("#8E3C59", "#B75C75", "#E9D6B6"),
    }
    base, detail, trim = colors[style]
    c.rounded((18, 18, 493, 749), 25, DARK)
    c.rounded((24, 24, 487, 743), 20, outline=trim, width=2)
    c.rounded((34, 34, 477, 733), 11, base)
    p = Canvas((512, 768))
    if style == "crimson":
        for j in range(-8, 9):
            y = 383.5 + j * 54
            for i in range(-5, 6):
                x = 255.5 + i * 54
                p.line([(x, y - 27), (x + 27, y), (x, y + 27),
                        (x - 27, y), (x, y - 27)], detail, 1.6)
                p.line([(x, y - 20), (x + 20, y), (x, y + 20),
                        (x - 20, y), (x, y - 20)], "#71313A", .9)
                diamond(p, x, y, 5.5, trim)
                p.ellipse((x + 25, y + 25, x + 29, y + 29), "#B8757E")
    elif style == "royal":
        # Repeated fan arches instead of a recoloured lattice.
        for j in range(-5, 6):
            y = 383.5 + j * 80
            for i in range(-4, 5):
                x = 255.5 + i * 80
                for r in (17, 25, 33):
                    points = [(x + r * math.cos(a), y + r * math.sin(a))
                              for a in [math.pi + k * math.pi / 20 for k in range(21)]]
                    p.line(points, trim if r == 25 else detail, 1)
                    p.line([(px, 2*y-py) for px, py in points], trim if r == 25 else detail, 1)
                diamond(p, x, y, 5, trim)
        for x in (49, 462):
            p.line([(x, 51), (x, 716)], trim, 1)
    else:
        # Poker Head's traditional four-petal pink pattern, green stitch accents.
        for j in range(-7, 8):
            y = 383.5 + j * 62
            for i in range(-5, 6):
                x = 255.5 + i * 62
                flower(p, x, y, 15, trim, "#355144")
                diamond(p, x + 31, y + 31, 4.6, "#A9BA9A")
                p.line([(x + 12, y + 12), (x + 25, y + 25)], detail, 1)
                p.line([(x - 12, y - 12), (x - 25, y - 25)], detail, 1)
    clipped(c, p, (34, 34, 477, 733), 11)
    c.rounded((34, 34, 477, 733), 11, outline=trim, width=1)
    return c.finish()


def table(style):
    colors = {
        "midnight": ("#364B6B", "#95ACC6", "#171F31", "#263A58", "#607FA5"),
        "chaos": ("#70507D", "#BA94BF", "#2A2034", "#4D2F4D", "#996380"),
        "poker_head": ("#96805A", "#D5C397", "#1D3029", "#2E4B3D", "#A78C5F"),
    }
    rail, bright, upper, lower, seam = colors[style]
    c = Canvas((1280, 720), "#14161B")
    c.rounded((266, 52, 1014, 704), 32, "#0C0D11")
    c.rounded((272, 58, 1008, 698), 28, "#252630")
    c.rounded((273, 59, 1007, 697), 27, outline=seam, width=1)
    c.rounded((279, 65, 1001, 691), 22, rail)
    c.rounded((281, 67, 999, 689), 20, outline=bright, width=1)
    c.rounded((293, 79, 987, 677), 12, "#101317")
    c.rounded((297, 83, 983, 673), 9, upper)
    field = Canvas((1280, 720))
    if style == "chaos":
        boundary = [(297, 314), (422, 346), (442, 339), (442, 350),
                    (578, 374), (700, 374), (838, 348), (838, 337),
                    (858, 344), (983, 313)]
    else:
        boundary = [(x, 311 + 64 * (1 - ((x - 640) / 343) ** 2))
                    for x in range(297, 984, 2)]
    field.polygon(boundary + [(983, 673), (297, 673)], lower)
    field.line(boundary, seam, 1.5)
    field.line([(x, y + 5) for x, y in boundary], rail, .8)
    clipped(c, field, (297, 83, 983, 673), 9)
    c.rounded((297, 83, 983, 673), 9, outline=seam, width=1)
    for x in (287, 993):
        for index, y in enumerate(range(112, 657, 36)):
            if style == "midnight":
                # Tiny moons and diamonds remain visible outside the hands.
                if index % 3 == 0:
                    c.ellipse((x-4, y-5, x+4, y+5), bright)
                    c.ellipse((x-1, y-6, x+6, y+3), rail)
                else:
                    diamond(c, x, y, 4.3, bright)
                c.line([(x, y+9), (x, y+21)], seam, .8)
            elif style == "chaos":
                offset = 1.5 if index % 2 else -1.5
                c.line([(x-4, y-6), (x+4, y-6), (x+4, y+6)], bright, 1.2)
                c.line([(x-4+offset, y-3), (x-4+offset, y+8), (x+2, y+8)], bright, 1.2)
                diamond(c, x, y, 2.7, "#D0AFBF")
            else:
                flower(c, x, y, 4.6, bright, upper)
                c.ellipse((x-1, y+17, x+1, y+19), bright)
    for x in (311, 969):
        if style == "midnight":
            suit(c, "spade", x, 98, 9, bright)
        elif style == "chaos":
            c.line([(x-5, 98), (x, 93), (x+5, 98), (x, 103)], bright, 1)
        else:
            flower(c, x, 98, 5, bright, lower)
    c.line([(310, 686), (574, 686)], bright, .8)
    c.line([(706, 686), (970, 686)], bright, .8)
    for kind, x in zip(("spade", "heart", "club", "diamond"), (595, 625, 655, 685)):
        suit(c, kind, x, 686, 8, bright)
    return c.image.resize((1920, 1080), Image.Resampling.LANCZOS).convert("RGB")


def chip(style, value):
    colors = {
        "neon": {1: "#BBCDCB", 5: "#C879A3", 10: "#62B5C2", 25: "#ABBB65"},
        "gold": {1: "#E4D4A9", 5: "#C08E54", 10: "#998044", 25: "#C9AE65"},
    }
    body = colors[style][value]
    bright = "#EAE5D8" if style == "neon" else "#F1E3BF"
    edge = DARK if style == "neon" else "#503C29"
    c = Canvas((256, 256))
    c.ellipse((11, 11, 245, 245), edge)
    c.ellipse((15, 15, 241, 241), body)
    c.ellipse((19, 19, 237, 237), outline=bright, width=1)
    c.ellipse((24, 24, 232, 232), outline=edge, width=2)
    groups = {1: 1, 5: 2, 10: 3, 25: 4}[value]
    for i in range(8):
        angle = i * math.tau / 8
        if style == "neon":
            for j in range(groups):
                a = angle + (j - (groups-1)/2) * .075
                points = [(128 + r*math.cos(t), 128 + r*math.sin(t))
                          for r, t in ((83, a-.021), (107, a-.021),
                                       (107, a+.021), (83, a+.021))]
                c.polygon(points, edge)
        else:
            # Gold tokens use engraved laurel leaves rather than the neon bars.
            for j in range(groups):
                a = angle + (j - (groups-1)/2) * .09
                x, y = 128 + 97*math.cos(a), 128 + 97*math.sin(a)
                tangent = (-math.sin(a), math.cos(a))
                radial = (math.cos(a), math.sin(a))
                c.polygon([(x+radial[0]*8, y+radial[1]*8),
                           (x+tangent[0]*2.5, y+tangent[1]*2.5),
                           (x-radial[0]*8, y-radial[1]*8),
                           (x-tangent[0]*2.5, y-tangent[1]*2.5)], edge)
    c.ellipse((47, 47, 209, 209), edge)
    c.ellipse((51, 51, 205, 205), outline=bright, width=1)
    c.ellipse((56, 56, 200, 200), body)
    for i in range(16):
        a = i * math.tau / 16
        x, y = 128 + 66*math.cos(a), 128 + 66*math.sin(a)
        if style == "gold":
            diamond(c, x, y, 1.6, edge)
        else:
            c.ellipse((x-1, y-1, x+1, y+1), bright)
    c.ellipse((70, 70, 186, 186), edge)
    c.ellipse((73, 73, 183, 183), IVORY)
    c.ellipse((78, 78, 178, 178), outline="#CABFAD", width=1)
    return c.finish()


def avatar(kind):
    c = Canvas((256, 256))
    ring = GOLD if kind == "spade" else "#A9A4B5"
    base = "#20272A" if kind == "spade" else "#3C3045"
    c.ellipse((11, 11, 245, 245), DARK)
    c.ellipse((16, 16, 240, 240), ring)
    c.ellipse((21, 21, 235, 235), base)
    c.ellipse((28, 28, 228, 228), outline=ring, width=1)
    if kind == "spade":
        for i in range(12):
            a = i * math.tau / 12
            diamond(c, 128+91*math.cos(a), 128+91*math.sin(a), 2.5, GOLD)
        suit(c, "spade", 128, 124, 117, IVORY)
        suit(c, "spade", 128, 124, 93, GOLD)
        suit(c, "spade", 128, 124, 67, base)
        c.line([(78, 188), (100, 198), (128, 203), (156, 198), (178, 188)], GOLD, 2)
        diamond(c, 128, 52, 6, GOLD)
    else:
        # Keep the achievement's White Flag meaning, despite its avatar_joker id.
        c.line([(77, 66), (77, 191)], GOLD, 5)
        c.ellipse((71, 56, 83, 68), GOLD)
        c.polygon([(80, 71), (110, 60), (141, 66), (172, 58), (192, 65),
                   (185, 112), (170, 107), (142, 119), (112, 113), (80, 122)], IVORY)
        c.polygon([(112, 61), (128, 64), (126, 117), (113, 113)], "#CFBFAF")
        c.polygon([(169, 60), (178, 61), (173, 109), (161, 112)], "#E1D5C5")
        c.line([(65, 191), (89, 191)], GOLD, 2)
        c.line([(97, 177), (153, 177)], "#796B83", 1)
        diamond(c, 128, 195, 4, ring)
    return c.finish()


def label(draw, position, text, size=21, color=IVORY):
    draw.text(position, text, font=font(size), fill=color)


def presentation(images, out):
    sheet = Image.new("RGB", (1650, 640), DARK)
    d = ImageDraw.Draw(sheet)
    label(d, (42, 24), "UNLOCKABLE DECKS / PROCEDURAL COLLECTION", 31)
    for i, (style, title) in enumerate((("crimson", "CRIMSON LATTICE"),
                                       ("royal", "ROYAL FLUSH"),
                                       ("poker_head", "POKER HEAD'S DECK"))):
        x = 42 + i*550
        img = images[f"card_back_{style}"].resize((250, 375), Image.Resampling.LANCZOS)
        sheet.paste(img, (x, 111), img)
        front = images.get("card_front_poker_head") if style == "poker_head" else None
        if front is not None:
            img = front.resize((145, 218), Image.Resampling.LANCZOS)
            sheet.paste(img, (x+285, 180), img)
            label(d, (x+279, 427), "MATCHING FACE", 15, "#ADAAAE")
        else:
            label(d, (x+280, 265), "SHARED", 17, "#ADAAAE")
            label(d, (x+280, 296), "CARD FACE", 17, "#ADAAAE")
        label(d, (x, 517), title, 22)
        label(d, (x, 557), "512 x 768 / Transparent PNG", 17, "#ADAAAE")
    sheet.save(out / "decks.png", optimize=True)
    sheet = Image.new("RGB", (1650, 1050), DARK)
    d = ImageDraw.Draw(sheet)
    label(d, (42, 25), "CHIPS & AVATARS / PROCEDURAL COLLECTION", 31)
    for row, (style, title) in enumerate((("neon", "NEON CHIPS"), ("gold", "GOLD CHIPS"))):
        y = 112+row*285
        label(d, (42, y), title, 23)
        for i, value in enumerate((1, 5, 10, 25)):
            x = 230+i*310
            img = images[f"chips_{style}_{value}"].resize((190, 190), Image.Resampling.LANCZOS)
            sheet.paste(img, (x, y), img)
            d.text((x+95, y+95), str(value), anchor="mm", font=font(31), fill=DARK)
            label(d, (x+45, y+215), f"CHIP {value}", 17, "#ADAAAE")
    d.line((42, 681, 1608, 681), fill="#4A3A43", width=1)
    for i, (asset, title) in enumerate((("avatar_spade", "ACE OF SPADES"), ("avatar_joker", "WHITE FLAG"))):
        x = 90+i*800
        img = images[asset].resize((240, 240), Image.Resampling.LANCZOS)
        sheet.paste(img, (x, 730), img)
        label(d, (x+272, 789), title, 25)
        label(d, (x+272, 834), "256 x 256 / Transparent", 17, "#ADAAAE")
        tiny = images[asset].resize((48, 48), Image.Resampling.LANCZOS)
        sheet.paste(tiny, (x+280, 888), tiny)
        label(d, (x+350, 901), "48 px preview", 16, "#ADAAAE")
    sheet.save(out / "chips_avatars.png", optimize=True)


def runtime_previews(out):
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["CHAOS_DB"] = ":memory:"
    os.environ["CHAOS_USE_LLM"] = "0"
    from preview_assets import in_play_controller, render_scene
    import pygame
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    from chaos_blackjack.cosmetics import get_cosmetic
    from chaos_blackjack import meta
    from chaos_blackjack.meta.fake import install_fake
    import chaos_blackjack.gui.scenes  # noqa: F401

    service = install_fake(demo=False)
    app = App(GuiSettings(asset_dirs=(out / "assets", ROOT / "assets")))
    previews = out / "previews"
    previews.mkdir()
    themes = (("midnight", "card_back_royal", "chips_neon"),
              ("chaos", "card_back_crimson", "chips_neon"),
              ("poker_head", "deck_poker_head", "chips_gold"))
    for theme, deck_id, chips_id in themes:
        aliases = {}
        for cid in ("table_"+theme, deck_id, chips_id):
            aliases.update(get_cosmetic(cid).assets)
        app.assets.set_aliases(aliases)
        shot = render_scene(app, "table", controller=in_play_controller())
        pygame.image.save(shot, str(previews / f"table_{theme}.png"))
    # Exercise the actual wardrobe rows and avatar in an isolated fake profile.
    player = meta.create_player(1, "Art Preview")
    from chaos_blackjack.cosmetics import cosmetics
    for cosmetic in cosmetics():
        if not cosmetic.default:
            service.grant_cosmetic(player.id, cosmetic.id)
    for cid in ("deck_poker_head", "table_poker_head", "chips_gold", "avatar_spade"):
        meta.equip(player.id, cid)
    for slot in ("deck", "table", "chips", "avatar"):
        shot = render_scene(app, "profile", player_id=player.id, tab="wardrobe", slot=slot)
        pygame.image.save(shot, str(previews / f"wardrobe_{slot}.png"))
    app.audio.close()
    service._conn.close()
    meta.use_service(None)
    pygame.quit()
    sheet = Image.new("RGB", (1920, 1010), DARK)
    draw = ImageDraw.Draw(sheet)
    label(draw, (36, 22), "TABLE SKINS / CURRENT GAME LAYOUT", 31)
    for i, (style, title) in enumerate((("midnight", "MIDNIGHT FELT"),
                                       ("chaos", "CHAOS VELVET"),
                                       ("poker_head", "POKER HEAD'S TABLE"))):
        x = 18+i*640
        label(draw, (x+12, 87), title, 23)
        shot = Image.open(previews / f"table_{style}.png").convert("RGB")
        sheet.paste(shot.resize((620, 349), Image.Resampling.LANCZOS), (x, 133))
        crop = shot.crop((266, 52, 1014, 704)).resize((600, 523), Image.Resampling.LANCZOS)
        sheet.paste(crop, (x+10, 486))
    sheet.save(out / "tables.png", optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "cosmetic_redraw_v1")
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        ap.error(f"Output already exists; choose a new folder: {out}")
    (out / "assets").mkdir(parents=True)
    images = {f"card_back_{s}": deck(s) for s in ("crimson", "royal", "poker_head")}
    images["card_front_poker_head"] = deck("poker_head", face=True)
    images.update({f"table_{s}": table(s) for s in ("midnight", "chaos", "poker_head")})
    images.update({f"chips_{s}_{v}": chip(s, v) for s in ("neon", "gold") for v in (1, 5, 10, 25)})
    images.update({"avatar_spade": avatar("spade"), "avatar_joker": avatar("flag")})
    rows = []
    for asset_id, image in images.items():
        path = out / "assets" / f"{asset_id}.png"
        write_png(image, path)
        images[asset_id] = Image.open(path).convert("RGB" if asset_id.startswith("table_") else "RGBA")
        rows.append({"id": asset_id, "size": list(image.size), "bytes": path.stat().st_size})
    report = {"source": "scripts/generate_cosmetic_assets.py", "assets": rows,
              "total_bytes": sum(row["bytes"] for row in rows)}
    (out / "manifest.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    presentation(images, out)
    runtime_previews(out)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
