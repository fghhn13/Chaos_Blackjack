"""Run ending — victory or bankruptcy."""

from __future__ import annotations

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import run_end_text
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE


@register_scene("ending")
class EndingScene(Scene):
    def on_enter(self, kind: str = "defeat", money: int = 0, rounds: int = 0, **params) -> None:
        self.kind = kind
        self.money = money
        self.rounds = rounds
        a = self.app.assets
        self.ui = WidgetGroup(
            Button(a, (W // 2 - 230, H - 150, 210, 58), "Play Again", lambda: self.app.scenes.reset("table"),
                   hotkey=pygame.K_RETURN),
            Button(a, (W // 2 + 20, H - 150, 210, 58), "Main Menu", lambda: self.app.scenes.reset("menu"),
                   style="ghost", hotkey=pygame.K_ESCAPE),
        )

    def handle_event(self, event: pygame.event.Event) -> None:
        self.ui.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        bg = "ending_victory" if self.kind == "victory" else "ending_bankrupt"
        surface.blit(a.image(bg, LOGICAL_SIZE), (0, 0))
        band = pygame.Surface((W, 150), pygame.SRCALPHA)
        band.fill((0, 0, 0, 150))
        surface.blit(band, (0, H - 345))
        head, sub = run_end_text(self.kind)
        color = theme.GOLD if self.kind == "victory" else theme.IVORY
        h = a.font(theme.FONT_TITLE, bold=True).render(head, True, color)
        surface.blit(h, h.get_rect(center=(W // 2, H - 290)))
        s = a.font(theme.FONT_BODY).render(f"{sub}    Final bankroll {self.money}    Rounds {self.rounds}", True, theme.TEXT)
        surface.blit(s, s.get_rect(center=(W // 2, H - 228)))
        self.ui.draw(surface)
