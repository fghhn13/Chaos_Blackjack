"""Generic inventory overlay: every registered item works without a UI edit."""

from __future__ import annotations

import pygame

from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup


@register_scene("items")
class ItemsScene(Scene):
    transparent = True

    def on_enter(self, controller: GameController, **params) -> None:
        self.controller = controller
        self.items = controller.view().items
        self.index = 0
        self.message = ""
        a = self.app.assets
        self.previous = Button(a, (300, 460, 150, 48), "Previous", lambda: self._move(-1))
        self.use = Button(a, (470, 460, 150, 48), "Use  Enter", self._use, hotkey=pygame.K_RETURN)
        self.next = Button(a, (640, 460, 150, 48), "Next", lambda: self._move(1))
        self.ui = WidgetGroup(
            self.previous, self.use, self.next,
            Button(a, (810, 460, 150, 48), "Back  Esc", self.app.scenes.pop,
                   style="ghost", hotkey=pygame.K_ESCAPE),
        )
        self.use.enabled = bool(self.items)
        self.previous.enabled = self.next.enabled = len(self.items) > 1

    def _move(self, delta: int) -> None:
        if self.items:
            self.index = (self.index + delta) % len(self.items)
            self.message = ""

    def _use(self) -> None:
        if not self.items:
            return
        try:
            result = self.controller.use_item(self.items[self.index].id)
        except ActionError as exc:
            self.message = str(exc)
            return
        if result.ok:
            self.app.scenes.pop()
        else:
            self.message = result.message

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._move(-1 if event.key == pygame.K_LEFT else 1)
        else:
            self.ui.handle_event(event)

    def draw(self, surface) -> None:
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))
        pygame.draw.rect(surface, theme.PANEL, (260, 190, 740, 360), border_radius=12)
        a = self.app.assets
        text = "Inventory"
        if self.items:
            item = self.items[self.index]
            text = f"{item.id}  x{item.count}    ({self.index + 1}/{len(self.items)})"
        surface.blit(a.font(theme.FONT_HEADING).render(text, True, theme.GOLD), (300, 225))
        description = "No items available."
        if self.items:
            description = self.items[self.index].description or "Use this item."
        font = a.font(theme.FONT_BODY)
        # Wrap help and failures so content packs do not need bespoke widgets.
        y = 300
        for text, color in ((description, theme.IVORY), (self.message, theme.CHAOS_MAGENTA)):
            line = ""
            for word in text.split():
                candidate = (line + " " + word).strip()
                if font.size(candidate)[0] > 650 and line:
                    surface.blit(font.render(line, True, color), (300, y))
                    y += 28
                    line = word
                else:
                    line = candidate
            if line:
                surface.blit(font.render(line, True, color), (300, y))
                y += 36
        self.ui.draw(surface)
