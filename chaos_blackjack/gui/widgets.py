"""Minimal widget kit: Label, Button, Toggle and a WidgetGroup container.

Widgets work in logical (canvas) coordinates; App already converts mouse
positions, so widgets never think about window scaling.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.gui import theme

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager


class Widget:
    visible = True

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the event was consumed."""
        return False

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


class Label(Widget):
    def __init__(
        self,
        assets: "AssetManager",
        text: str,
        pos: tuple[int, int],
        *,
        size: int = theme.FONT_BODY,
        color: theme.Color = theme.TEXT,
        anchor: str = "topleft",
        bold: bool = False,
    ) -> None:
        self.assets = assets
        self.text = text
        self.pos = pos
        self.size = size
        self.color = color
        self.anchor = anchor
        self.bold = bold

    def draw(self, surface: pygame.Surface) -> None:
        img = self.assets.font(self.size, self.bold).render(self.text, True, self.color)
        surface.blit(img, img.get_rect(**{self.anchor: self.pos}))


class Button(Widget):
    STYLES = {
        # style: (fill, fill_hover, border, text)
        "primary": ((0x2A, 0x22, 0x10), (0x4A, 0x3C, 0x1C), theme.GOLD, theme.IVORY),
        "chaos": ((0x2A, 0x10, 0x30), (0x48, 0x18, 0x52), theme.CHAOS_MAGENTA, theme.IVORY),
        "ghost": ((0x12, 0x18, 0x1A), (0x22, 0x2C, 0x2E), theme.TEXT_MUTED, theme.TEXT),
    }

    def __init__(
        self,
        assets: "AssetManager",
        rect: pygame.Rect | tuple[int, int, int, int],
        text: str,
        on_click: Callable[[], None] | None = None,
        *,
        style: str = "primary",
        enabled: bool = True,
        hotkey: int | None = None,
        font_size: int = theme.FONT_BUTTON,
        tooltip: str = "",
    ) -> None:
        self.assets = assets
        self.rect = pygame.Rect(rect)
        self.text = text
        self.on_click = on_click
        self.style = style
        self.enabled = enabled
        self.hotkey = hotkey
        self.font_size = font_size
        self.tooltip = tooltip
        self.hovered = False
        self._pressed = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
            return False
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            fire = self._pressed and self.rect.collidepoint(event.pos)
            self._pressed = False
            if fire:
                self.click()
                return True
        if event.type == pygame.KEYDOWN and self.hotkey is not None and event.key == self.hotkey:
            self.click()
            return True
        return False

    def click(self) -> None:
        if self.enabled and self.on_click is not None:
            self.on_click()

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        fill, fill_hover, border, text_color = self.STYLES[self.style]
        if not self.enabled:
            fill, border, text_color = (0x16, 0x1A, 0x1B), (0x3A, 0x40, 0x40), (0x60, 0x66, 0x66)
        elif self.hovered:
            fill = fill_hover
        rect = self.rect.move(0, 2) if self._pressed else self.rect
        pygame.draw.rect(surface, fill, rect, border_radius=10)
        pygame.draw.rect(surface, border, rect, 2, border_radius=10)
        img = self.assets.font(self.font_size).render(self.text, True, text_color)
        surface.blit(img, img.get_rect(center=rect.center))
        if self.hovered and self.tooltip:
            tip = self.assets.font(theme.FONT_SMALL).render(self.tooltip, True, theme.TEXT_MUTED)
            surface.blit(tip, tip.get_rect(midtop=(rect.centerx, rect.bottom + 6)))


class Toggle(Button):
    """Button that flips a boolean; `label(value)` renders its text."""

    def __init__(
        self,
        assets: "AssetManager",
        rect,
        label: Callable[[bool], str],
        value: bool = False,
        on_change: Callable[[bool], None] | None = None,
        **kwargs,
    ) -> None:
        self.label = label
        self.value = value
        self.on_change = on_change
        super().__init__(assets, rect, label(value), self._flip, **kwargs)

    def _flip(self) -> None:
        self.value = not self.value
        self.text = self.label(self.value)
        if self.on_change is not None:
            self.on_change(self.value)


class WidgetGroup(Widget):
    def __init__(self, *widgets: Widget) -> None:
        self.widgets: list[Widget] = list(widgets)

    def add(self, widget: Widget) -> Widget:
        self.widgets.append(widget)
        return widget

    def handle_event(self, event: pygame.event.Event) -> bool:
        consumed = False
        for w in reversed(self.widgets):
            # Mouse motion goes to everyone so hover states stay correct.
            if w.handle_event(event) and event.type != pygame.MOUSEMOTION:
                consumed = True
                break
        return consumed

    def update(self, dt: float) -> None:
        for w in self.widgets:
            w.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        for w in self.widgets:
            if w.visible:
                w.draw(surface)
