"""Draw Casino Green and four flat, half-body Chaos AI portraits with Pillow.

    python scripts/generate_house_assets.py --out output/house_art_v1

All files are original procedural art. Choose a new output folder for each
revision; existing art, profiles and game rules are never modified.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

from generate_casino_assets import Canvas, diamond, font, suit, write_png
from generate_cosmetic_assets import clipped

ROOT = Path(__file__).resolve().parents[1]
INK = "#211A29"
IVORY = "#EEE5D5"
GOLD = "#C9B07B"




def casino_green():
    c = Canvas((1280, 720), "#141A18")
    # Frame the visible centre column; bottom decoration sits below controls.
    c.rounded((266, 52, 1014, 704), 32, "#0C1210")
    c.rounded((272, 58, 1008, 698), 28, "#303933")
    c.rounded((274, 60, 1006, 696), 26, outline="#697260", width=1)
    c.rounded((280, 66, 1000, 690), 21, "#466252")
    c.rounded((282, 68, 998, 688), 19, outline="#B2A37F", width=1)
    c.rounded((293, 79, 987, 677), 12, "#14271E")
    c.rounded((297, 83, 983, 673), 9, "#263F34")
    field = Canvas((1280, 720))
    boundary = [(x, 314+61*(1-((x-640)/343)**2)) for x in range(297, 984, 2)]
    field.polygon(boundary+[(983, 673), (297, 673)], "#2F4C3D")
    field.line(boundary, "#9C9270", 1.2)
    field.line([(x, y+5) for x, y in boundary], "#46614B", .8)
    clipped(c, field, (297, 83, 983, 673), 9)
    c.rounded((297, 83, 983, 673), 9, outline="#7F8865", width=1)
    # Quiet stitching, with a larger diamond every fourth stitch.
    for x in (287, 993):
        for i, y in enumerate(range(112, 663, 18)):
            if i % 4 == 0:
                diamond(c, x, y, 3.8, "#C0B28D")
            else:
                c.line([(x, y-2), (x, y+2)], "#A3B09A", .8)
    for x, direction in ((311, 1), (969, -1)):
        c.line([(x, 109), (x, 97), (x+direction*20, 97)], "#A7A17A", 1)
        diamond(c, x+direction*25, 97, 3.6, "#C0B28D")
    c.line([(310, 685), (574, 685)], "#B2A37F", .8)
    c.line([(706, 685), (970, 685)], "#B2A37F", .8)
    for kind, x in zip(("spade", "heart", "club", "diamond"), (595, 625, 655, 685)):
        suit(c, kind, x, 685, 8, "#C0B28D")
    return c.image.resize((1920, 1080), Image.Resampling.LANCZOS).convert("RGB")


def portrait(mood):
    """A starter dealer assembled from flat, readable geometric pieces."""
    c = Canvas((512, 512))
    coat = "#37463E"
    sleeve = "#4C5A50"
    face = "#88758F"
    # Upper body: shoulder trapezoid, waistcoat and folded sleeves.
    c.rounded((239, 261, 273, 311), 8, "#74637D")
    c.polygon([(181, 298), (331, 298), (384, 333), (405, 470),
               (107, 470), (128, 333)], coat)
    c.polygon([(207, 300), (305, 300), (333, 470), (179, 470)], "#526759")
    c.polygon([(224, 294), (288, 294), (277, 352),
               (256, 369), (235, 352)], IVORY)
    # Simple lapels and a small bow tie give the initial dealer a uniform.
    c.polygon([(188, 303), (224, 294), (244, 350), (205, 329)], "#27382F")
    c.polygon([(324, 303), (288, 294), (268, 350), (307, 329)], "#27382F")
    c.polygon([(239, 313), (255, 319), (239, 327)], INK)
    c.polygon([(273, 313), (257, 319), (273, 327)], INK)
    c.rounded((252, 315, 260, 324), 2, INK)
    c.ellipse((253, 382, 259, 388), GOLD)
    # Two broad sleeves and white mittens read as calmly folded hands.
    c.polygon([(137, 355), (166, 347), (249, 416),
               (226, 447), (145, 407)], sleeve)
    c.polygon([(375, 355), (346, 347), (263, 416),
               (286, 447), (367, 407)], sleeve)
    c.rounded((211, 414, 255, 446), 12, IVORY)
    c.rounded((257, 414, 301, 446), 12, "#E1DACB")
    # Two triangles and a rounded head retain the purple two-horn identity.
    c.polygon([(180, 135), (219, 109), (171, 56)], "#6E6078")
    c.polygon([(332, 135), (293, 109), (341, 56)], "#6E6078")
    c.rounded((164, 103, 348, 280), 73, face)
    # Expressions use only short strokes, circles and elliptical arcs.
    if mood == "laugh":
        for x in (201, 279):
            c.draw.arc(c.box((x, 179, x+32, 210)), 205, 335,
                       fill=GOLD, width=5*c.scale)
        c.ellipse((236, 218, 276, 252), INK)
        c.rounded((244, 241, 268, 248), 3, "#B98AA2")
    else:
        if mood == "smug":
            c.line([(203, 195), (227, 195)], GOLD, 5)
            c.line([(283, 190), (307, 187)], GOLD, 5)
            c.line([(283, 173), (306, 166)], INK, 4)
        else:
            c.rounded((209, 188, 225, 201), 5, GOLD)
            c.rounded((287, 188, 303, 201), 5, GOLD)
        if mood == "angry":
            c.line([(201, 172), (230, 181)], INK, 4)
            c.line([(282, 181), (311, 172)], INK, 4)
            c.draw.arc(c.box((235, 227, 278, 252)), 200, 340,
                       fill=INK, width=4*c.scale)
        elif mood == "smug":
            c.draw.arc(c.box((233, 211, 281, 241)), 20, 160,
                       fill=INK, width=4*c.scale)
        else:
            c.line([(237, 233), (275, 233)], INK, 4)
    return c.finish()


def presentation(images, out):
    moods = ("calm", "smug", "laugh", "angry")
    sheet = Image.new("RGB", (1800, 630), "#191B1D")
    draw = ImageDraw.Draw(sheet)
    draw.text((38, 24), "CHAOS AI / STARTER DEALER", font=font(34), fill=IVORY)
    draw.text((40, 76), "ORIGINAL PROCEDURAL PORTRAITS  /  512 x 512 TRANSPARENT PNG", font=font(16), fill="#A8A3AB")
    for i, mood in enumerate(moods):
        x = 24+i*450
        img = images["chaos_"+mood].resize((402, 402), Image.Resampling.LANCZOS)
        sheet.paste(img, (x, 115), img)
        draw.text((x+22, 553), mood.upper(), font=font(26), fill=IVORY)
    sheet.save(out / "portraits.png", optimize=True)
    # Actual 200-pixel portrait on the table's side-panel colour.
    sheet = Image.new("RGB", (920, 260), "#1E2523")
    draw = ImageDraw.Draw(sheet)
    for i, mood in enumerate(moods):
        img = images["chaos_"+mood].resize((200, 200), Image.Resampling.LANCZOS)
        sheet.paste(img, (15+i*230, 15), img)
        draw.text((28+i*230, 230), mood.upper(), font=font(16), fill=IVORY)
    sheet.save(out / "portraits_200px.png", optimize=True)


def runtime_previews(out):
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["CHAOS_DB"] = ":memory:"
    os.environ["CHAOS_USE_LLM"] = "0"
    import pygame
    from preview_assets import render_scene, matte_sheet
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.view import TablePhase
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    import chaos_blackjack.gui.scenes  # noqa: F401
    app = App(GuiSettings(asset_dirs=(out / "assets", ROOT / "assets")))
    app.assets.set_aliases({})
    previews = out / "previews"
    previews.mkdir()
    for mood in ("calm", "smug", "laugh", "angry"):
        for seed in range(1, 100):
            controller = GameController(RunConfig(seed=seed, enable_chaos=True, use_llm=False, host="house"))
            controller.place_bet(10)
            if controller.phase == TablePhase.CHAOS:
                controller.resolve_chaos()
            if controller.phase == TablePhase.PLAYER_TURN:
                break
        else:
            raise RuntimeError("No seeded player turn for the house preview")
        def set_mood(scene):
            scene.chaos_panel.mood = mood
            scene.chaos_panel.speech = {"calm": "Place your bet. I'm watching.",
                                       "smug": "New rules. My table.",
                                       "laugh": "Too greedy!", "angry": "Enjoy it while it lasts."}[mood]
        shot = render_scene(app, "table", controller=controller, setup=set_mood)
        pygame.image.save(shot, str(previews / f"table_{mood}.png"))
        pygame.image.save(matte_sheet(app, "chaos_"+mood), str(previews / f"matte_chaos_{mood}.png"))
    app.audio.close()
    pygame.quit()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        ap.error(f"Output already exists; choose a new folder: {out}")
    (out / "assets").mkdir(parents=True)
    images = {"table_background": casino_green(),
              **{"chaos_"+mood: portrait(mood) for mood in ("calm", "smug", "laugh", "angry")}}
    rows = []
    for asset_id, image in images.items():
        path = out / "assets" / f"{asset_id}.png"
        write_png(image, path)
        images[asset_id] = Image.open(path).convert("RGB" if asset_id == "table_background" else "RGBA")
        rows.append({"id": asset_id, "size": list(image.size), "bytes": path.stat().st_size})
    (out / "manifest.json").write_text(json.dumps({"source": "scripts/generate_house_assets.py",
        "assets": rows, "total_bytes": sum(row["bytes"] for row in rows)}, indent=2)+"\n", encoding="utf-8")
    presentation(images, out)
    runtime_previews(out)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
