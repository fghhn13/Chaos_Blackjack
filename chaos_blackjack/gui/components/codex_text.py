"""Clipped text for codex cards, captions and scrollable reference details."""

import pygame

from chaos_blackjack.gui import theme


def wrap_text(text: str, font, width: int) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and font.size(candidate)[0] > width:
                lines.append(line)
                line = ""
            for character in word:
                candidate = line + character
                if line and font.size(candidate)[0] > width:
                    lines.append(line)
                    line = ""
                line += character
            line += " "
        lines.append(line.rstrip())
    return lines


def draw_text(surface, text, font, rect, color=theme.TEXT, *, offset=0, centered=False) -> int:
    rect = pygame.Rect(rect)
    lines = wrap_text(text, font, rect.w)
    height = font.get_linesize() + 4
    old_clip = surface.get_clip()
    surface.set_clip(old_clip.clip(rect))
    for index, line in enumerate(lines):
        image = font.render(line, True, color)
        at = image.get_rect(topleft=(rect.x, rect.y + index * height - offset))
        if centered:
            at.centerx = rect.centerx
        surface.blit(image, at)
    surface.set_clip(old_clip)
    return len(lines) * height
