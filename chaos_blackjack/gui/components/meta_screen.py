"""Shared presentation for player screens, name entry and settings."""

from __future__ import annotations

from collections.abc import Callable
import sqlite3

import pygame

from chaos_blackjack import meta
from chaos_blackjack.meta.models import MAX_NAME_LENGTH
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import PlayerBadge, back_button, draw_backdrop, draw_header
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup, fit_text, wrap_text


def text(surface, assets, value, pos, *, size=20, color=theme.TEXT, width=None):
    font = assets.font(size)
    value = str(value)
    if width is not None:
        value = fit_text(font, value, width)
    surface.blit(font.render(value, True, color), pos)


def paragraph(surface, assets, value, rect, *, color=theme.TEXT_MUTED, size=18):
    rect = pygame.Rect(rect)
    font = assets.font(size)
    lines = wrap_text(font, str(value), rect.w, max_lines=max(1, rect.h // font.get_linesize()))
    for i, line in enumerate(lines):
        surface.blit(font.render(line, True, color), (rect.x, rect.y + i * font.get_linesize()))


def panel(surface, rect):
    pygame.draw.rect(surface, theme.PANEL, rect, border_radius=14)
    pygame.draw.rect(surface, theme.GOLD_DIM, rect, 1, border_radius=14)


class MetaScreen(Scene):
    title = ""
    subtitle = ""

    def setup(self):
        self.message = ""
        self.leaving = False
        self.ui = WidgetGroup()

    def action(self, fn: Callable):
        """Keep API rejection text visible without changing the screen."""
        try:
            return fn()
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.message = str(exc)
            return None

    def navigate(self, name, **params):
        if not self.leaving:
            self.leaving = True
            self.app.scenes.push(name, **params)

    def handle_event(self, event):
        if not self.leaving:
            self.ui.handle_event(event)

    def on_resume(self, result=None):
        self.leaving = False

    def draw(self, surface):
        draw_backdrop(surface, self.app.assets, shade=205)
        self.draw_header(surface)

    def draw_header(self, surface):
        draw_header(surface, self.app.assets, self.title, self.subtitle)
        player = getattr(self, "player", None)
        if player is not None:
            PlayerBadge(self.app.assets, player, None).draw(surface)
        if self.message:
            paragraph(surface, self.app.assets, self.message, (66, 596, 1148, 40), color=theme.CHAOS_MAGENTA)


@register_scene("meta_name")
class NameDialog(MetaScreen):
    transparent = True

    def on_enter(self, title="Player name", value="", on_submit=None, on_success=None, **params):
        self.setup()
        self.title, self.value = title, value
        self.on_submit, self.on_success = on_submit, on_success
        self.submitted = False
        self.replace_value = bool(value)
        pygame.key.start_text_input()
        self.ui = WidgetGroup(
            Button(self.app.assets, (394, 446, 230, 52), "Save", self.submit, hotkey=pygame.K_RETURN),
            Button(self.app.assets, (654, 446, 230, 52), "Cancel", self.app.scenes.pop,
                   style="ghost", hotkey=pygame.K_ESCAPE),
        )

    def on_exit(self):
        pygame.key.stop_text_input()

    def submit(self):
        if self.submitted:
            return
        result = self.action(lambda: self.on_submit(self.value))
        if result is not None:
            self.submitted = True
            self.app.scenes.pop()
            if self.on_success:
                self.on_success(result)

    def handle_event(self, event):
        if self.submitted:
            return
        if event.type == pygame.TEXTINPUT:
            self.value = (("" if self.replace_value else self.value) + event.text)[:MAX_NAME_LENGTH]
            self.replace_value = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
            self.value = "" if self.replace_value else self.value[:-1]
            self.replace_value = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_a and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
            self.replace_value = True
        else:
            super().handle_event(event)

    def draw(self, surface):
        shade = pygame.Surface((1280, 720), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        surface.blit(shade, (0, 0))
        panel(surface, (350, 205, 580, 325))
        a = self.app.assets
        text(surface, a, self.title, (390, 237), size=30, color=theme.GOLD, width=500)
        box = pygame.Rect(390, 301, 500, 62)
        pygame.draw.rect(surface, theme.FELT, box, border_radius=8)
        pygame.draw.rect(surface, theme.GOLD, box, 2, border_radius=8)
        if self.replace_value:
            pygame.draw.rect(surface, theme.GOLD_DIM, box.inflate(-16, -16), border_radius=4)
        text(surface, a, self.value or "Enter a name", (405, 317), width=460)
        paragraph(surface, a, self.message or f"Up to {MAX_NAME_LENGTH} characters. Enter saves; Esc cancels.",
                  (390, 378, 500, 52), color=theme.CHAOS_MAGENTA if self.message else theme.TEXT_MUTED)
        self.ui.draw(surface)


@register_scene("meta_settings")
class MetaSettings(MetaScreen):
    title = "Settings"
    subtitle = "Sound and display settings apply to every screen."

    def on_enter(self, **params):
        self.setup()
        a = self.app.assets
        self.mute = Button(a, (340, 190, 600, 60), "", self.app.audio.toggle_mute)
        self.ui = WidgetGroup(
            self.mute,
            Button(a, (340, 280, 285, 58), "Volume -", lambda: self.app.adjust_volume(-0.1), key_hint="-"),
            Button(a, (655, 280, 285, 58), "Volume +", lambda: self.app.adjust_volume(0.1), key_hint="+"),
            Button(a, (340, 380, 600, 58), "Toggle fullscreen", self.app.toggle_fullscreen, key_hint="F11"),
            back_button(a, self.app.scenes.pop),
            keyboard=True,
        )

    def draw(self, surface):
        state = "muted" if self.app.audio.muted else f"{self.app.audio.volume:.0%}"
        self.mute.text = f"Sound: {state}"
        super().draw(surface)
        paragraph(surface, self.app.assets, "M mute  ·  +/- volume  ·  F11 fullscreen  ·  F5 reload assets",
                  (340, 480, 600, 60))
        self.ui.draw(surface)
