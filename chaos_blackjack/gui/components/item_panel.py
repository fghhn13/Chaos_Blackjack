"""Right table column: the shoe, the item inventory and the reward streak.

Items are buttons: clicking one calls `on_use(item_id)` while the view allows
`use_item`. Hovering shows what the item does.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.app.help_text import ITEM_HELP
from chaos_blackjack.app.view import Action, GameView, ItemView
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.cards import CARD_SIZE
from chaos_blackjack.gui.texts import asset_name
from chaos_blackjack.gui.widgets import Widget, draw_heading, draw_panel, draw_tooltip, fit_text

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

ITEM_ROW = 52
ITEM_ICON = 40


class ItemPanel(Widget):
    def __init__(
        self,
        assets: "AssetManager",
        rect: pygame.Rect | tuple[int, int, int, int],
        on_use: Callable[[str], None],
    ) -> None:
        self.assets = assets
        self.rect = pygame.Rect(rect)
        self.on_use = on_use
        self.items: tuple[ItemView, ...] = ()
        self.can_use = False
        self.streak = 0
        self.reward_streak = 0
        self.item_rects: list[tuple[pygame.Rect, ItemView]] = []
        self.hovered: ItemView | None = None
        self._mouse = (0, 0)

    @property
    def deck_rect(self) -> pygame.Rect:
        rect = pygame.Rect((0, 0), CARD_SIZE)
        rect.midtop = (self.rect.centerx, self.rect.y + 24)
        return rect

    def _items_top(self) -> int:
        return self.deck_rect.bottom + 40

    def sync(self, v: GameView) -> None:
        self.items = tuple(i for i in v.items if i.count > 0)
        self.can_use = v.can(Action.USE_ITEM)
        self.streak, self.reward_streak = v.win_streak, v.reward_streak

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._mouse = event.pos
            self.hovered = next((i for rect, i in self.item_rects if rect.collidepoint(event.pos)), None)
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.can_use:
            hit = next((i for rect, i in self.item_rects if rect.collidepoint(event.pos)), None)
            if hit is not None:
                self.on_use(hit.id)
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        a = self.assets
        r = self.rect
        draw_panel(surface, r)
        inner_w = r.w - 28
        y = draw_heading(surface, a, "Items", (r.x + 14, self._items_top()), inner_w)

        body = a.font(theme.FONT_SMALL, bold=True)
        tiny = a.font(theme.FONT_TINY)
        self.item_rects = []
        if not self.items:
            surface.blit(tiny.render("No items yet", True, theme.TEXT_MUTED), (r.x + 14, y + 4))
        for i, item in enumerate(self.items):
            row = pygame.Rect(r.x + 8, y + i * ITEM_ROW, r.w - 16, ITEM_ROW - 6)
            if row.bottom > r.bottom - 64:
                break
            active = self.can_use
            if item is self.hovered and active:
                pygame.draw.rect(surface, theme.FELT, row, border_radius=8)
                pygame.draw.rect(surface, theme.GOLD, row, 1, border_radius=8)
            icon = a.image(item.id, (ITEM_ICON, ITEM_ICON))
            if not active:
                icon = icon.copy()
                icon.set_alpha(110)
            surface.blit(icon, (row.x + 6, row.centery - ITEM_ICON // 2))
            count = body.render(f"×{item.count}", True, theme.GOLD if active else theme.TEXT_MUTED)
            surface.blit(count, count.get_rect(midright=(row.right - 10, row.centery)))
            tx = row.x + ITEM_ICON + 14
            name = fit_text(body, asset_name(item.id), row.right - 18 - count.get_width() - tx)
            surface.blit(body.render(name, True, theme.IVORY if active else theme.TEXT_MUTED), (tx, row.centery - 10))
            self.item_rects.append((row, item))
        hint = "Click an item to use it" if self.can_use and self.items else ""
        if hint:
            surface.blit(tiny.render(hint, True, theme.TEXT_MUTED), (r.x + 14, r.bottom - 76))

        self._draw_streak(surface, r.bottom - 48)

    def _draw_streak(self, surface: pygame.Surface, y: int) -> None:
        """Reward progress: one pip per win needed for the next item."""
        a = self.assets
        r = self.rect
        label = a.font(theme.FONT_TINY, bold=True).render("WIN STREAK", True, theme.GOLD_DIM)
        surface.blit(label, (r.x + 14, y))
        need = max(1, self.reward_streak)
        filled = self.streak % need if self.streak else 0
        for i in range(need):
            c = (r.x + 24 + i * 22, y + 30)
            if i < filled:
                pygame.draw.circle(surface, theme.GOLD, c, 7)
            else:
                pygame.draw.circle(surface, theme.GOLD_DIM, c, 7, 1)
        note = a.font(theme.FONT_TINY).render(f"{need - filled} more win{'s' if need - filled != 1 else ''} for an item",
                                              True, theme.TEXT_MUTED)
        surface.blit(note, note.get_rect(midright=(r.right - 14, y + 30)))

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if self.hovered is not None:
            text = f"{asset_name(self.hovered.id)}: {ITEM_HELP.get(self.hovered.id, '')}"
            if not self.can_use:
                text += " (usable on your turn)"
            row = next(rect for rect, i in self.item_rects if i is self.hovered)
            draw_tooltip(surface, self.assets, text, (self.rect.x - 292, row.y))
