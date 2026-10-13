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
from chaos_blackjack.gui.widgets import Button, WidgetGroup, wrap_text

W, H = LOGICAL_SIZE

CARD_W, CARD_H, CARD_GAP = 236, 300, 24
ICON = 96


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
        self.box = pygame.Rect(0, 0, 3 * CARD_W + 2 * CARD_GAP + 64, 500)
        self.box.center = (W // 2, H // 2)
        self.close_button = Button(
            self.app.assets, (self.box.centerx + 10, self.box.bottom - 72, 180, 52), "Close",
            self.app.scenes.pop, style="ghost", hotkey=pygame.K_ESCAPE,
        )
        self.reroll_button = Button(
            self.app.assets, (self.box.centerx - 210, self.box.bottom - 72, 200, 52), "Reroll",
            self._reroll, hotkey=pygame.K_r, font_size=theme.FONT_BODY,
        )
        self._build()

    def _build(self) -> None:
        a = self.app.assets
        self.view: GameView = self.controller.view()
        self.card_rects: list[tuple[pygame.Rect, ShopOfferView]] = []
        self.buy_buttons: list[Button] = []
        offers = self.view.shop_offers
        x0 = self.box.centerx - (len(offers) * (CARD_W + CARD_GAP) - CARD_GAP) // 2
        for i, offer in enumerate(offers):
            rect = pygame.Rect(x0 + i * (CARD_W + CARD_GAP), self.box.y + 84, CARD_W, CARD_H)
            self.card_rects.append((rect, offer))
            label = "Sold" if offer.sold else f"Buy  {offer.price}"
            button = Button(a, (rect.x + 24, rect.bottom - 64, rect.w - 48, 48), label,
                            self._buyer(offer.item), enabled=offer.affordable,
                            font_size=theme.FONT_BODY, hotkey=pygame.K_1 + i)
            self.buy_buttons.append(button)
        price = self.view.shop_reroll_price
        self.reroll_button.text = ("Rerolled" if price is None else "Free reroll" if price == 0
                                   else f"Reroll  {price}")
        self.reroll_button.enabled = self.view.can(Action.REROLL)
        self.ui = WidgetGroup(*self.buy_buttons, self.reroll_button, self.close_button)

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

    def _buyer(self, item_id: str) -> Callable[[], None]:
        def buy() -> None:
            if self._poke_pending:
                return
            try:
                self.controller.buy(item_id)
                self.message = (f"Bought {asset_name(item_id)}.", theme.GOLD)
            except ActionError as e:
                self.message = (str(e), BAD)
            if self.on_change is not None:
                self.on_change()
            self._build()

        return buy

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._poke_pending:
            return
        if (event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.on_poke is not None
                and self.portrait_rect is not None and self.portrait_rect.collidepoint(event.pos)):
            self._poke_pending = self.on_poke()
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
        pygame.draw.rect(surface, theme.GOLD if offer.affordable else theme.GOLD_DIM, rect, 1, border_radius=12)
        icon = a.image(offer.item, (ICON, ICON))
        if not live:
            icon = icon.copy()
            icon.set_alpha(90)
        surface.blit(icon, icon.get_rect(midtop=(rect.centerx, rect.y + 16)))
        name = a.font(theme.FONT_BODY, bold=True).render(asset_name(offer.item), True,
                                                          theme.IVORY if live else theme.TEXT_MUTED)
        surface.blit(name, name.get_rect(midtop=(rect.centerx, rect.y + ICON + 26)))
        font = a.font(theme.FONT_TINY)
        for i, line in enumerate(wrap_text(font, offer.description or self.controller.registry.describe_item(offer.item),
                                           rect.w - 32, max_lines=4)):
            img = font.render(line, True, theme.TEXT_MUTED)
            surface.blit(img, img.get_rect(midtop=(rect.centerx, rect.y + ICON + 58 + i * font.get_linesize())))
        if live and not offer.affordable:
            note = font.render("Keep enough chips to bet", True, BAD)
            surface.blit(note, note.get_rect(midbottom=(rect.centerx, rect.bottom - 70)))
