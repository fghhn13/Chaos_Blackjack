"""Generic yes/no dialog drawn over the current scene.

    app.scenes.push("confirm", message="...", on_confirm=callback)
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE


@register_scene("confirm")
class ConfirmScene(Scene):
    transparent = True

    def on_enter(
        self,
        message: str = "Are you sure?",
        on_confirm: Callable[[], None] | None = None,
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        **params,
    ) -> None:
        self.message = message
        self.on_confirm = on_confirm
        a = self.app.assets
        self.box = pygame.Rect(0, 0, 520, 220)
        self.box.center = (W // 2, H // 2)
        bx, by = self.box.centerx, self.box.bottom - 80
        self.ui = WidgetGroup(
            Button(a, (bx - 190, by, 170, 52), confirm_text, self._confirm, hotkey=pygame.K_RETURN),
            Button(a, (bx + 20, by, 170, 52), cancel_text, self.app.scenes.pop, style="ghost",
                   hotkey=pygame.K_ESCAPE),
        )

    def _confirm(self) -> None:
        self.app.scenes.pop()
        if self.on_confirm is not None:
            self.on_confirm()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.ui.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, theme.PANEL, self.box, border_radius=12)
        pygame.draw.rect(surface, theme.GOLD_DIM, self.box, 2, border_radius=12)
        img = self.app.assets.font(theme.FONT_BODY).render(self.message, True, theme.TEXT)
        surface.blit(img, img.get_rect(center=(self.box.centerx, self.box.top + 70)))
        self.ui.draw(surface)
