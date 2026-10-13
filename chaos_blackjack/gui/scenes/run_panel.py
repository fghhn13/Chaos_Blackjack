"""Run panel — the table's full information, one tab per group of parts.

    app.scenes.push("run_panel", controller=ctrl, layout=layout, tab="log", on_change=callback)

Tabs and their parts come from the table's layout (app/layout.py); each part
is drawn from its widgets in the `full` variant, so a new mechanic shows up
here without GUI code. Clickable widgets send their `Act` to
`controller.perform`; `on_change` lets the table refresh afterwards.
Tab / Esc close, Left / Right or a tab's letter switch tabs, the wheel scrolls.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.layout import Layout, split_entry
from chaos_blackjack.app.parts import PartContext, build_part
from chaos_blackjack.app.widgets import Act
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.widget_view import WidgetView
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import BAD
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE
BOX = pygame.Rect(0, 0, W - 200, H - 90)
BOX.center = (W // 2, H // 2)
TAB_H = 40


@register_scene("run_panel")
class RunPanelScene(Scene):
    transparent = True

    def on_enter(self, controller: GameController | None = None, layout: Layout | None = None, tab: str = "",
                 on_change: Callable[[], None] | None = None, **params) -> None:
        assert controller is not None and layout is not None
        self.controller, self.layout, self.on_change = controller, layout, on_change
        self.tabs = layout.panel
        self.index = next((i for i, t in enumerate(self.tabs) if t.id == tab), 0)
        self.scroll = 0
        self.message: tuple[str, theme.Color] | None = None
        self.state: dict = {}  # per-panel widget state (e.g. the log filter)
        a = self.app.assets
        self.tab_buttons: list[Button] = []
        x = BOX.x + 24
        for i, t in enumerate(self.tabs):
            label = t.label + (f"  {t.hotkey.upper()}" if t.hotkey else "")
            w = a.font(theme.FONT_BODY).size(label)[0] + 36
            self.tab_buttons.append(Button(a, (x, BOX.y + 18, w, TAB_H), label, self._chooser(i),
                                           style="ghost", font_size=theme.FONT_BODY))
            x += w + 8
        self.close = Button(a, (BOX.right - 150, BOX.y + 18, 126, TAB_H), "Close", self.app.scenes.pop,
                            style="ghost", hotkey=pygame.K_ESCAPE, font_size=theme.FONT_BODY)
        self.ui = WidgetGroup(*self.tab_buttons, self.close)
        self._build()

    @property
    def content(self) -> pygame.Rect:
        top = BOX.y + 18 + TAB_H + 16
        return pygame.Rect(BOX.x + 32, top, BOX.w - 64, BOX.bottom - 24 - top)

    def _chooser(self, index: int) -> Callable[[], None]:
        return lambda: self.select(index)

    def select(self, index: int) -> None:
        self.index = index % len(self.tabs)
        self.scroll = 0
        self.message = None
        self._build()

    @property
    def tab(self):
        return self.tabs[self.index]

    def _build(self) -> None:
        ctx = PartContext(self.controller, self.controller.view())
        widgets = []
        for entry in self.tab.parts:
            part, variant = split_entry(entry, "full")
            widgets.extend(build_part(part, ctx, variant))
        self.view = WidgetView(self.app.assets, tuple(widgets), self.content.w, full=True, on_act=self._act, state=self.state)
        for i, b in enumerate(self.tab_buttons):
            b.style = "primary" if i == self.index else "ghost"

    def _act(self, act: Act) -> None:
        if act.id == "gui:panel":
            target = next((i for i, t in enumerate(self.tabs) if t.id == act.arg), None)
            if target is not None:
                self.select(target)
            return
        try:
            result = self.controller.perform(act.id, act.arg)
            ok = getattr(result, "ok", True)
            text = getattr(result, "message", "") or "Done."
            self.message = (text, theme.GOLD if ok else BAD)
        except ActionError as e:
            self.message = (str(e), BAD)
        if self.on_change is not None:
            self.on_change()
        if self.controller.view().choice is not None:  # e.g. an item asks for its target
            self.message = None
            self.app.scenes.push("choice", controller=self.controller, on_change=self._choice_changed)
        self._build()

    def _choice_changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
        self._build()

    def on_resume(self, result=None) -> None:
        self._build()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self.app.scenes.pop()
                return
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.select(self.index + (1 if event.key == pygame.K_RIGHT else -1))
                return
            letter = pygame.key.name(event.key)
            hit = next((i for i, t in enumerate(self.tabs) if t.hotkey and t.hotkey == letter), None)
            if hit is not None:
                self.select(hit)
                return
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_by(-event.y * 48)
            return
        if self.ui.handle_event(event):
            return
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP) and hasattr(event, "pos"):
            if event.type == pygame.MOUSEBUTTONUP and not self.content.collidepoint(event.pos):
                return
            self.view.handle_event(event)

    def _scroll_by(self, dy: int) -> None:
        overflow = max(0, self.view.measure() - self.content.h)
        self.scroll = max(0, min(overflow, self.scroll + dy))

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, theme.PANEL, BOX, border_radius=14)
        pygame.draw.rect(surface, theme.GOLD_DIM, BOX, 2, border_radius=14)
        self.ui.draw(surface)
        area = self.content
        canvas = pygame.Surface(area.size, pygame.SRCALPHA)
        total = self.view.draw(canvas, (0, -self.scroll), offset=area.topleft, clip=area)
        surface.blit(canvas, area)
        if total > area.h:  # scroll bar
            k = area.h / total
            bar = pygame.Rect(area.right + 10, area.y + round(self.scroll * k), 4, max(24, round(area.h * k)))
            pygame.draw.rect(surface, theme.GOLD_DIM, bar, border_radius=2)
        hint = "Tab / Esc close  ·  Left / Right switch tabs  ·  wheel scrolls"
        if self.message is not None:
            text, color = self.message
        else:
            text, color = hint, theme.TEXT_MUTED
        img = a.font(theme.FONT_TINY).render(text, True, color)
        surface.blit(img, img.get_rect(bottomleft=(BOX.x + 32, BOX.bottom - 6)))
        self.view.draw_overlay(surface)
