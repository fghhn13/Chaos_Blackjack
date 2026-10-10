"""Main menu."""

from __future__ import annotations

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.chaos_panel import mood_face
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, Label, Toggle, WidgetGroup

W, H = LOGICAL_SIZE


@register_scene("menu")
class MainMenuScene(Scene):
    def on_enter(self, **params) -> None:
        a = self.app.assets
        x, y, bw, bh, gap = 120, 300, 320, 56, 16

        def row(i: int) -> tuple[int, int, int, int]:
            return (x, y + i * (bh + gap), bw, bh)

        self.ui = WidgetGroup(
            Label(a, "Chaos Blackjack", (x, 150), size=theme.FONT_TITLE, color=theme.GOLD, role="display"),
            Label(a, "Rules bend. The house cheats.", (x + 4, 232), size=theme.FONT_HEADING - 8, color=theme.CHAOS_MAGENTA),
            Button(a, row(0), "New Game", lambda: self.app.scenes.push("table"), hotkey=pygame.K_RETURN),
            Button(a, row(1), "Load Game", enabled=False, style="ghost", tooltip="Coming in phase 4"),
            Toggle(
                a, row(2),
                lambda on: f"Chaos Mode: {'ON' if on else 'OFF'}",
                value=self.app.prefs.enable_chaos,
                on_change=self._set_chaos,
                style="chaos",
            ),
            Button(a, row(3), "Asset Gallery", lambda: self.app.scenes.push("gallery"), style="ghost"),
            Button(a, row(4), "Quit", self.app.quit, style="ghost", hotkey=pygame.K_ESCAPE),
        )

    def _set_chaos(self, on: bool) -> None:
        self.app.prefs.enable_chaos = on

    def handle_event(self, event: pygame.event.Event) -> None:
        self.ui.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        surface.blit(a.image("menu_background", LOGICAL_SIZE), (0, 0))
        face = mood_face(a, "smug" if self.app.prefs.enable_chaos else "calm")
        portrait = a.image_fit(face, (420, 420))
        surface.blit(portrait, portrait.get_rect(center=(int(W * 0.74), int(H * 0.55))))
        self.ui.draw(surface)
        hint = a.font(theme.FONT_SMALL).render("F11 fullscreen   F5 reload assets", True, theme.TEXT_MUTED)
        surface.blit(hint, hint.get_rect(bottomright=(W - 20, H - 14)))
