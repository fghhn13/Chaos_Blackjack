"""Asset gallery — check generated art in-game.

Shows every manifest asset, whether it comes from a file or a placeholder,
and opens a large preview on dark / felt / white backdrops (to spot alpha
fringes, per generation-plan.md §7). F5 rescans the asset folders.
"""

from __future__ import annotations

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.assets.manifest import by_category
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE

CATEGORY_LABELS = {
    "background": "Backgrounds",
    "card": "Cards",
    "chip": "Chips",
    "character": "Chaos AI",
    "item": "Items",
    "rule": "Chaos Rules",
}
BACKDROPS = (("dark", theme.DARK), ("felt", theme.FELT), ("white", (255, 255, 255)))

TILE_W, TILE_H, TILE_GAP = 170, 190, 18
GRID_TOP = 150


@register_scene("gallery")
class GalleryScene(Scene):
    def on_enter(self, **params) -> None:
        self.categories = list(by_category())
        self.current = self.categories[0]
        self.tiles: list[tuple[pygame.Rect, str]] = []
        a = self.app.assets
        tabs = []
        x = 40
        for cat in self.categories:
            label = CATEGORY_LABELS.get(cat, cat)
            w = 32 + a.font(theme.FONT_BODY).size(label)[0]
            tabs.append(Button(a, (x, 84, w, 42), label, lambda c=cat: self._select(c),
                               style="ghost", font_size=theme.FONT_BODY))
            x += w + 10
        self.tabs = tabs
        self.ui = WidgetGroup(
            *tabs,
            Button(a, (W - 160, 24, 120, 42), "Back", self.app.scenes.pop,
                   style="ghost", hotkey=pygame.K_ESCAPE, font_size=theme.FONT_BODY),
        )
        self._select(self.current)

    def _select(self, category: str) -> None:
        self.current = category
        for tab, cat in zip(self.tabs, self.categories):
            tab.style = "primary" if cat == category else "ghost"
        specs = by_category()[category]
        per_row = (W - 80 + TILE_GAP) // (TILE_W + TILE_GAP)
        self.tiles = []
        for i, spec in enumerate(specs):
            r, c = divmod(i, per_row)
            rect = pygame.Rect(40 + c * (TILE_W + TILE_GAP), GRID_TOP + r * (TILE_H + TILE_GAP), TILE_W, TILE_H)
            self.tiles.append((rect, spec.id))

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.ui.handle_event(event):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, asset_id in self.tiles:
                if rect.collidepoint(event.pos):
                    self.app.scenes.push("asset_preview", asset_id=asset_id)
                    return

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        surface.fill(theme.DARK)
        total = sum(len(v) for v in by_category().values())
        done = sum(1 for v in by_category().values() for s in v if a.has_file(s.id))
        title = a.font(theme.FONT_HEADING, role="display").render("Asset Gallery", True, theme.GOLD)
        surface.blit(title, (40, 24))
        stat = a.font(theme.FONT_BODY).render(f"Replaced {done} / {total}    click to enlarge    F5 rescan",
                                              True, theme.TEXT_MUTED)
        surface.blit(stat, (290, 36))
        self.ui.draw(surface)

        mouse = self.app.mouse_pos()
        for rect, asset_id in self.tiles:
            hovered = rect.collidepoint(mouse)
            pygame.draw.rect(surface, theme.PANEL, rect, border_radius=8)
            pygame.draw.rect(surface, theme.GOLD if hovered else (0x2A, 0x33, 0x35), rect, 2, border_radius=8)
            thumb = a.image_fit(asset_id, (TILE_W - 24, TILE_H - 64))
            surface.blit(thumb, thumb.get_rect(center=(rect.centerx, rect.y + (TILE_H - 40) // 2)))
            name = a.font(theme.FONT_SMALL).render(asset_id, True, theme.TEXT)
            surface.blit(name, name.get_rect(midbottom=(rect.centerx, rect.bottom - 22)))
            src = a.source(asset_id)
            tag_text, tag_color = {"file": ("file", (0x5C, 0xC0, 0x7A)),
                                   "placeholder": ("placeholder", theme.TEXT_MUTED)}.get(src, ("missing", theme.CHAOS_MAGENTA))
            tag = a.font(14).render(tag_text, True, tag_color)
            surface.blit(tag, tag.get_rect(midbottom=(rect.centerx, rect.bottom - 4)))


@register_scene("asset_preview")
class AssetPreviewScene(Scene):
    transparent = True

    def on_enter(self, asset_id: str = "", **params) -> None:
        self.asset_id = asset_id
        self.backdrop = 0

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_b:
            self.backdrop = (self.backdrop + 1) % len(BACKDROPS)
        elif (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE) or (
            event.type == pygame.MOUSEBUTTONUP and event.button == 1
        ):
            self.app.scenes.pop()

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 200))
        surface.blit(shade, (0, 0))
        box = pygame.Rect(0, 0, int(W * 0.8), int(H * 0.74))
        box.center = (W // 2, H // 2 - 10)
        label, color = BACKDROPS[self.backdrop]
        pygame.draw.rect(surface, color, box, border_radius=10)
        img = a.image_fit(self.asset_id, (box.w - 40, box.h - 40))
        surface.blit(img, img.get_rect(center=box.center))

        native = a.image(self.asset_id).get_size()
        path = a.path(self.asset_id)
        info = f"{self.asset_id}   {native[0]}×{native[1]}   {path if path else 'procedural placeholder'}"
        for i, text in enumerate((info, f"Backdrop: {label} (B to switch)   click or Esc to close")):
            img = a.font(theme.FONT_SMALL).render(text, True, theme.TEXT if i == 0 else theme.TEXT_MUTED)
            surface.blit(img, img.get_rect(midtop=(W // 2, box.bottom + 12 + i * 24)))
