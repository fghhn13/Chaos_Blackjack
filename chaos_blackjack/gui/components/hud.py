"""Heads-up display pieces: top status bar and the event feed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.app.view import GameView
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Widget

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

W, H = LOGICAL_SIZE
BAR_H = 56


def draw_status_bar(surface: pygame.Surface, assets: "AssetManager", v: GameView) -> None:
    bar = pygame.Surface((W, BAR_H), pygame.SRCALPHA)
    bar.fill((*theme.DARK, 210))
    surface.blit(bar, (0, 0))
    pygame.draw.line(surface, theme.GOLD_DIM, (0, BAR_H), (W, BAR_H), 1)

    body = assets.font(theme.FONT_BODY)
    small = assets.font(theme.FONT_SMALL)

    # Bankroll progress toward the target.
    x, y, pw, ph = 24, 14, 300, 28
    pygame.draw.rect(surface, theme.PANEL, (x, y, pw, ph), border_radius=6)
    k = max(0.0, min(1.0, v.money / max(1, v.target_money)))
    if k > 0:
        pygame.draw.rect(surface, theme.GOLD_DIM, (x, y, int(pw * k), ph), border_radius=6)
    pygame.draw.rect(surface, theme.GOLD, (x, y, pw, ph), 1, border_radius=6)
    money = body.render(f"Bankroll {v.money} / {v.target_money}", True, theme.IVORY)
    surface.blit(money, money.get_rect(center=(x + pw // 2, y + ph // 2)))

    parts = [f"Round {v.round}", f"Bet {v.current_bet if v.player_cards else '-'}",
             f"Streak {v.win_streak}/{v.reward_streak}"]
    if v.chaos_enabled:
        parts.append(f"Chaos budget {v.chaos_budget}")
    text = body.render("    ".join(parts), True, theme.TEXT)
    surface.blit(text, (x + pw + 32, y + 2))

    hint = small.render("Esc  menu", True, theme.TEXT_MUTED)
    surface.blit(hint, hint.get_rect(midright=(W - 20, BAR_H // 2)))


@dataclass
class _FeedLine:
    text: str
    color: theme.Color
    age: float = 0.0


class EventFeed(Widget):
    """Bottom-left log of recent events; lines fade out after `ttl` seconds."""

    def __init__(self, assets: "AssetManager", anchor: tuple[int, int], *, max_lines: int = 6, ttl: float = 8.0) -> None:
        self.assets = assets
        self.anchor = anchor  # bottom-left of the newest line
        self.max_lines = max_lines
        self.ttl = ttl
        self.lines: list[_FeedLine] = []

    def push(self, text: str, color: theme.Color = theme.TEXT) -> None:
        self.lines.append(_FeedLine(text, color))
        del self.lines[:-self.max_lines]

    def clear(self) -> None:
        self.lines.clear()

    def update(self, dt: float) -> None:
        for line in self.lines:
            line.age += dt
        self.lines = [l for l in self.lines if l.age < self.ttl]

    def draw(self, surface: pygame.Surface) -> None:
        font = self.assets.font(theme.FONT_SMALL)
        x, y = self.anchor
        for line in reversed(self.lines):
            img = font.render(line.text, True, line.color)
            fade = min(1.0, (self.ttl - line.age) / 1.5)
            img.set_alpha(int(255 * fade))
            y -= img.get_height() + 4
            surface.blit(img, (x, y))
