"""Onboarding scenes (docs/design/TUTORIAL.md): the practice table and the strategy chart.

The practice table is the table scene on a "tutorial" controller (chaos_blackjack/tutorial): Poker Head
explains each hand in a dialog (before the bet, when the cards are dealt, after the result) and only the
taught button works. After the last hand, or when the player skips, the strategy chart follows; closing it
finishes the tutorial. The chart is also in the Collection.
"""

from __future__ import annotations

import random
from typing import Callable

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import GameController
from chaos_blackjack.app.view import TablePhase
from chaos_blackjack.content.basic_strategy import CELL_LEGEND, DEALER_COLUMNS, HARD, SOFT
from chaos_blackjack.content.builtin_persona import host_persona
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.intro import HostDialog
from chaos_blackjack.gui.components.lobby import MARGIN, draw_backdrop, draw_header
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.scenes.table import RUN_END_DELAY, TableScene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup
from chaos_blackjack.modes import get_mode
from chaos_blackjack.tutorial.lessons import CHART, LESSONS, WELCOME, beats

W, H = LOGICAL_SIZE

# Chart geometry: hard totals on the left, soft totals on the right, the legend below, room for the coach.
CELL_W, CELL_H, LABEL_W = 44, 28, 64
GRID_TOP = 160
TABLE_W = LABEL_W + CELL_W * len(DEALER_COLUMNS)
HARD_X, SOFT_X = MARGIN, W - MARGIN - TABLE_W
LEGEND_Y = GRID_TOP + CELL_H * (len(HARD) + 1) + 16
COACH_BOX = pygame.Rect(0, 0, 820, 190)
COACH_BOX.midbottom = (W // 2, H - 8)
# At the practice table the coach talks beside the cards, over the right panel, so the hands stay visible.
TABLE_COACH_BOX = pygame.Rect(780, 288, W - 16 - 780, 322)

CELL_COLORS = {
    "H": (0xB8, 0x4A, 0x40),    # hit: red
    "S": (0xD9, 0xBC, 0x5A),    # stand: yellow
    "D": (0x4E, 0x9A, 0x5E),    # double: green
    "DS": (0x3F, 0x86, 0x8C),   # double, else stand: teal
    "R": (0xCF, 0xCF, 0xC8),    # surrender: light grey
}
CELL_TEXT = {"H": "H", "S": "S", "D": "D", "DS": "Ds", "R": "R"}


def draw_chart_table(surface: pygame.Surface, assets, x: int, title: str,
                     rows: tuple[tuple[str, tuple[str, ...]], ...]) -> None:
    """One block of the chart: a title, the dealer's up cards as columns, your hands as rows."""
    head = assets.font(theme.FONT_SMALL, bold=True)
    small = assets.font(theme.FONT_TINY, bold=True)
    surface.blit(head.render(title, True, theme.GOLD), (x, GRID_TOP - 30))
    shows = small.render("Dealer shows", True, theme.TEXT_MUTED)
    surface.blit(shows, shows.get_rect(bottomright=(x + TABLE_W, GRID_TOP - 8)))
    corner = small.render("You", True, theme.TEXT_MUTED)
    surface.blit(corner, corner.get_rect(center=(x + LABEL_W // 2, GRID_TOP + CELL_H // 2)))
    for i, col in enumerate(DEALER_COLUMNS):
        cell = pygame.Rect(x + LABEL_W + i * CELL_W, GRID_TOP, CELL_W, CELL_H)
        pygame.draw.rect(surface, theme.DARK, cell)
        label = head.render(col, True, theme.IVORY)
        surface.blit(label, label.get_rect(center=cell.center))
    for r, (name, cells) in enumerate(rows):
        y = GRID_TOP + (r + 1) * CELL_H
        row = pygame.Rect(x, y, LABEL_W, CELL_H)
        pygame.draw.rect(surface, theme.PANEL, row)
        label = head.render(name, True, theme.IVORY)
        surface.blit(label, label.get_rect(center=row.center))
        for i, c in enumerate(cells):
            cell = pygame.Rect(x + LABEL_W + i * CELL_W, y, CELL_W, CELL_H)
            pygame.draw.rect(surface, CELL_COLORS[c], cell)
            pygame.draw.rect(surface, theme.DARK, cell, 1)
            text = head.render(CELL_TEXT[c], True, theme.INK)
            surface.blit(text, text.get_rect(center=cell.center))
    pygame.draw.rect(surface, theme.GOLD_DIM, (x, GRID_TOP, TABLE_W, CELL_H * (len(rows) + 1)), 1)


def draw_legend(surface: pygame.Surface, assets, y: int) -> None:
    font = assets.font(theme.FONT_SMALL)
    widths = [34 + font.size(text)[0] for _, text in CELL_LEGEND]
    x = (W - sum(widths) - 28 * (len(widths) - 1)) // 2
    for (code, text), width in zip(CELL_LEGEND, widths):
        swatch = pygame.Rect(x, y, 26, 22)
        pygame.draw.rect(surface, CELL_COLORS[code], swatch, border_radius=4)
        mark = assets.font(theme.FONT_TINY, bold=True).render(CELL_TEXT[code], True, theme.INK)
        surface.blit(mark, mark.get_rect(center=swatch.center))
        surface.blit(font.render(text, True, theme.IVORY), (x + 34, y + 2))
        x += width + 28


@register_scene("strategy_chart")
class StrategyChartScene(Scene):
    """The basic strategy chart; with `coach`, Poker Head explains it first (the tutorial's last step)."""

    def on_enter(self, coach: bool = False, on_close: Callable[[], None] | None = None, **params) -> None:
        a = self.app.assets
        self.on_close = on_close
        self.closed = False
        self.dialog = (HostDialog(a, beats(CHART), host_persona("poker_head"), finish="Enter to finish",
                                  box=COACH_BOX, shade=False) if coach else None)
        self.ui = WidgetGroup(Button(a, (W - MARGIN - 200, 650, 200, 50), "Done", self.close, style="ghost",
                                     hotkey=pygame.K_ESCAPE, font_size=theme.FONT_BODY), keyboard=True)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.app.scenes.pop()
        if self.on_close is not None:
            self.on_close()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.dialog is not None and not self.dialog.done:
            self.dialog.handle_event(event)
            return
        self.ui.handle_event(event)

    def update(self, dt: float) -> None:
        self.ui.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        draw_backdrop(surface, a, shade=200)
        draw_header(surface, a, "Basic strategy",
                    "The move that loses least for each hand. Dealer stands on all 17s; surrender only as the first move.")
        draw_chart_table(surface, a, HARD_X, "Hard totals (no ace, or an ace counted as 1)", HARD)
        draw_chart_table(surface, a, SOFT_X, "Soft totals (an ace counted as 11)", SOFT)
        draw_legend(surface, a, LEGEND_Y)
        if self.dialog is not None and not self.dialog.done:
            self.dialog.draw(surface)
        else:
            self.ui.draw(surface)


@register_scene("tutorial_table")
class TutorialTableScene(TableScene):
    """Practice hands with Poker Head as a coach; `on_finish` runs when the tutorial is over (or skipped)."""

    def on_enter(self, on_finish: Callable[[], None] | None = None, seed: int | None = None, **params) -> None:
        config = get_mode("tutorial").apply(RunConfig.from_balance(
            self.app.balance, seed=seed if seed is not None else random.randrange(2**30)))
        super().on_enter(controller=GameController(config), intro=False)
        self.on_finish = on_finish
        self.coached: set[tuple] = set()
        self.intro = HostDialog(self.app.assets, beats(WELCOME), self.persona, finish="Enter to begin")

    @property
    def table(self):
        return self.controller.table

    def coach_lines(self) -> tuple[tuple[str, str], ...]:
        """What Poker Head says now, once per moment of each hand."""
        v, table = self.view, self.table
        lesson = table.lesson
        if v.phase == TablePhase.PLAYER_TURN and lesson is not None:
            key = (v.phase, table.played, len(v.player_cards) if lesson.action is None else 0)
            lines = lesson.turn or (("present_card", table.advice()),)
        elif v.phase == TablePhase.BETTING and lesson is not None:
            key, lines = (v.phase, table.played), lesson.before
        elif v.phase == TablePhase.ROUND_OVER and table.played:
            key, lines = (v.phase, table.played), LESSONS[table.played - 1].after
        else:
            return ()
        if key in self.coached:
            return ()
        self.coached.add(key)
        return lines

    def coach(self) -> None:
        if self.dialog() is not None or self.fx.busy or self._busy():
            return
        lines = self.coach_lines()
        if lines:
            self.intro = HostDialog(self.app.assets, beats(lines), self.persona, finish="Enter to continue",
                                    box=TABLE_COACH_BOX, shade=False)

    def handle_event(self, event: pygame.event.Event) -> None:
        if (not self.intro_open() and not self._closed and event.type == pygame.KEYDOWN
                and event.key == pygame.K_ESCAPE):
            self.app.scenes.push("confirm", message="Skip the rest of the practice? The strategy chart comes next.",
                                 confirm_text="Skip", cancel_text="Keep playing", on_confirm=self.to_chart)
            return
        super().handle_event(event)

    def to_chart(self) -> None:
        if self._ending_opened:
            return
        self._ending_opened = True
        self.app.scenes.replace("strategy_chart", coach=True, on_close=self.on_finish)

    def update(self, dt: float) -> None:
        if self.view.phase != TablePhase.RUN_OVER:
            super().update(dt)
            self.coach()
            return
        if self._closed or self._ending_opened:
            return
        self.left.update(dt)
        self.right.update(dt)
        self.fx.update(dt)
        if self.fx.busy:
            return
        self._timer += dt
        if self._timer >= RUN_END_DELAY:
            self.to_chart()


__all__ = ["StrategyChartScene", "TutorialTableScene", "draw_chart_table"]
