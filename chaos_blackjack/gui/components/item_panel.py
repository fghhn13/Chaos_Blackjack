"""Right table column: the shoe, the item inventory (or a table's own facts,
e.g. J-54's protocol and deck) and the shop button.

Items are buttons: clicking one calls `on_use(item_id)` while the view allows
`use_item`. Hovering shows what the item does. The shop button calls
`on_shop()` while betting.
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
from chaos_blackjack.gui.widgets import Button, Widget, draw_heading, draw_panel, draw_tooltip, fit_text

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
        on_shop: Callable[[], None],
    ) -> None:
        self.assets = assets
        self.rect = pygame.Rect(rect)
        self.on_use = on_use
        self.items: tuple[ItemView, ...] = ()
        self.can_use = False
        self.restock_in = 0
        self.table_info: tuple[tuple[str, str], ...] = ()
        self.shop_button = Button(
            assets, (self.rect.x + 14, self.rect.bottom - 62, self.rect.w - 28, 48), "Shop",
            on_shop, hotkey=pygame.K_b, font_size=theme.FONT_BODY,
        )
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
        # Each view builds new ItemView objects; keep the hover on the same item id.
        if self.hovered is not None:
            self.hovered = next((i for i in self.items if i.id == self.hovered.id), None)
        self.can_use = v.can(Action.USE_ITEM)
        self.shop_button.enabled = v.can(Action.BUY)
        self.restock_in = v.shop_restock_in
        self.table_info = v.table_info

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.shop_button.handle_event(event) and event.type != pygame.MOUSEMOTION:
            return True
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
        if self.table_info and not self.items:
            self._draw_table_info(surface)
            self._draw_shop(surface)
            return
        y = draw_heading(surface, a, "Items", (r.x + 14, self._items_top()), inner_w)

        body = a.font(theme.FONT_SMALL, bold=True)
        tiny = a.font(theme.FONT_TINY)
        self.item_rects = []
        if not self.items:
            surface.blit(tiny.render("No items yet", True, theme.TEXT_MUTED), (r.x + 14, y + 4))
        for i, item in enumerate(self.items):
            row = pygame.Rect(r.x + 8, y + i * ITEM_ROW, r.w - 16, ITEM_ROW - 6)
            if row.bottom > r.bottom - 100:
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
            surface.blit(tiny.render(hint, True, theme.TEXT_MUTED), (r.x + 14, r.bottom - 112))

        self._draw_shop(surface)

    def _draw_table_info(self, surface: pygame.Surface) -> None:
        """The table's own facts (label over value), in place of an empty inventory."""
        a, r = self.assets, self.rect
        y = draw_heading(surface, a, "Experiment", (r.x + 14, self._items_top()), r.w - 28)
        label_font, value_font = a.font(theme.FONT_TINY, bold=True), a.font(theme.FONT_SMALL)
        for label, value in self.table_info:
            if y + 40 > r.bottom - 100:
                break
            surface.blit(label_font.render(label.upper(), True, theme.GOLD_DIM), (r.x + 14, y))
            y += label_font.get_linesize()
            surface.blit(value_font.render(fit_text(value_font, value, r.w - 28), True, theme.IVORY), (r.x + 14, y))
            y += value_font.get_linesize() + 6

    def _draw_shop(self, surface: pygame.Surface) -> None:
        """Shop button (usable while betting) and the restock countdown."""
        r = self.rect
        n = self.restock_in
        note = self.assets.font(theme.FONT_TINY).render(
            f"New stock in {n} round{'s' if n != 1 else ''}", True, theme.TEXT_MUTED,
        )
        surface.blit(note, note.get_rect(midbottom=(r.centerx, self.shop_button.rect.y - 6)))
        self.shop_button.draw(surface)

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if self.hovered is not None:
            description = self.hovered.description or ITEM_HELP.get(self.hovered.id, "")
            text = f"{asset_name(self.hovered.id)}: {description}"
            if not self.can_use:
                text += " (usable on your turn)"
            row = next((rect for rect, i in self.item_rects if i is self.hovered), None)
            if row is None:
                return  # hovered row not laid out yet (e.g. synced after the last draw)
            draw_tooltip(surface, self.assets, text, (self.rect.x - 292, row.y))
