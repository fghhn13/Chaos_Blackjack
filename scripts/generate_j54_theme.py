"""Create an independent J-54 theme preview, based on the red/black art study.

    python scripts/generate_j54_theme.py --out output/j54_theme_v1

Only a new output folder is written. Proposed ids and aliases are registered
in memory for previews; the game catalog, assets and player saves stay intact.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw

from generate_casino_assets import Canvas, diamond, font, write_png
from generate_cosmetic_assets import clipped

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BLACK = "#171719"
CHARCOAL = "#2C292D"
RED = "#B43C46"
RUBY = "#77232F"
IVORY = "#EDE4D2"
STEEL = "#8E8985"
ALIASES = {"card_back": "card_back_j54", "card_front_blank": "card_front_j54",
           "table_background": "table_j54", "avatar": "avatar_j54",
           **{f"chip_{v}": f"chips_j54_{v}" for v in (1, 5, 10, 25)}}
ASSET_BASES = {asset: base for base, asset in ALIASES.items()} | {
    "card_back_j54_calculator": "card_back", "avatar_j54_computer": "avatar"}


def square(c, x, y, size, color):
    c.draw.rectangle(c.box((x-size/2, y-size/2, x+size/2, y+size/2)), fill=color)




def pixel_stamp(draw,rows,x,y,color):
    """Place a binary pattern on a logical pixel grid."""
    for row,data in enumerate(rows):
        for col,bit in enumerate(data):
            if bit=="1":
                draw.point((x+col,y+row),fill=color)


def ghost():
    """A coarse, three-shape grin; no smooth curves or secondary details."""
    image=Image.new("RGBA",(32,48))
    draw=ImageDraw.Draw(image)
    eye=("110000000","011110000","001111110","000011111")
    pixel_stamp(draw,eye,5,17,RED)
    pixel_stamp(draw,tuple(row[::-1] for row in eye),18,16,RED)
    smile=("100000000000000000000001",
           "110000000000000000000011",
           "011000000000000000000110",
           "011110000000000000011110",
           "001111110000000011111100",
           "000111111111111111111000",
           "000011111111111111110000",
           "000001111111111111100000",
           "000000011111111110000000",
           "000000000111111000000000")
    pixel_stamp(draw,smile,4,24,RED)
    return image


def calculator():
    """An LCD and chunky key pattern, drawn directly on a coarse pixel grid."""
    image=Image.new("RGBA",(32,48))
    draw=ImageDraw.Draw(image)
    draw.rectangle((4,7,27,15),fill=BLACK)
    for point in ((4,7),(27,7),(4,15),(27,15)):
        draw.point(point,fill=RED)
    for x,width in ((6,3),(10,3),(14,6)):
        draw.rectangle((x,12,x+width-1,12),fill=IVORY)
    draw.point((25,13),fill=RED)
    operators=(("010","111","010"),("000","111","000"),
               ("101","010","101"),("111","000","111"))
    for row in range(4):
        for col in range(4):
            x,y=4+col*6,19+row*6
            color=IVORY if col<3 and (row+col)%3==0 else BLACK
            draw.rectangle((x,y,x+4,y+4),fill=color)
            if col==3:
                pixel_stamp(draw,operators[row],x+1,y+1,IVORY)
    return image


def card(style):
    c=Canvas((512,768))
    if style == "front":
        c.rounded((0,0,511,767),42,IVORY)
        c.rounded((6,6,505,761),36,outline="#B8AEA1",width=1)
        # Runtime ranks and suits have an uninterrupted ivory field.
        c.rounded((23,23,488,744),23,outline="#D0B2AA",width=1)
        for x in (221,239,257,275,293):
            square(c,x,22,3,RED if x==257 else "#B19C92")
            square(c,511-x,745,3,RED if x==257 else "#B19C92")
        return c.finish()
    c.rounded((0,0,511,767),42,RED if style=="calculator" else BLACK)
    c.rounded((13,13,498,754),29,outline=BLACK if style=="calculator" else RUBY,
              width=3 if style=="calculator" else 2)
    if style == "ghost":
        pixels=ghost()
    elif style == "calculator":
        pixels=calculator()
    else:
        raise ValueError(style)
    image=c.finish()
    # Scale the motif after the border is antialiased, keeping all grid edges crisp.
    image.alpha_composite(pixels.resize(image.size,Image.Resampling.NEAREST))
    return image


def table():
    c=Canvas((1280,720),"#131316")
    c.rounded((266,52,1014,704),32,"#0D0B0F")
    c.rounded((272,58,1008,698),28,CHARCOAL)
    c.rounded((274,60,1006,696),26,outline="#665258",width=1)
    c.rounded((280,66,1000,690),21,RED)
    c.rounded((282,68,998,688),19,outline="#D29996",width=1)
    c.rounded((293,79,987,677),12,BLACK)
    c.rounded((297,83,983,673),9,"#221D22")
    field=Canvas((1280,720))
    border=[(297,312),(357,312),(357,328),(417,328),(417,344),(477,344),
            (477,360),(537,360),(537,376),(743,376),(743,360),(803,360),
            (803,344),(863,344),(863,328),(923,328),(923,312),(983,312)]
    field.polygon(border+[(983,673),(297,673)],"#45202B")
    # Large interlocking diamonds give the felt a circus pattern. Contrast is
    # restrained in the hand lanes, stronger between them and along the sides.
    for row,y in enumerate(range(70,720,64)):
        for x in range(280,1030,64):
            xx=x+(32 if row%2 else 0)
            color="#58313C" if y>376 else "#38282F"
            field.polygon([(xx,y-32),(xx+32,y),(xx,y+32),(xx-32,y)],color)
            field.line([(xx,y-27),(xx+27,y),(xx,y+27),(xx-27,y),(xx,y-27)],
                       "#65404A" if y>376 else "#473239",.6)
            square(field,xx,y,2.2,"#865560" if y>376 else "#66444E")
    # A narrow checkerboard and pin-diamond band stays visible beside the cards.
    for x in (301,965):
        for i,y in enumerate(range(145,620,20)):
            field.draw.rectangle(field.box((x,y,x+16,y+20)),
                                 fill="#6D3440" if i%2 else "#211C22")
            diamond(field,x+8,y+10,4,"#A97179" if i%2 else "#70404B")
    field.line(border,"#9F5865",1.4)
    field.line([(x,y+5) for x,y in border],"#682C3B",.8)
    # Short paired signal traces occupy the margins outside the widest hand.
    for x,direction in ((306,1),(974,-1)):
        field.line([(x,115),(x+direction*31,115),(x+direction*31,127),
                    (x+direction*50,127)],"#63424A",1)
        square(field,x+direction*50,127,4,"#9D6971")
    clipped(c,field,(297,83,983,673),9)
    c.rounded((297,83,983,673),9,outline="#92505F",width=1)
    for x,direction in ((287,1),(993,-1)):
        for index,y in enumerate(range(111,657,32)):
            # Bracket-and-node trim is visible between the panels and hands.
            c.line([(x-3*direction,y-5),(x+3*direction,y-5),
                    (x+3*direction,y+5),(x-3*direction,y+5)],"#DEB7AA",.9)
            square(c,x,y,2.6,BLACK)
            if index%2==0:
                c.line([(x,y+9),(x,y+20)],"#D28E8D",.8)
    for x in (311,969):
        square(c,x,97,4,IVORY)
    c.line([(310,685),(574,685)],"#D29996",.8)
    c.line([(706,685),(970,685)],"#D29996",.8)
    for x in (604,622,640,658,676):
        square(c,x,685,4,IVORY if x in (604,640,676) else BLACK)
    return c.image.resize((1920,1080),Image.Resampling.LANCZOS).convert("RGB")


def pixel_badge(fill):
    """An opaque stepped disc on a transparent 32 x 32 grid."""
    image=Image.new("RGBA",(32,32))
    draw=ImageDraw.Draw(image)
    draw.ellipse((1,1,30,30),fill=BLACK)
    draw.ellipse((2,2,29,29),fill=fill)
    return image,draw


def chip(value):
    """Chunky casino edge marks around a clean centre for runtime values."""
    body={1:IVORY,5:RED,10:BLACK,25:RUBY}[value]
    mark=BLACK if value==1 else IVORY
    groups={1:1,5:2,10:3,25:4}[value]
    image,draw=pixel_badge(body)
    draw.ellipse((5,5,26,26),outline=RED if value==10 else BLACK,width=1)
    for i in range(8):
        angle=-math.pi/2+i*math.tau/8
        for j in range(groups):
            tangent=(j-(groups-1)/2)*2
            for radius in (12,11):
                x=round(15.5+radius*math.cos(angle)-tangent*math.sin(angle))
                y=round(15.5+radius*math.sin(angle)+tangent*math.cos(angle))
                draw.point((x,y),fill=mark)
    draw.ellipse((8,8,23,23),fill=BLACK)
    draw.ellipse((9,9,22,22),fill=IVORY)
    return image.resize((256,256),Image.Resampling.NEAREST)


def avatar(style="clown"):
    """J-54 badges drawn entirely as flat 32 x 32 pixel compositions."""
    image,draw=pixel_badge(RED)
    if style=="clown":
        draw.ellipse((3,3,28,28),fill=BLACK)
        draw.polygon([(8,14),(6,7),(4,8),(7,4),(13,6),(16,13)],fill=RED)
        draw.polygon([(6,7),(7,4),(9,9),(11,14)],fill=BLACK)
        draw.polygon([(16,13),(20,6),(25,5),(28,12),(25,11),(23,9),(22,14)],fill=RED)
        draw.polygon([(25,5),(28,12),(25,11),(23,9)],fill=BLACK)
        draw.rectangle((3,8,5,10),fill=IVORY)
        draw.rectangle((27,12,29,14),fill=IVORY)
        draw.rectangle((8,13,25,24),fill=IVORY)
        for p in ((8,13),(25,13),(8,24),(25,24)):
            draw.point(p,fill=BLACK)
        draw.rectangle((9,14,24,23),fill=RUBY)
        draw.rectangle((10,15,23,22),fill=BLACK)
        for x in (11,19):
            pixel_stamp(draw,("11","11"),x,16,IVORY)
        pixel_stamp(draw,("10000000001","01100000110","00011111000"),11,20,IVORY)
        draw.rectangle((8,24,25,25),fill=IVORY)
        for x in (9,13,18,22):
            draw.rectangle((x,26,x+1,27),fill=IVORY)
        draw.rectangle((15,26,16,28),fill=RED)
    elif style=="computer":
        draw.rectangle((6,8,25,21),fill=BLACK)
        for p in ((6,8),(25,8),(6,21),(25,21)):
            draw.point(p,fill=RED)
        draw.rectangle((7,9,24,20),fill=IVORY)
        draw.rectangle((8,10,23,19),fill=BLACK)
        power=("0001000","0101010","1001001","1000001","1000001","0100010","0011100")
        pixel_stamp(draw,power,12,11,IVORY)
        draw.rectangle((15,11,15,13),fill=RED)
        draw.rectangle((14,22,17,24),fill=BLACK)
        draw.rectangle((11,25,20,25),fill=BLACK)
        draw.rectangle((6,26,25,28),fill=BLACK)
        for x in range(7,24,3):
            draw.rectangle((x,27,x+1,27),fill=IVORY)
    else:
        raise ValueError(style)
    return image.resize((256,256),Image.Resampling.NEAREST)


def overview(images,out):
    sheet=Image.new("RGB",(1800,1480),BLACK)
    d=ImageDraw.Draw(sheet)
    d.text((48,28),"J-54 / PIXEL & SHADOW",font=font(46,True),fill=IVORY)
    d.text((50,92),"RED / BLACK / IVORY    -    INDEPENDENT THEME PREVIEW",font=font(18),fill="#AE9B9D")
    for i,color in enumerate((BLACK,RUBY,RED,IVORY,STEEL)):
        d.rounded_rectangle((1500+i*49,45,1536+i*49,81),radius=4,fill=color)
    d.line((48,130,1752,130),fill="#493039")
    for i,(asset,label) in enumerate((("card_back_j54","01 / PIXEL GRIN"),
                                     ("card_back_j54_calculator","02 / RED CALCULATOR"),
                                     ("card_front_j54","SHARED FRONT"))):
        x=48+i*290
        img=images[asset].resize((230,345),Image.Resampling.LANCZOS)
        sheet.paste(img,(x,167),img)
        d.text((x,535),label,font=font(21),fill=IVORY)
    d.text((1020,167),"03 / TWO AVATARS",font=font(23),fill=IVORY)
    for x,asset,label in ((1020,"avatar_j54","PIXEL CLOWN"),
                         (1400,"avatar_j54_computer","COMPUTER")):
        img=images[asset].resize((236,236),Image.Resampling.NEAREST)
        sheet.paste(img,(x,226),img)
        d.text((x+118,495),label,anchor="mm",font=font(20),fill=IVORY)
    d.line((48,593,1752,593),fill="#493039")
    d.text((48,623),"04 / ARGYLE & SIGNAL TABLE",font=font(23),fill=IVORY)
    img=images["table_j54"].resize((1110,624),Image.Resampling.LANCZOS)
    sheet.paste(img,(48,675))
    d.text((48,1323),"1920 x 1080 / Patterned felt, checker trim and circuit details",font=font(18),fill="#AE9B9D")
    d.text((1220,623),"05 / MATCHING CHIPS",font=font(23),fill=IVORY)
    for i,value in enumerate((1,5,10,25)):
        x,y=1220+(i%2)*275,716+(i//2)*290
        img=images[f"chips_j54_{value}"].resize((214,214),Image.Resampling.NEAREST)
        sheet.paste(img,(x,y),img)
        d.text((x+107,y+107),str(value),anchor="mm",font=font(34),fill=BLACK)
        d.text((x+107,y+238),f"CHIP {value}",anchor="mm",font=font(17),fill="#AE9B9D")
    d.line((48,1380,1752,1380),fill="#493039")
    d.text((48,1410),"Two card backs / Two avatars / One table / Shared front / Four chips",font=font(20),fill=IVORY)
    d.text((48,1441),"PNG assets contain no chip values. This preview does not install or unlock cosmetics.",font=font(16),fill="#AE9B9D")
    sheet.save(out/"overview.png",optimize=True)


def size_preview(images,out):
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT","1")
    from chaos_blackjack.gui.components.cards import CARD_SIZE
    sheet=Image.new("RGB",(1200,710),BLACK)
    d=ImageDraw.Draw(sheet)
    d.text((30,24),"ACTUAL DISPLAY SIZES",font=font(28,True),fill=IVORY)
    d.text((30,82),f"CARD BACKS / {CARD_SIZE[0]} x {CARD_SIZE[1]}",font=font(18),fill=IVORY)
    for x,asset,label in ((40,"card_back_j54","GRIN"),(190,"card_back_j54_calculator","CALCULATOR")):
        img=images[asset].resize(CARD_SIZE,Image.Resampling.LANCZOS)
        sheet.paste(img,(x,130),img)
        d.text((x+CARD_SIZE[0]/2,335),label,anchor="mm",font=font(15),fill=IVORY)
    for y,asset,label in ((88,"avatar_j54","CLOWN"),(380,"avatar_j54_computer","COMPUTER")):
        d.text((365,y),label,font=font(18),fill=IVORY)
        for x,size in ((370,256),(670,128),(850,64),(1000,48)):
            img=images[asset].resize((size,size),Image.Resampling.NEAREST)
            sheet.paste(img,(x,y+28),img)
            d.text((x+size/2,y+size+37),str(size),anchor="mt",font=font(16),fill="#AE9B9D")
    sheet.save(out/"display_sizes.png",optimize=True)
    cards=Image.new("RGB",(1180,610),"#252126")
    draw=ImageDraw.Draw(cards)
    draw.text((35,24),"J-54 / PIXEL CARD BACKS",font=font(32,True),fill=IVORY)
    draw.line((590,100,590,565),fill="#493039")
    for x,asset,label in ((45,"card_back_j54","PIXEL SHADOW GRIN"),
                         (625,"card_back_j54_calculator","RED PIXEL CALCULATOR")):
        for dx,y,size in ((0,110,(256,384)),(309,230,CARD_SIZE)):
            img=images[asset].resize(size,Image.Resampling.LANCZOS)
            cards.paste(img,(x+dx,y),img)
        draw.text((x,533),label,font=font(20),fill=IVORY)
        draw.text((x+309,438),f"{CARD_SIZE[0]} x {CARD_SIZE[1]}",font=font(17),fill=IVORY)
    cards.save(out/"card_backs_preview.png",optimize=True)


def cosmetic_preview(images,out):
    sheet=Image.new("RGB",(1200,770),"#252126")
    draw=ImageDraw.Draw(sheet)
    draw.text((35,24),"J-54 / PIXEL AVATARS & CHIPS",font=font(32,True),fill=IVORY)
    for x,asset,label in ((45,"avatar_j54","PIXEL CLOWN"),
                         (625,"avatar_j54_computer","PIXEL COMPUTER")):
        for dx,y,size in ((0,105,256),(309,170,64),(403,178,48)):
            img=images[asset].resize((size,size),Image.Resampling.NEAREST)
            sheet.paste(img,(x+dx,y),img)
            draw.text((x+dx+size/2,y+size+14),str(size),anchor="mt",font=font(16),fill=IVORY)
        draw.text((x,401),label,font=font(20),fill=IVORY)
    draw.line((35,450,1165,450),fill="#493039")
    draw.text((35,467),"FOUR CHIP COLOURS / VALUES ARE GAME OVERLAYS",font=font(20),fill=IVORY)
    for i,value in enumerate((1,5,10,25)):
        x=40+i*290
        for dx,y,size in ((0,512,160),(186,551,76)):
            img=images[f"chips_j54_{value}"].resize((size,size),Image.Resampling.NEAREST)
            sheet.paste(img,(x+dx,y),img)
            draw.text((x+dx+size/2,y+size/2),str(value),anchor="mm",
                      font=font(26 if size==160 else 20),fill=BLACK)
        draw.text((x+80,695),f"CHIP {value}",anchor="mm",font=font(17),fill=IVORY)
        draw.text((x+224,649),"76 x 76",anchor="mm",font=font(14),fill=IVORY)
    draw.text((35,736),"32 x 32 pixel grid / Transparent outer corners / Clear centres for runtime labels",font=font(16),fill="#AE9B9D")
    sheet.save(out/"avatars_chips_preview.png",optimize=True)


def inspect_and_preview(out):
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"]="1"
    os.environ["SDL_VIDEODRIVER"]="dummy"
    os.environ["SDL_AUDIODRIVER"]="dummy"
    os.environ["CHAOS_USE_LLM"]="0"
    os.environ["CHAOS_DB"]=":memory:"
    import pygame
    from chaos_blackjack.gui.assets.manifest import MANIFEST,AssetSpec
    from chaos_blackjack.gui.app import App
    from chaos_blackjack.gui.settings import GuiSettings
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.view import TablePhase
    from chaos_blackjack.modes import get_mode
    from preview_assets import render_scene,matte_sheet,zoom_cards,zoom_chips
    from validate_assets import check,subject_rect
    import chaos_blackjack.gui.scenes  # noqa: F401

    # Temporary specs validate proposals against the shipped base sizes and
    # alpha policies. They never modify the game's persisted manifest.
    pygame.init()
    rows=[]
    for asset,base in ASSET_BASES.items():
        spec=MANIFEST[base]
        MANIFEST[asset]=AssetSpec(asset,spec.category,spec.size,spec.placeholder)
        rows.append(check(asset,[out/"assets"/(asset+".png")],64))
    front=subject_rect(out/"assets"/"card_front_j54.png")
    for asset in ("card_back_j54","card_back_j54_calculator"):
        back=subject_rect(out/"assets"/(asset+".png"))
        if back is None or front is None or max(abs(a-b) for a,b in zip(back,front))>2:
            raise RuntimeError(f"Card front/back outlines disagree: {asset}")
    (out/"validation.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")
    if any(row["status"]!="OK" for row in rows):
        raise RuntimeError("A theme asset failed validation: "+str(rows))
    app=App(GuiSettings(asset_dirs=(out/"assets",ROOT/"assets")))
    app.assets.set_aliases(ALIASES)
    previews=out/"previews"
    previews.mkdir()
    mode=get_mode("j54")
    betting=GameController(mode.apply(RunConfig(seed=1,use_llm=False)))
    pygame.image.save(render_scene(app,"table",controller=betting),str(previews/"table_betting.png"))
    for seed in range(1,100):
        controller=GameController(mode.apply(RunConfig(seed=seed,use_llm=False)))
        controller.place_bet(10)
        if controller.phase==TablePhase.CHAOS:
            controller.resolve_chaos()
        if controller.phase==TablePhase.PLAYER_TURN:
            break
    else:
        raise RuntimeError("No seeded player-turn preview")
    # Let the rule's brief glitch and the chip-drop animation finish before
    # capturing the steady layout. The run still waits for the player.
    for variant,back in (("ghost","card_back_j54"),("calculator","card_back_j54_calculator")):
        app.assets.set_aliases(ALIASES | {"card_back":back})
        controller=GameController(mode.apply(RunConfig(seed=seed,use_llm=False)))
        controller.place_bet(10)
        if controller.phase==TablePhase.CHAOS:
            controller.resolve_chaos()
        shot=render_scene(app,"table",controller=controller,
                          setup=lambda scene:(scene._pump_notices(),scene._sync_widgets(),scene.fx.update(2.0)))
        pygame.image.save(shot,str(previews/f"table_play_{variant}.png"))
        pygame.image.save(zoom_cards(app),str(previews/f"zoom_cards_{variant}.png"))
    app.assets.set_aliases(ALIASES)
    for asset in ASSET_BASES:
        pygame.image.save(matte_sheet(app,asset),str(previews/("matte_"+asset+".png")))
    pygame.image.save(zoom_cards(app),str(previews/"zoom_cards.png"))
    pygame.image.save(zoom_chips(app),str(previews/"zoom_chips.png"))
    checks=Image.new("RGB",(1500,1900),BLACK)
    draw=ImageDraw.Draw(checks)
    for index,asset in enumerate(ASSET_BASES):
        x,y=(index%2)*750,(index//2)*380
        draw.text((x+20,y+15),asset,font=font(19),fill=IVORY)
        with Image.open(previews/("matte_"+asset+".png")) as matte:
            matte.thumbnail((710,315),Image.Resampling.LANCZOS)
            checks.paste(matte,(x+20,y+50))
    checks.save(out/"quality_checks.png",optimize=True)
    app.audio.close()
    pygame.quit()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    out=args.out.resolve()
    if out.exists():
        ap.error(f"Output already exists; choose a new folder: {out}")
    (out/"assets").mkdir(parents=True)
    images={"card_back_j54":card("ghost"),"card_back_j54_calculator":card("calculator"),
            "card_front_j54":card("front"),
            "table_j54":table(),"avatar_j54":avatar("clown"),
            "avatar_j54_computer":avatar("computer"),
            **{f"chips_j54_{v}":chip(v) for v in (1,5,10,25)}}
    rows=[]
    for asset,image in images.items():
        path=out/"assets"/(asset+".png")
        write_png(image,path)
        images[asset]=Image.open(path).convert("RGB" if asset=="table_j54" else "RGBA")
        rows.append({"id":asset,"size":list(image.size),"bytes":path.stat().st_size})
    (out/"manifest.json").write_text(json.dumps({"source":"scripts/generate_j54_theme.py",
        "status":"independent preview; not installed", "aliases":ALIASES,
        "asset_bases":ASSET_BASES, "variants":{"card_backs":["card_back_j54","card_back_j54_calculator"],
        "avatars":["avatar_j54","avatar_j54_computer"]},"assets":rows,
        "total_bytes":sum(row["bytes"] for row in rows)},indent=2)+"\n",encoding="utf-8")
    overview(images,out)
    size_preview(images,out)
    cosmetic_preview(images,out)
    inspect_and_preview(out)
    (out/"README.md").write_text("""# J-54: Pixel and Shadow — independent preview

This procedural red/black/ivory theme is not installed in the game.

- `assets/card_back_j54.png`: black card with a red pixel shadow grin, 512 x 768.
- `assets/card_back_j54_calculator.png`: red card with a black pixel screen/key pattern, 512 x 768.
- `assets/card_front_j54.png`: shared blank front, 512 x 768.
- `assets/table_j54.png`: argyle felt, checker trim and signal traces, 1920 x 1080.
- `assets/avatar_j54.png`: pixel clown avatar, 256 x 256.
- `assets/avatar_j54_computer.png`: red pixel computer-symbol avatar, 256 x 256.
- Four `assets/chips_j54_*.png` pixel chips, 256 x 256; game values remain overlays.

The card-back motifs use a 32 x 48 logical grid, enlarged with nearest-neighbor
sampling. Card silhouettes still match the shared front. Both avatars and all
four chips also use coarse 32 x 32 grids and nearest-neighbor enlargement.
This revision redraws the avatars and chips; the table and cards retain their designs.

`card_backs_preview.png` compares the pixel card backs at two scales.
`avatars_chips_preview.png` presents both avatars at 256, 64 and 48 pixels,
and all four chip colours at 160 and 76 pixels with sample value overlays.
`overview.png` presents all ten assets; `display_sizes.png` shows 120 x 180
card backs and both avatars at 256, 128, 64 and 48 pixels.
`previews/` contains actual J-54 betting/play screens for both card-back
variants, dark/felt/white matte sheets and enlarged card/chip checks.
`validation.json` checks every PNG against the game's base asset contracts.
The game catalog, installed assets, character expressions and saves are untouched.

Reproduce from the repository root with a new destination:
`python scripts/generate_j54_theme.py --out output/j54_theme_preview`
""",encoding="utf-8")
    with zipfile.ZipFile(out/"j54_theme_preview.zip","w",zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out.rglob("*")):
            if path.is_file() and path.suffix!=".zip":
                archive.write(path,path.relative_to(out).as_posix())
    print(json.dumps(rows,indent=2))


if __name__=="__main__":
    main()
