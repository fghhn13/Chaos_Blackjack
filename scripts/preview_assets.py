"""Render game screens and asset check sheets headlessly (needs only pygame).

Writes PNGs into --out (default output/asset_previews/):
  scene_menu.png, scene_menu_chaos.png      main menu (chaos off / on portrait)
  scene_table_betting.png                    table while betting (chips)
  scene_table_play.png                       table mid-round (card faces + backs)
  scene_table_chaos.png                      chaos on: active rule, narration, items
  scene_table_tooltip.png                    same, hovering an item
  scene_ending_victory.png, scene_ending_bankrupt.png
  gallery_<category>.png                     asset gallery, one per tab
  matte_<id>.png                             asset large on dark / felt / white
  zoom_cards.png, zoom_chips.png             in-game sizes magnified x3
  motion_*.png (with --motion)               animation filmstrips: deal, settle, chaos glitch

  python scripts/preview_assets.py
  python scripts/preview_assets.py --matte card_back card_front_blank peek chip_1
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["CHAOS_USE_LLM"] = "0"  # previews must never call a billed model

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from chaos_blackjack.app.config import RunConfig  # noqa: E402
from chaos_blackjack.app.controller import GameController  # noqa: E402
from chaos_blackjack.app.view import CardView, TablePhase  # noqa: E402
from chaos_blackjack.gui import theme  # noqa: E402
from chaos_blackjack.gui.app import App  # noqa: E402
from chaos_blackjack.gui.assets.manifest import MANIFEST, by_category  # noqa: E402
from chaos_blackjack.gui.components.cards import CARD_SIZE, CardRenderer  # noqa: E402
from chaos_blackjack.gui.settings import GuiSettings, default_asset_dirs  # noqa: E402

MATTES = {"dark": theme.DARK, "felt": (0x26, 0x3B, 0x34), "white": (255, 255, 255)}
DEFAULT_MATTE_IDS = ("card_back", "card_front_blank", "chip_1", "peek", "chaos_calm")
CHIP_SIZE = (76, 76)
ZOOM = 3


def render_scene(app: App, name: str, setup=None, after_draw=None, **params) -> pygame.Surface:
    """Draw one frame of `name`. `after_draw(scene)` runs after a first frame
    (e.g. to hover something laid out during draw) and the frame is redrawn."""
    app.scenes.reset(name, **params)
    app.scenes.apply_pending()
    if setup:
        setup(app.scenes.top)
    app.scenes.update(0.0)
    app.scenes.apply_pending()
    app.canvas.fill(theme.DARK)
    app.scenes.draw(app.canvas)
    if after_draw:
        after_draw(app.scenes.top)
        app.canvas.fill(theme.DARK)
        app.scenes.draw(app.canvas)
    return app.canvas.copy()


def in_play_controller() -> GameController:
    """A seeded round that is waiting for the player's decision."""
    for seed in range(1, 200):
        c = GameController(RunConfig(seed=seed, enable_chaos=False))
        c.place_bet(10)
        if c.phase == TablePhase.PLAYER_TURN:
            return c
    raise RuntimeError("no seed produced a player turn")


def chaos_controller() -> GameController:
    """Chaos on, a rule in play, the player to act, and a few items in hand."""
    items = ("peek", "peek", "fate_oracle", "shield", "hole_card_hacker")
    for seed in range(1, 400):
        c = GameController(RunConfig(seed=seed, enable_chaos=True))
        c.run.items = items  # preview only: start with a few items in hand
        c.place_bet(15)
        if c.phase == TablePhase.CHAOS:
            c.resolve_chaos()
        v = c.view()
        if c.phase == TablePhase.PLAYER_TURN and v.active_rules:
            return c
    raise RuntimeError("no seed produced a chaos rule before the player turn")


def _catch_up(scene) -> None:
    """Feed notices queued before the scene existed (narration, rule) to it."""
    scene._pump_notices()
    scene._sync_widgets()


def _hover_first_item(scene) -> None:
    rect, _ = scene.item_panel.item_rects[0]
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": rect.center, "rel": (0, 0), "buttons": (0, 0, 0)}))


FRAME_DT = 1 / 60


def film(app: App, times: list[float], start=None) -> list[tuple[float, pygame.Surface]]:
    """Run the top scene at 60 fps and grab the canvas at each time (seconds after `start`)."""
    if start is not None:
        start(app.scenes.top)
    frames, t = [], 0.0
    for target in sorted(times):
        while t < target - 1e-9:
            app.scenes.update(FRAME_DT)
            app.scenes.apply_pending()
            t += FRAME_DT
        app.canvas.fill(theme.DARK)
        app.scenes.draw(app.canvas)
        frames.append((target, app.canvas.copy()))
    return frames


def film_sheet(app: App, frames: list[tuple[float, pygame.Surface]], cols: int = 3, scale: float = 0.4) -> pygame.Surface:
    w, h = (round(v * scale) for v in frames[0][1].get_size())
    rows = (len(frames) + cols - 1) // cols
    sheet = pygame.Surface((cols * (w + 8) + 8, rows * (h + 30) + 8))
    sheet.fill((12, 12, 12))
    font = app.assets.font(theme.FONT_SMALL, bold=True)
    for i, (t, frame) in enumerate(frames):
        x, y = 8 + (i % cols) * (w + 8), 8 + (i // cols) * (h + 30)
        sheet.blit(font.render(f"t = {t:.2f}s", True, theme.IVORY), (x, y))
        sheet.blit(pygame.transform.smoothscale(frame, (w, h)), (x, y + 24))
    return sheet


def fresh_chaos_seed() -> int:
    """A seed whose first round gets a chaos rule (probed on a throwaway controller)."""
    for seed in range(1, 400):
        c = GameController(RunConfig(seed=seed, enable_chaos=True))
        c.place_bet(15)
        if c.phase == TablePhase.CHAOS:
            c.resolve_chaos()
            if c.view().active_rules:
                return seed
    raise RuntimeError("no seed applies a chaos rule in round one")


def motion_strips(app: App) -> dict[str, pygame.Surface]:
    out: dict[str, pygame.Surface] = {}
    app.scenes.reset("table", controller=in_play_seed_controller())
    app.scenes.apply_pending()
    out["motion_deal"] = film_sheet(app, film(app, [0.0, 0.12, 0.25, 0.4, 0.55, 0.9],
                                              start=lambda s: s._deal(15)))
    out["motion_settle"] = film_sheet(app, film(app, [0.3, 0.8, 1.15, 1.5, 1.9, 2.6],
                                                start=lambda s: s._command("stand")()))
    app.scenes.reset("table", controller=GameController(RunConfig(seed=fresh_chaos_seed(), enable_chaos=True)))
    app.scenes.apply_pending()
    out["motion_glitch"] = film_sheet(app, film(app, [1.0, 1.3, 1.36, 1.45, 1.6, 1.9],
                                                start=lambda s: s._deal(15)))
    return out


def in_play_seed_controller() -> GameController:
    """Fresh controller (betting phase) whose first deal leaves the player to act."""
    for seed in range(1, 200):
        probe = GameController(RunConfig(seed=seed, enable_chaos=False))
        probe.place_bet(15)
        if probe.phase == TablePhase.PLAYER_TURN:
            return GameController(RunConfig(seed=seed, enable_chaos=False))
    raise RuntimeError("no seed produced a player turn")


def matte_sheet(app: App, asset_id: str, max_h: int = 640) -> pygame.Surface:
    img = app.assets.image(asset_id)
    w, h = img.get_size()
    if h > max_h:
        img = app.assets.image(asset_id, (round(w * max_h / h), max_h))
        w, h = img.get_size()
    pad = 24
    label_h = 28
    sheet = pygame.Surface(((w + pad * 2) * len(MATTES), h + pad * 2 + label_h))
    font = app.assets.font(theme.FONT_SMALL)
    for i, (name, color) in enumerate(MATTES.items()):
        cell = pygame.Rect(i * (w + pad * 2), 0, w + pad * 2, sheet.get_height())
        sheet.fill(color, cell)
        sheet.blit(img, (cell.x + pad, pad + label_h))
        ink = (0, 0, 0) if name == "white" else theme.IVORY
        sheet.blit(font.render(f"{asset_id} on {name}  [{app.assets.source(asset_id)}]", True, ink),
                   (cell.x + pad, 6))
    return sheet


def zoom_cards(app: App) -> pygame.Surface:
    cards = CardRenderer(app.assets)
    views = [CardView("A", "♠"), CardView("10", "♥"), CardView("K", "♦"), CardView("Q", "♣"),
             CardView("", "", face_up=False)]
    gap = 16
    w, h = CARD_SIZE
    strip = pygame.Surface((len(views) * (w + gap) + gap, h + gap * 2))
    strip.fill(MATTES["felt"])
    for i, v in enumerate(views):
        strip.blit(cards.render(v, CARD_SIZE), (gap + i * (w + gap), gap))
    return pygame.transform.scale_by(strip, ZOOM)


def zoom_chips(app: App) -> pygame.Surface:
    values = sorted(int(spec.id.split("_")[1]) for spec in MANIFEST.values() if spec.category == "chip")
    gap = 16
    w, h = CHIP_SIZE
    strip = pygame.Surface((len(values) * (w + gap) + gap, h + gap * 2))
    strip.fill(MATTES["felt"])
    font = app.assets.font(theme.FONT_BODY, bold=True)
    for i, v in enumerate(values):  # same composition as BetPanel's ChipButton
        rect = pygame.Rect(gap + i * (w + gap), gap, w, h)
        strip.blit(app.assets.image(f"chip_{v}", CHIP_SIZE), rect)
        label = font.render(str(v), True, theme.INK)
        strip.blit(label, label.get_rect(center=rect.center))
    return pygame.transform.scale_by(strip, ZOOM)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "output" / "asset_previews"))
    ap.add_argument("--dir", action="append", help="asset folder(s) in search order (default: the game's)")
    ap.add_argument("--matte", nargs="*", default=list(DEFAULT_MATTE_IDS), help="ids for matte sheets")
    ap.add_argument("--motion", action="store_true", help="also render animation filmstrips")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dirs = tuple(Path(d) for d in args.dir) if args.dir else default_asset_dirs()
    app = App(GuiSettings(asset_dirs=dirs))
    import chaos_blackjack.gui.scenes  # noqa: F401  (registers scenes)

    shots: dict[str, pygame.Surface] = {}
    app.prefs.enable_chaos = False
    shots["scene_menu"] = render_scene(app, "menu")
    app.prefs.enable_chaos = True
    shots["scene_menu_chaos"] = render_scene(app, "menu")
    app.prefs.enable_chaos = False
    shots["scene_table_betting"] = render_scene(
        app, "table", controller=GameController(RunConfig(seed=1, enable_chaos=False)))
    shots["scene_table_play"] = render_scene(app, "table", controller=in_play_controller())
    shots["scene_table_chaos"] = render_scene(app, "table", setup=_catch_up, controller=chaos_controller())
    shots["scene_table_tooltip"] = render_scene(app, "table", setup=_catch_up, after_draw=_hover_first_item,
                                                controller=chaos_controller())
    shots["scene_ending_victory"] = render_scene(app, "ending", kind="victory", money=400, rounds=12)
    shots["scene_ending_bankrupt"] = render_scene(app, "ending", kind="defeat", money=0, rounds=9)
    for category in by_category():
        shots[f"gallery_{category}"] = render_scene(app, "gallery", setup=lambda s, c=category: s._select(c))
    for asset_id in args.matte:
        if asset_id not in MANIFEST:
            print(f"skip unknown id {asset_id!r}", file=sys.stderr)
            continue
        shots[f"matte_{asset_id}"] = matte_sheet(app, asset_id)
    shots["zoom_cards"] = zoom_cards(app)
    shots["zoom_chips"] = zoom_chips(app)
    if args.motion:
        shots.update(motion_strips(app))

    for name, surf in shots.items():
        pygame.image.save(surf, str(out / f"{name}.png"))
    print(f"{len(shots)} previews in {out}")
    for name in shots:
        print(f"  {name}.png")
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
