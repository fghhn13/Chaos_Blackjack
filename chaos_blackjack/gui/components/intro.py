"""The mode's host talks at the table: before the first round of a new run,
and when the run ends (docs/design/AI_MODES.md §3).

Shows the host's portrait and name with one beat at a time; every beat has
its own expression (a Poker Head portrait, or a drawn house-AI face). Enter,
Space or a click advances; Esc skips the rest. While it is open it takes
every input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.content.host_script import HostLine
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.chaos_panel import mood_face
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Widget, wrap_text

if TYPE_CHECKING:
    from chaos_blackjack.content.ai_profile import Persona
    from chaos_blackjack.gui.assets import AssetManager

W, H = LOGICAL_SIZE
BOX = pygame.Rect(0, 0, 820, 210)
BOX.midbottom = (W // 2, H - 70)
PORTRAIT = 170


class HostDialog(Widget):
    def __init__(self, assets: "AssetManager", beats: list[HostLine], persona: "Persona | None", *,
                 finish: str = "Enter to start", box: pygame.Rect | None = None, shade: bool = True) -> None:
        self.assets = assets
        self.box = box or BOX       # where the box sits (e.g. below a chart it talks about)
        self.shade = shade          # dim the screen behind it
        self.beats = [b for b in beats if b.text]
        self.index = 0
        self.persona = persona
        self.name = persona.name if persona else "Chaos AI"
        self.finish = finish

    @property
    def lines(self) -> list[str]:
        return [b.text for b in self.beats]

    @property
    def done(self) -> bool:
        return self.index >= len(self.beats)

    @property
    def portrait(self) -> str:
        mood = self.beats[min(self.index, len(self.beats) - 1)].mood if self.beats else ""
        if self.persona is not None:
            return self.persona.asset_id(mood)  # unknown moods fall back to the default expression
        return mood_face(self.assets, mood or "calm")

    def advance(self) -> None:
        self.index += 1

    def skip(self) -> None:
        self.index = len(self.beats)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if self.done:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.skip()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.advance()
        elif event.type == pygame.MOUSEBUTTONUP and getattr(event, "button", 1) == 1:
            self.advance()
        return True  # nothing else reacts while the host is talking

    def fit(self, text: str, width: int, height: int) -> tuple[pygame.font.Font, list[str]]:
        """The largest body font whose wrapped lines of `text` fit `width` x `height` (the smallest otherwise)."""
        for size in (theme.FONT_BUTTON, theme.FONT_BODY, theme.FONT_SMALL + 2):
            font = self.assets.font(size)
            lines = wrap_text(font, text, width)
            if len(lines) * font.get_linesize() <= height:
                return font, lines
        rows = max(1, height // font.get_linesize())
        return font, wrap_text(font, text, width, max_lines=rows)

    @property
    def compact(self) -> bool:
        """A narrow box (e.g. beside the cards): a small portrait above the text."""
        return self.box.w < 600

    def draw(self, surface: pygame.Surface) -> None:
        if self.done:
            return
        a = self.assets
        if self.shade:
            shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
            shade.fill((0x0E, 0x11, 0x10, 170))
            surface.blit(shade, (0, 0))
        box = self.box
        pygame.draw.rect(surface, theme.PANEL, box, border_radius=16)
        pygame.draw.rect(surface, theme.CHAOS_MAGENTA, box, 2, border_radius=16)
        name = a.font(theme.FONT_BUTTON, bold=True).render(self.name, True, theme.GOLD)
        if self.compact:
            size = 96
            portrait = a.image_fit(self.portrait, (size, size))
            surface.blit(portrait, (box.x + 18, box.y + 16))
            surface.blit(name, name.get_rect(midleft=(box.x + size + 34, box.y + 16 + size // 2)))
            x, y = box.x + 24, box.y + size + 28
        else:
            portrait = a.image_fit(self.portrait, (PORTRAIT, PORTRAIT))
            surface.blit(portrait, portrait.get_rect(center=(box.x + 24 + PORTRAIT // 2, box.centery)))
            x, y = box.x + PORTRAIT + 48, box.y + 66
            surface.blit(name, (x, box.y + 24))
        body, lines = self.fit(self.beats[self.index].text, box.right - 28 - x, box.bottom - 40 - y)
        for line in lines:
            surface.blit(body.render(line, True, theme.IVORY), (x, y))
            y += body.get_linesize()
        for i in range(len(self.beats)):
            pygame.draw.circle(surface, theme.GOLD if i <= self.index else theme.FELT_LIGHT,
                               (x + 6 + i * 18, box.bottom - 24), 5)
        last = self.index == len(self.beats) - 1
        hint = a.font(theme.FONT_SMALL).render(
            (self.finish if last else "Enter to continue") + "  ·  Esc to skip", True, theme.TEXT_MUTED)
        surface.blit(hint, hint.get_rect(bottomright=(box.right - 28, box.bottom - 14)))
