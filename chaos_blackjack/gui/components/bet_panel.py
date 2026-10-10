"""Betting panel — click chips to build a bet, then deal.

Left click a chip adds its value, right click removes it. ↑/↓ adjust by 1,
Enter deals. The amount is always clamped to the controller's limits.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.widgets import Button, Widget, WidgetGroup

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

CHIP_VALUES = tuple(theme.CHIP_COLORS)  # (1, 5, 10, 25)
CHIP_PX = 76


class ChipButton(Widget):
    def __init__(self, assets: "AssetManager", value: int, center: tuple[int, int], on_change: Callable[[int], None]) -> None:
        self.assets = assets
        self.value = value
        self.rect = pygame.Rect(0, 0, CHIP_PX, CHIP_PX)
        self.rect.center = center
        self.on_change = on_change
        self.hovered = False
        self.enabled = True

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and self.enabled and self.rect.collidepoint(event.pos):
            if event.button == 1:
                self.on_change(self.value)
                return True
            if event.button == 3:
                self.on_change(-self.value)
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        rect = self.rect.move(0, -6) if self.hovered and self.enabled else self.rect
        img = self.assets.image(f"chip_{self.value}", rect.size)
        if not self.enabled:
            img = img.copy()
            img.set_alpha(90)
        surface.blit(img, rect)
        label = self.assets.font(theme.FONT_BODY, bold=True).render(str(self.value), True, theme.INK)
        surface.blit(label, label.get_rect(center=rect.center))


class BetPanel(WidgetGroup):
    def __init__(
        self,
        assets: "AssetManager",
        center: tuple[int, int],
        on_deal: Callable[[int], None],
        initial: int = 10,
    ) -> None:
        super().__init__()
        self.assets = assets
        self.center = center
        self.on_deal = on_deal
        self.amount = initial
        self.lo, self.hi = 1, 1
        cx, cy = center
        self.chips = [
            ChipButton(assets, v, (cx - 330 + i * (CHIP_PX + 18), cy), self._add)
            for i, v in enumerate(CHIP_VALUES)
        ]
        for chip in self.chips:
            self.add(chip)
        self.add(Button(assets, (cx + 40, cy - 24, 90, 48), "Clear", lambda: self._set(self.lo), style="ghost", font_size=theme.FONT_BODY))
        self.add(Button(assets, (cx + 140, cy - 24, 90, 48), "Max", lambda: self._set(self.hi), style="ghost", font_size=theme.FONT_BODY))
        self.deal_button = self.add(Button(assets, (cx + 240, cy - 28, 140, 56), "Deal", self._deal, hotkey=pygame.K_RETURN))

    def set_limits(self, lo: int, hi: int) -> None:
        self.lo, self.hi = lo, hi
        self._set(self.amount)
        for chip in self.chips:
            chip.enabled = chip.value <= hi

    def _set(self, amount: int) -> None:
        self.amount = max(self.lo, min(self.hi, amount))

    def _add(self, delta: int) -> None:
        self._set(self.amount + delta)

    def _deal(self) -> None:
        self.on_deal(self.amount)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN):
            self._add(1 if event.key == pygame.K_UP else -1)
            return True
        return super().handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        cx, cy = self.center
        font = self.assets.font(theme.FONT_HEADING, bold=True)
        amount = font.render(f"Bet {self.amount}", True, theme.GOLD)
        surface.blit(amount, amount.get_rect(center=(cx, cy - 92)))
        hint = self.assets.font(theme.FONT_SMALL).render(
            f"Range {self.lo}–{self.hi}    left-click add / right-click remove / ↑↓ ±1 / Enter deal", True, theme.TEXT_MUTED,
        )
        surface.blit(hint, hint.get_rect(center=(cx, cy - 58)))
        super().draw(surface)
