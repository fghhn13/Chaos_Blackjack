"""Codex gallery and detail scenes; providers own the content and demos."""

from __future__ import annotations

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex import CodexEntry, codex_entries, codex_kinds, run_demo
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.codex_demo import CodexDemo
from chaos_blackjack.gui.components.codex_text import draw_text, wrap_text
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE
PAGE_SIZE = 10
DEMO_RECT = pygame.Rect(40, 110, 760, 510)
TEXT_PANEL = pygame.Rect(820, 110, W - 860, 510)
TEXT_RECT = TEXT_PANEL.inflate(-40, -40)


@register_scene("codex")
class CodexScene(Scene):
    def on_enter(self, config: RunConfig | None = None, kind: str | None = None, **params):
        self.config = config if config is not None else self.app.run_config
        self.kinds = codex_kinds()
        self.current = kind if kind in {k.id for k in self.kinds} else self.kinds[0].id
        self.page = 0
        self.tabs = []
        assets = self.app.assets
        x = 40
        for k in self.kinds:
            width = max(140, assets.font(theme.FONT_BODY).size(k.label)[0] + 32)
            self.tabs.append(Button(assets, (x, 84, width, 42), k.label,
                                    lambda key=k.id: self._select(key), style="ghost", font_size=20))
            x += width + 10
        self.previous = Button(assets, (40, H - 68, 144, 40), "Previous", lambda: self._page(-1),
                               style="ghost", hotkey=pygame.K_LEFT, font_size=18)
        self.next = Button(assets, (198, H - 68, 144, 40), "Next", lambda: self._page(1),
                           style="ghost", hotkey=pygame.K_RIGHT, font_size=18)
        self.ui = WidgetGroup(*self.tabs, self.previous, self.next,
            Button(assets, (W - 160, 24, 120, 42), "Back", self.app.scenes.pop,
                   style="ghost", hotkey=pygame.K_ESCAPE, font_size=20))
        self._select(self.current)

    def _select(self, kind):
        self.current = kind
        self.page = 0
        self.entries = codex_entries(kind, self.config)
        for k, tab in zip(self.kinds, self.tabs):
            tab.style = "primary" if k.id == kind else "ghost"
        self._layout()

    def _page(self, delta):
        self.page = max(0, min((len(self.entries) - 1) // PAGE_SIZE, self.page + delta))
        self._layout()

    def _layout(self):
        self.tiles = []
        for index, entry in enumerate(self.entries[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]):
            row, column = divmod(index, 5)
            self.tiles.append((pygame.Rect(40 + column * 242, 158 + row * 212, 224, 194), entry))
        self.previous.enabled = self.page > 0
        self.next.enabled = (self.page + 1) * PAGE_SIZE < len(self.entries)

    def handle_event(self, event):
        if self.ui.handle_event(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            index = next(i for i, k in enumerate(self.kinds) if k.id == self.current)
            delta = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self._select(self.kinds[(index + delta) % len(self.kinds)].id)
        elif event.type == pygame.MOUSEWHEEL:
            self._page(-event.y)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, entry in self.tiles:
                if rect.collidepoint(event.pos):
                    self.app.scenes.push("codex_detail", entry=entry, config=self.config)
                    return

    def draw(self, surface):
        assets = self.app.assets
        surface.fill(theme.DARK)
        draw_text(surface, "Codex", assets.font(theme.FONT_HEADING, role="display"), (40, 24, 800, 48), theme.GOLD)
        draw_text(surface, "Explore the rules, items and opponents at your table.", assets.font(18),
                  (238, 36, 800, 32), theme.TEXT_MUTED)
        self.ui.draw(surface)
        mouse = self.app.mouse_pos()
        hovered = None
        for rect, entry in self.tiles:
            selected = rect.collidepoint(mouse)
            pygame.draw.rect(surface, theme.PANEL, rect, border_radius=10)
            pygame.draw.rect(surface, theme.GOLD if selected else theme.FELT_LIGHT, rect, 2, border_radius=10)
            icon = assets.image_fit(entry.icon, (112, 112))
            surface.blit(icon, icon.get_rect(center=(rect.centerx, rect.y + 70)))
            draw_text(surface, entry.name, assets.font(20), (rect.x + 12, rect.y + 134, rect.w - 24, 56), centered=True)
            if selected:
                hovered = entry
        footer = hovered.summary if hovered else f"{len(self.entries)} entries    Tab: switch category    Click an entry to explore"
        draw_text(surface, footer, assets.font(16), (370, H - 66, W - 410, 48), theme.TEXT_MUTED)


@register_scene("codex_detail")
class CodexDetailScene(Scene):
    def on_enter(self, entry: CodexEntry, config: RunConfig | None = None, **params):
        self.entry = entry
        self.config = config if config is not None else self.app.run_config
        self.detail = entry.detail(self.config)
        self.text_offset = 0
        self.demo_error = ""
        frames = []
        if entry.demo is not None:
            try:
                frames = run_demo(entry.demo, self.config)
            except ValueError:
                self.demo_error = "This demonstration is unavailable with the current table settings."
        self.demo = CodexDemo(self.app.assets, frames)
        a = self.app.assets
        self.play = Button(a, (40, 640, 148, 44), "Pause", self.demo.toggle, hotkey=pygame.K_SPACE, font_size=18)
        self.replay = Button(a, (202, 640, 138, 44), "Replay", self.demo.replay, hotkey=pygame.K_r, font_size=18)
        self.previous = Button(a, (354, 640, 144, 44), "Previous", lambda: self.demo.step(-1),
                               hotkey=pygame.K_LEFT, style="ghost", font_size=18)
        self.next = Button(a, (512, 640, 124, 44), "Next", lambda: self.demo.step(1),
                           hotkey=pygame.K_RIGHT, style="ghost", font_size=18)
        self.ui = WidgetGroup(self.play, self.replay, self.previous, self.next,
            Button(a, (W - 160, 24, 120, 42), "Back", self.app.scenes.pop,
                   hotkey=pygame.K_ESCAPE, style="ghost", font_size=20))
        self._controls()

    def _controls(self):
        available = bool(self.demo.frames)
        self.play.enabled = self.replay.enabled = available
        self.previous.enabled = available and self.demo.index > 0
        self.next.enabled = available and self.demo.index < len(self.demo.frames) - 1
        self.play.text = "Pause" if self.demo.playing else "Play"

    def _scroll_text(self, delta):
        lines = wrap_text(self.detail, self.app.assets.font(theme.FONT_BODY), TEXT_RECT.w)
        height = len(lines) * (self.app.assets.font(theme.FONT_BODY).get_linesize() + 4)
        self.text_offset = max(0, min(max(0, height - TEXT_RECT.h), self.text_offset + delta))

    def handle_event(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_text(-event.y * 48)
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            self._scroll_text(-240 if event.key == pygame.K_PAGEUP else 240)
        else:
            self.ui.handle_event(event)
        self._controls()

    def update(self, dt):
        self.demo.update(dt)
        self._controls()

    def draw(self, surface):
        a = self.app.assets
        surface.fill(theme.DARK)
        icon = a.image_fit(self.entry.icon, (52, 52))
        surface.blit(icon, icon.get_rect(center=(66, 50)))
        draw_text(surface, self.entry.name, a.font(theme.FONT_HEADING, role="display"), (110, 24, W - 310, 50), theme.GOLD)
        pygame.draw.rect(surface, theme.PANEL, TEXT_PANEL, border_radius=10)
        draw_text(surface, self.detail, a.font(theme.FONT_BODY), TEXT_RECT, offset=self.text_offset)
        draw_text(surface, "Scroll or PgUp/PgDn for more", a.font(14), (TEXT_PANEL.x, 624, TEXT_PANEL.w, 22), theme.TEXT_MUTED)
        if self.demo.frames:
            self.demo.draw(surface, DEMO_RECT)
            draw_text(surface, f"{self.demo.index + 1} / {len(self.demo.frames)}", a.font(16), (668, 652, 120, 28), theme.TEXT_MUTED)
        else:
            pygame.draw.rect(surface, theme.PANEL, DEMO_RECT, border_radius=12)
            image = a.image_fit(self.entry.icon, (260, 260))
            surface.blit(image, image.get_rect(center=(DEMO_RECT.centerx, 290)))
            draw_text(surface, self.demo_error or self.entry.summary, a.font(22),
                      (DEMO_RECT.x + 60, 448, DEMO_RECT.w - 120, 120), theme.TEXT, centered=True)
        self.ui.draw(surface)
