"""Shop overlay — buy items between rounds.

    app.scenes.push("shop", controller=ctrl, on_change=callback)

The scene only calls `controller.buy()` / `controller.reroll_shop()` and
redraws from `controller.view()`; `on_change` lets the table refresh its
widgets and event feed after a purchase.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.help_text import ITEM_HELP
from chaos_blackjack.app.view import Action, GameView, ShopOfferView
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import BAD, asset_name
from chaos_blackjack.gui.touch import TOUCH_SCROLL
from chaos_blackjack.gui.widgets import Button, WidgetGroup, fit_text, wrap_text

W, H = LOGICAL_SIZE
WARN = (0xE0, 0xB0, 0x60)  # a raised price

CARD_W, CARD_H, CARD_GAP = 236, 300, 24
ICON = 96
# A long shelf (e.g. Poker Head's "every product" testing switch) is a scrolling grid of small cards.
GRID_AFTER = 4                      # more offers than this -> grid
GRID_W, GRID_H, GRID_GAP, GRID_ICON = 182, 200, 12, 52
SCROLL_STEP = 60


@register_scene("shop")
class ShopScene(Scene):
    transparent = True

    def on_enter(
        self,
        controller: GameController | None = None,
        on_change: Callable[[], None] | None = None,
        on_poke: Callable[[], bool] | None = None,
        portrait_rect: pygame.Rect | None = None,
        **params,
    ) -> None:
        assert controller is not None
        self.controller = controller
        self.on_change = on_change
        self.on_poke = on_poke
        self.portrait_rect = portrait_rect
        self._poke_pending = False
        self.message: tuple[str, theme.Color] | None = None
        self.scroll = 0
        self.box = pygame.Rect(0, 0, 3 * CARD_W + 2 * CARD_GAP + 64, 500)
        self.close_button = Button(self.app.assets, (0, 0, 180, 52), "Close", self.app.scenes.pop, style="ghost",
                                   hotkey=pygame.K_ESCAPE)
        self.reroll_button = Button(self.app.assets, (0, 0, 200, 52), "Reroll", self._reroll, hotkey=pygame.K_r,
                                    font_size=theme.FONT_BODY)
        self._build()

    def _build(self) -> None:
        a = self.app.assets
        self.view: GameView = self.controller.view()
        self.card_rects: list[tuple[pygame.Rect, ShopOfferView]] = []
        self.buy_buttons: list[Button] = []
        offers = self.view.shop_offers
        self.grid = len(offers) > GRID_AFTER
        if self.grid:
            self._build_grid(offers)
        else:
            n = max(3, len(offers))
            self.box = pygame.Rect(0, 0, n * CARD_W + (n - 1) * CARD_GAP + 64, 500)
            self.box.center = (W // 2, H // 2)
            x0 = self.box.centerx - (len(offers) * (CARD_W + CARD_GAP) - CARD_GAP) // 2
            for i, offer in enumerate(offers):
                rect = pygame.Rect(x0 + i * (CARD_W + CARD_GAP), self.box.y + 84, CARD_W, CARD_H)
                self.card_rects.append((rect, offer))
                self.buy_buttons.append(Button(a, (rect.x + 24, rect.bottom - 64, rect.w - 48, 48), self._label(offer),
                                               self._buyer(offer), enabled=offer.affordable, font_size=theme.FONT_BODY,
                                               hotkey=pygame.K_1 + i, tooltip=offer.reason))
        self.close_button.rect.topleft = (self.box.centerx + 10, self.box.bottom - 72)
        self.reroll_button.rect.topleft = (self.box.centerx - 210, self.box.bottom - 72)
        price = self.view.shop_reroll_price
        self.reroll_button.text = ("Rerolled" if price is None else "Free reroll" if price == 0
                                   else f"Reroll  {price}")
        self.reroll_button.enabled = self.view.can(Action.REROLL)
        # A long shelf without any reroll (e.g. the "every product" switch) shows no reroll button.
        self.reroll_button.visible = not (self.grid and price is None)
        self.ui = WidgetGroup(*self.buy_buttons, self.reroll_button, self.close_button)

    @staticmethod
    def _label(offer: ShopOfferView) -> str:
        return "Sold" if offer.sold else "Borrow" if offer.kind == "finance" and offer.price == 0 else f"Buy  {offer.price}"

    def _build_grid(self, offers) -> None:
        a = self.app.assets
        self.box = pygame.Rect(0, 0, W - 80, H - 40)
        self.box.center = (W // 2, H // 2)
        self.area = pygame.Rect(self.box.x + 24, self.box.y + 76, self.box.w - 48, self.box.h - 76 - 96)
        cols = max(1, (self.area.w + GRID_GAP) // (GRID_W + GRID_GAP))
        rows = -(-len(offers) // cols)
        self.content_h = rows * (GRID_H + GRID_GAP) - GRID_GAP
        self.scroll = max(0, min(self.scroll, self.content_h - self.area.h))
        x0 = self.area.x + (self.area.w - (cols * (GRID_W + GRID_GAP) - GRID_GAP)) // 2
        for i, offer in enumerate(offers):
            row, col = divmod(i, cols)
            rect = pygame.Rect(x0 + col * (GRID_W + GRID_GAP), self.area.y + row * (GRID_H + GRID_GAP) - self.scroll,
                               GRID_W, GRID_H)
            self.card_rects.append((rect, offer))
            button = Button(a, (rect.x + 12, rect.bottom - 42, rect.w - 24, 34), self._label(offer),
                            self._buyer(offer), enabled=offer.affordable, font_size=theme.FONT_SMALL,
                            hotkey=pygame.K_1 + i if i < 9 else None, tooltip=offer.reason)
            button.visible = self.area.contains(button.rect)
            self.buy_buttons.append(button)

    def _reroll(self) -> None:
        if self._poke_pending:
            return
        try:
            self.controller.reroll_shop()
            self.message = ("New stock on the shelves.", theme.GOLD)
        except ActionError as e:
            self.message = (str(e), BAD)
        if self.on_change is not None:
            self.on_change()
        self._build()

    def _buyer(self, offer: ShopOfferView) -> Callable[[], None]:
        def buy() -> None:
            if self._poke_pending:
                return
            try:
                self.controller.buy(offer.item)
                if self.controller.view().choice is not None:
                    # e.g. every build slot is full: pick what to replace; nothing is charged before that.
                    self.message = None
                    self.app.scenes.push("choice", controller=self.controller, on_change=self._choice_changed)
                else:
                    self.message = (f"Bought {offer.name or asset_name(offer.item)}.", theme.GOLD)
            except ActionError as e:
                self.message = (str(e), BAD)
            if self.on_change is not None:
                self.on_change()
            self._build()

        return buy

    def _choice_changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
        self._build()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._poke_pending:
            return
        if (event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.on_poke is not None
                and self.portrait_rect is not None and self.portrait_rect.collidepoint(event.pos)):
            self._poke_pending = self.on_poke()
            return
        if event.type == pygame.MOUSEWHEEL and self.grid:
            self.scroll = max(0, self.scroll - event.y * SCROLL_STEP)
            self._build()
            return
        if event.type == TOUCH_SCROLL:
            if self.grid and self.area.collidepoint(event.pos):
                self.scroll = max(0, self.scroll + event.dy)
                self._build()
            return
        self.ui.handle_event(event)

    def on_resume(self, result=None) -> None:
        self._poke_pending = False
        self._build()

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        v = self.view
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, theme.PANEL, self.box, border_radius=14)
        pygame.draw.rect(surface, theme.GOLD_DIM, self.box, 2, border_radius=14)

        title = a.font(theme.FONT_HEADING, role="display").render("Shop", True, theme.GOLD)
        surface.blit(title, (self.box.x + 32, self.box.y + 20))
        small = a.font(theme.FONT_SMALL)
        rounds = v.shop_restock_in
        info = small.render(
            f"Bankroll {v.money}    New stock in {rounds} round{'s' if rounds != 1 else ''}", True, theme.TEXT_MUTED,
        )
        surface.blit(info, info.get_rect(midright=(self.box.right - 32, self.box.y + 44)))

        if self.grid:
            surface.set_clip(self.area)
            for rect, offer in self.card_rects:
                if rect.colliderect(self.area):
                    self._draw_small_offer(surface, rect, offer)
            surface.set_clip(None)
            if self.content_h > self.area.h:  # scroll bar
                k = self.area.h / self.content_h
                bar = pygame.Rect(self.area.right + 8, self.area.y + round(self.scroll * k), 4,
                                  max(24, round(self.area.h * k)))
                pygame.draw.rect(surface, theme.GOLD_DIM, bar, border_radius=2)
        else:
            for rect, offer in self.card_rects:
                self._draw_offer(surface, rect, offer)
        if not self.card_rects:
            empty = a.font(theme.FONT_BODY).render("Nothing for sale.", True, theme.TEXT_MUTED)
            surface.blit(empty, empty.get_rect(center=self.box.center))

        if self.message is not None:
            text, color = self.message
            img = small.render(text, True, color)
            surface.blit(img, img.get_rect(midbottom=(self.box.centerx, self.box.bottom - 82)))
        self.ui.draw(surface)

    def _draw_offer(self, surface: pygame.Surface, rect: pygame.Rect, offer: ShopOfferView) -> None:
        a = self.app.assets
        live = not offer.sold
        pygame.draw.rect(surface, theme.DARK, rect, border_radius=12)
        edge = theme.GROUP_COLORS.get(offer.group, theme.GOLD)  # the product group's colour
        if not offer.affordable:
            edge = tuple(round(c * 0.55) for c in edge)
        pygame.draw.rect(surface, edge, rect, 2 if offer.group else 1, border_radius=12)
        icon = a.image(offer.item, (ICON, ICON))
        if not live:
            icon = icon.copy()
            icon.set_alpha(90)
        surface.blit(icon, icon.get_rect(midtop=(rect.centerx, rect.y + 16)))
        font_name = a.font(theme.FONT_BODY, bold=True)
        label = fit_text(font_name, offer.name or asset_name(offer.item), rect.w - 20)
        name = font_name.render(label, True, theme.IVORY if live else theme.TEXT_MUTED)
        surface.blit(name, name.get_rect(midtop=(rect.centerx, rect.y + ICON + 26)))
        font = a.font(theme.FONT_TINY)
        top = rect.y + ICON + 54
        if offer.kind:  # a catalog product: its kind and when it acts (e.g. "Consumable · On your turn")
            tag = " · ".join(x for x in (offer.kind.capitalize(), offer.when) if x)
            for line in wrap_text(font, tag, rect.w - 24, max_lines=2):
                img = font.render(line, True, theme.GROUP_COLORS.get(offer.group, theme.GOLD_DIM))
                surface.blit(img, img.get_rect(midtop=(rect.centerx, top)))
                top += font.get_linesize()
            top += 2
        # A note above the button (why it cannot be bought, or why its price changed); the effect text
        # takes the space left between the tag and the note.
        if live and not offer.affordable:
            notes, color = [fit_text(font, offer.reason or "Not available now", rect.w - 24)], BAD
        elif live and offer.base_price is not None:
            notes = wrap_text(font, f"Base {offer.base_price} · {offer.price_note}", rect.w - 24, max_lines=2)
            color = WARN if offer.price > offer.base_price else theme.GOLD
        else:
            notes, color = [], theme.TEXT_MUTED
        lh = font.get_linesize()
        note_top = rect.bottom - 70 - len(notes) * lh
        room = max(1, (note_top - top) // lh) if notes else (3 if offer.kind else 4)
        description = offer.description or self.controller.registry.describe_item(offer.item)
        for i, line in enumerate(wrap_text(font, description, rect.w - 32, max_lines=min(room, 4))):
            img = font.render(line, True, theme.TEXT_MUTED)
            surface.blit(img, img.get_rect(midtop=(rect.centerx, top + i * lh)))
        for i, line in enumerate(notes):
            img = font.render(line, True, color)
            surface.blit(img, img.get_rect(midtop=(rect.centerx, note_top + i * lh)))

    def _draw_small_offer(self, surface: pygame.Surface, rect: pygame.Rect, offer: ShopOfferView) -> None:
        """A grid card: icon and name, kind and phase, two lines of effect, why it cannot be bought."""
        a = self.app.assets
        live = not offer.sold
        pygame.draw.rect(surface, theme.DARK, rect, border_radius=10)
        edge = theme.GROUP_COLORS.get(offer.group, theme.GOLD)
        if not offer.affordable:
            edge = tuple(round(c * 0.55) for c in edge)
        pygame.draw.rect(surface, edge, rect, 2 if offer.group else 1, border_radius=10)
        icon = a.image(offer.item, (GRID_ICON, GRID_ICON))
        if not live:
            icon = icon.copy()
            icon.set_alpha(90)
        surface.blit(icon, (rect.x + 10, rect.y + 10))
        font_name, tiny = a.font(theme.FONT_SMALL, bold=True), a.font(theme.FONT_TINY)
        x, width = rect.x + GRID_ICON + 18, rect.w - GRID_ICON - 26
        for i, line in enumerate(wrap_text(font_name, offer.name or asset_name(offer.item), width, max_lines=2)):
            surface.blit(font_name.render(line, True, theme.IVORY if live else theme.TEXT_MUTED),
                         (x, rect.y + 10 + i * font_name.get_linesize()))
        top = rect.y + GRID_ICON + 18
        if offer.kind:
            tag = " · ".join(x for x in (offer.kind.capitalize(), offer.when) if x)
            img = tiny.render(fit_text(tiny, tag, rect.w - 20), True, theme.GROUP_COLORS.get(offer.group, theme.GOLD_DIM))
            surface.blit(img, (rect.x + 10, top))
            top += tiny.get_linesize()
        if live and not offer.affordable:
            lines = [fit_text(tiny, offer.reason or "Not available now", rect.w - 20)]
            color = BAD
        elif live and offer.base_price is not None:
            lines = [fit_text(tiny, f"Base {offer.base_price} · {offer.price_note}", rect.w - 20)]
            color = WARN if offer.price > offer.base_price else theme.GOLD
        else:
            lines = wrap_text(tiny, offer.description or self.controller.registry.describe_item(offer.item),
                              rect.w - 20, max_lines=3)
            color = theme.TEXT_MUTED
        for i, line in enumerate(lines):
            surface.blit(tiny.render(line, True, color), (rect.x + 10, top + 2 + i * tiny.get_linesize()))
