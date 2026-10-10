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
        role: str = "ui",
    ) -> None:
        self.assets = assets
        self.text = text
        self.pos = pos
        self.size = size
        self.color = color
        self.anchor = anchor
        self.bold = bold
        self.role = role

    def draw(self, surface: pygame.Surface) -> None:
        img = self.assets.font(self.size, self.bold, self.role).render(self.text, True, self.color)
        surface.blit(img, img.get_rect(**{self.anchor: self.pos}))


class Button(Widget):
    STYLES = {
        # style: (fill, fill_hover, border, text)
        "primary": ((0x2A, 0x27, 0x1E), (0x3E, 0x38, 0x29), theme.GOLD, theme.IVORY),
        "chaos": ((0x2A, 0x23, 0x2C), (0x3C, 0x31, 0x3F), theme.CHAOS_MAGENTA, theme.IVORY),
        "ghost": ((0x1C, 0x22, 0x21), (0x29, 0x31, 0x2F), theme.TEXT_MUTED, theme.TEXT),
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
        key_hint: str | None = None,
    ) -> None:
        self.assets = assets
        # None = derive from `hotkey`; "" = no badge.
        self.key_hint = key_name(hotkey) if key_hint is None else key_hint
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
            fill, border, text_color = (0x1A, 0x1F, 0x1E), (0x3A, 0x40, 0x3E), (0x62, 0x68, 0x65)
        elif self.hovered:
            fill = fill_hover
        rect = self.rect.move(0, 2) if self._pressed else self.rect
        pygame.draw.rect(surface, fill, rect, border_radius=10)
        pygame.draw.rect(surface, border, rect, 2, border_radius=10)
        img = self.assets.font(self.font_size).render(self.text, True, text_color)
        if self.key_hint:
            cap = self.assets.font(theme.FONT_TINY, bold=True).render(self.key_hint, True, text_color)
            cap_rect = pygame.Rect(0, 0, max(22, cap.get_width() + 10), 22)
            gap = 10
            total = img.get_width() + gap + cap_rect.w
            if total <= rect.w - 16:
                x = rect.centerx - total // 2
                surface.blit(img, img.get_rect(midleft=(x, rect.centery)))
                cap_rect.midleft = (x + img.get_width() + gap, rect.centery)
                pygame.draw.rect(surface, border, cap_rect, 1, border_radius=5)
                surface.blit(cap, cap.get_rect(center=cap_rect.center))
            else:
                surface.blit(img, img.get_rect(center=rect.center))
        else:
            surface.blit(img, img.get_rect(center=rect.center))
        if self.hovered and self.tooltip:
            tip = self.assets.font(theme.FONT_SMALL).render(self.tooltip, True, theme.TEXT_MUTED)
            surface.blit(tip, tip.get_rect(midtop=(rect.centerx, rect.bottom + 6)))


_KEY_NAMES = {"return": "Enter", "escape": "Esc", "space": "Space"}


def key_name(key: int | None) -> str:
    """Short label for a hotkey badge ("H", "Enter", ...)."""
    if key is None:
        return ""
    name = pygame.key.name(key)
    return _KEY_NAMES.get(name, name.upper() if len(name) == 1 else name.title())


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


# ------------------------------------------------------------ draw helpers


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, *, alpha: int = theme.PANEL_ALPHA) -> None:
    """Translucent rounded panel with a thin old-gold edge."""
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (*theme.PANEL, alpha), panel.get_rect(), border_radius=14)
    surface.blit(panel, rect)
    pygame.draw.rect(surface, theme.GOLD_DIM, rect, 1, border_radius=14)


def draw_heading(surface: pygame.Surface, assets: "AssetManager", text: str, pos: tuple[int, int], width: int) -> int:
    """Small-caps section heading with a rule line; returns the y below it."""
    img = assets.font(theme.FONT_TINY, bold=True).render(text.upper(), True, theme.GOLD_DIM)
    surface.blit(img, pos)
    y = pos[1] + img.get_height() + 4
    pygame.draw.line(surface, theme.GOLD_DIM, (pos[0], y), (pos[0] + width, y), 1)
    return y + 8


def fit_text(font: pygame.font.Font, text: str, max_width: int) -> str:
    """Trim `text` with an ellipsis so it renders within `max_width`."""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "…")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap_text(font: pygame.font.Font, text: str, max_width: int, max_lines: int = 99) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.size(trial)[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_text(font, lines[-1] + " …", max_width)
    return [fit_text(font, line, max_width) for line in lines]


def draw_tooltip(surface: pygame.Surface, assets: "AssetManager", text: str, anchor: tuple[int, int]) -> None:
    """Wrapped tooltip box placed near `anchor`, kept on screen."""
    font = assets.font(theme.FONT_SMALL)
    lines = wrap_text(font, text, 260)
    pad = 10
    lh = font.get_linesize()
    w = max(font.size(line)[0] for line in lines) + pad * 2
    h = lh * len(lines) + pad * 2
    rect = pygame.Rect(anchor[0], anchor[1], w, h)
    rect.clamp_ip(surface.get_rect().inflate(-8, -8))
    pygame.draw.rect(surface, theme.DARK, rect, border_radius=8)
    pygame.draw.rect(surface, theme.GOLD_DIM, rect, 1, border_radius=8)
    for i, line in enumerate(lines):
        surface.blit(font.render(line, True, theme.TEXT), (rect.x + pad, rect.y + pad + i * lh))
