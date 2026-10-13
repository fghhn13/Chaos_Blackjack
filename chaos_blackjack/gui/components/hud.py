"""Heads-up display pieces: top status bar and the event feed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.app.view import GameView
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Widget, fit_text

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

W, H = LOGICAL_SIZE
BAR_H = 48
GAIN = (0x9C, 0xC2, 0x96)  # bankroll text while it rolls up / down
LOSS = (0xD0, 0x7C, 0x70)


def draw_status_bar(surface: pygame.Surface, assets: "AssetManager", v: GameView, *, money: int | None = None) -> None:
    """`money` overrides the bankroll shown (it rolls toward `v.money` while animating)."""
    shown = v.money if money is None else money
    bar = pygame.Surface((W, BAR_H), pygame.SRCALPHA)
    bar.fill((*theme.DARK, 225))
    surface.blit(bar, (0, 0))
    pygame.draw.line(surface, theme.GOLD_DIM, (0, BAR_H), (W, BAR_H), 1)

    body = assets.font(theme.FONT_BODY)
    small = assets.font(theme.FONT_SMALL)
    tiny = assets.font(theme.FONT_TINY, bold=True)

    # Bankroll progress toward the target, aligned with the left column.
    x, y, pw, ph = 16, 10, 240, 28
    pygame.draw.rect(surface, theme.PANEL, (x, y, pw, ph), border_radius=6)
    # A table without a chip target (J-54's capture protocol) shows the bankroll alone.
    k = max(0.0, min(1.0, shown / max(1, v.target_money))) if v.target_money > 0 else 0.0
    if k > 0:
        pygame.draw.rect(surface, theme.GOLD_DIM, (x, y, max(12, int(pw * k)), ph), border_radius=6)
    pygame.draw.rect(surface, theme.GOLD, (x, y, pw, ph), 1, border_radius=6)
    color = theme.IVORY if shown == v.money else (GAIN if shown < v.money else LOSS)
    money = body.render(f"{shown} / {v.target_money}" if v.target_money > 0 else f"{shown}", True, color)
    surface.blit(money, money.get_rect(center=(x + pw // 2, y + ph // 2)))
    surface.blit(tiny.render("BANKROLL", True, theme.GOLD_DIM), (x + pw + 12, y + 7))

    bet = v.current_bet if v.player_cards else "-"
    fee = f"     Fee {v.fee}" if v.fee else ""
    mid = body.render(f"Round {v.round}     Bet {bet}{fee}", True, theme.TEXT)
    surface.blit(mid, mid.get_rect(center=(W // 2, BAR_H // 2)))

    hint = small.render("Esc  menu", True, theme.TEXT_MUTED)
    hint_rect = hint.get_rect(midright=(W - 20, BAR_H // 2))
    surface.blit(hint, hint_rect)

    if v.chaos_enabled:
        # Remaining chaos budget as pips, right-aligned before the menu hint.
        n = max(0, v.chaos_budget)
        right = hint_rect.left - 32
        for i in range(n):
            c = (right - i * 16, BAR_H // 2)
            pygame.draw.polygon(surface, theme.CHAOS_MAGENTA,
                                [(c[0], c[1] - 6), (c[0] + 5, c[1]), (c[0], c[1] + 6), (c[0] - 5, c[1])])
        label = tiny.render("CHAOS" if n else "CHAOS SPENT", True, theme.CHAOS_PURPLE)
        surface.blit(label, label.get_rect(midright=(right - max(0, n - 1) * 16 - 14, BAR_H // 2)))


@dataclass
class _FeedLine:
    text: str
    color: theme.Color
    age: float = 0.0


class EventFeed(Widget):
    """Bottom-left log of recent events; lines fade out after `ttl` seconds."""

    def __init__(
        self,
        assets: "AssetManager",
        anchor: tuple[int, int],
        *,
        max_lines: int = 6,
        ttl: float = 8.0,
        max_width: int | None = None,
        align_top: bool = False,
    ) -> None:
        self.assets = assets
        self.max_width = max_width
        self.align_top = align_top  # True: anchor is the top-left, oldest line first
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
        if self.align_top:
            for line in self.lines[-self.max_lines:]:
                img = self._render(font, line)
                surface.blit(img, (x, y))
                y += img.get_height() + 4
            return
        for line in reversed(self.lines[-self.max_lines:]):
            img = self._render(font, line)
            y -= img.get_height() + 4
            surface.blit(img, (x, y))

    def _render(self, font: pygame.font.Font, line: _FeedLine) -> pygame.Surface:
        text = fit_text(font, line.text, self.max_width) if self.max_width else line.text
        img = font.render(text, True, line.color)
        fade = min(1.0, (self.ttl - line.age) / 1.5)
        img.set_alpha(int(255 * fade))
        return img
