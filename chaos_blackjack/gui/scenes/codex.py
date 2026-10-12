"""Collection (codex) browser and detail scenes; providers own the content and demos."""

from __future__ import annotations

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex import CodexEntry, CodexSection, codex_sections, run_demo
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.codex_demo import CodexDemo
from chaos_blackjack.gui.components.codex_text import draw_text, wrap_text
from chaos_blackjack.gui.components.lobby import MARGIN, back_button, draw_backdrop, draw_header
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup
from chaos_blackjack.modes import EXPANSIONS_LABEL

W, H = LOGICAL_SIZE
HEADING_H = 32
NOTE_H = 40
GENERAL_AREA = pygame.Rect(MARGIN, 190, W - 2 * MARGIN - 12, 440)
GENERAL_TILE = (172, 160)
HOST_PANEL = pygame.Rect(MARGIN, 190, 330, 440)
HOST_AREA = pygame.Rect(HOST_PANEL.right + 28, 190, W - MARGIN - HOST_PANEL.right - 40, 440)
HOST_TILE = (104, 134)
DEMO_RECT = pygame.Rect(40, 110, 760, 510)
TEXT_PANEL = pygame.Rect(820, 110, W - 860, 510)
TEXT_RECT = TEXT_PANEL.inflate(-40, -40)


@register_scene("codex")
class CodexScene(Scene):
    """Tabs: the Classic Table, then "Dealers" with one tab per dealer (e.g. Poker
    Head). The Classic Table lays its groups out as a grid; a dealer page shows
    the character on the left and its rules and table items on the right. Long
    pages scroll with the wheel or Page Up/Down; Tab cycles the sections."""

    def on_enter(self, config: RunConfig | None = None, section: str | None = None, **params):
        self.config = config if config is not None else self.app.run_config
        self.sections = codex_sections(self.config)
        ids = [s.id for s in self.sections]
        self.current = section if section in ids else ids[0]
        self.scroll = 0
        assets = self.app.assets
        self.tabs = {}
        self.expansions_label_x = None
        x = MARGIN
        for s in self.sections:
            if s.expansion and self.expansions_label_x is None:
                x += 14
                self.expansions_label_x = x
                x += assets.font(theme.FONT_TINY, bold=True).size(EXPANSIONS_LABEL.upper())[0] + 14
            width = max(140, assets.font(theme.FONT_BODY).size(s.label)[0] + 40)
            self.tabs[s.id] = Button(assets, (x, 134, width, 42), s.label, lambda sid=s.id: self._select(sid),
                                     style="ghost", font_size=20, key_hint="")
            x += width + 10
        self.about = Button(assets, (HOST_PANEL.x + 24, HOST_PANEL.bottom - 60, HOST_PANEL.w - 48, 44),
                            "About this table", self._open_table, style="ghost", font_size=18, key_hint="")
        self.ui = WidgetGroup(*self.tabs.values(), self.about, back_button(assets, self.app.scenes.pop))
        self._select(self.current)

    # ------------------------------------------------------------------ data

    @property
    def section(self) -> CodexSection:
        return next(s for s in self.sections if s.id == self.current)

    @property
    def entries(self) -> tuple[CodexEntry, ...]:
        return self.section.entries

    def _select(self, section_id):
        self.current = section_id
        self.scroll = 0
        for sid, tab in self.tabs.items():
            expansion = next(s.expansion for s in self.sections if s.id == sid)
            tab.style = "ghost" if sid != section_id else ("chaos" if expansion else "primary")
        self.about.visible = self.about.enabled = self.section.mode is not None
        self._layout()

    def _open_table(self):
        if self.section.mode is not None:
            self.app.scenes.push("codex_detail", entry=self.section.mode, config=self.config)

    # ---------------------------------------------------------------- layout

    def _area(self) -> pygame.Rect:
        return HOST_AREA if self.section.expansion else GENERAL_AREA

    def _layout(self):
        """Group headings and tiles at the current scroll position."""
        area = self._area()
        tile, gap = (HOST_TILE, 8) if area is HOST_AREA else (GENERAL_TILE, 22)
        per_row = max(1, (area.w + gap) // (tile[0] + gap))
        self.headings, self.notes, self.tiles = [], [], []
        y = area.y - self.scroll
        for group in self.section.groups:
            self.headings.append((group.label, y))
            y += HEADING_H
            if not group.entries:
                self.notes.append((group.empty, y))
                y += NOTE_H
                continue
            for index, entry in enumerate(group.entries):
                row, column = divmod(index, per_row)
                rect = pygame.Rect(area.x + column * (tile[0] + gap), y + row * (tile[1] + gap), *tile)
                self.tiles.append((rect, entry))
            rows = (len(group.entries) + per_row - 1) // per_row
            y += rows * (tile[1] + gap) + 6
        self.content_h = y + self.scroll - area.y
        self.max_scroll = max(0, self.content_h - area.h)

    def _scroll_by(self, pixels):
        self.scroll = max(0, min(self.max_scroll, self.scroll + pixels))
        self._layout()

    def visible_tiles(self):
        """Tiles that are on screen (and so clickable)."""
        area = self._area()
        return [(r, e) for r, e in self.tiles if r.bottom > area.y and r.y < area.bottom]

    # ---------------------------------------------------------------- events

    def handle_event(self, event):
        if self.ui.handle_event(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            ids = [s.id for s in self.sections]
            delta = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self._select(ids[(ids.index(self.current) + delta) % len(ids)])
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            self._scroll_by(-200 if event.key == pygame.K_PAGEUP else 200)
        elif event.type == pygame.MOUSEWHEEL:
            self._scroll_by(-event.y * 60)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, entry in self.visible_tiles():
                if rect.collidepoint(event.pos):
                    self.app.scenes.push("codex_detail", entry=entry, config=self.config)
                    return

    # ---------------------------------------------------------------- drawing

    def draw(self, surface):
        assets = self.app.assets
        draw_backdrop(surface, assets, shade=215)
        draw_header(surface, assets, "Collection", "The classic table, the dealers you will meet, their rules and items.")
        if self.expansions_label_x is not None:
            label = assets.font(theme.FONT_TINY, bold=True).render(EXPANSIONS_LABEL.upper(), True, theme.GOLD_DIM)
            surface.blit(label, label.get_rect(midleft=(self.expansions_label_x, 155)))
        if self.section.expansion:
            self._draw_host(surface)
        area = self._area()
        clip = surface.get_clip()
        surface.set_clip(area.inflate(8, 8))
        small = assets.font(theme.FONT_TINY, bold=True)
        for label, y in self.headings:
            img = small.render(label.upper(), True, theme.GOLD_DIM)
            surface.blit(img, (area.x, y + 4))
            pygame.draw.line(surface, theme.GOLD_DIM, (area.x, y + 22), (area.right, y + 22), 1)
        for note, y in self.notes:
            draw_text(surface, note, assets.font(16), (area.x, y, area.w, NOTE_H), theme.TEXT_MUTED)
        mouse = self.app.mouse_pos()
        hovered = None
        for rect, entry in self.tiles:
            selected = rect.collidepoint(mouse) and area.collidepoint(mouse)
            pygame.draw.rect(surface, theme.PANEL, rect, border_radius=10)
            pygame.draw.rect(surface, theme.GOLD if selected else theme.FELT_LIGHT, rect, 2, border_radius=10)
            size = int(rect.w * (0.6 if area is HOST_AREA else 0.52))
            icon = assets.image_fit(entry.icon, (size, size))
            surface.blit(icon, icon.get_rect(center=(rect.centerx, rect.y + 12 + size // 2)))
            font = assets.font(15 if area is HOST_AREA else 18)
            draw_text(surface, entry.name, font, (rect.x + 6, rect.y + size + 20, rect.w - 12, 44), centered=True)
            if selected:
                hovered = entry
        surface.set_clip(clip)
        if self.max_scroll:
            track = pygame.Rect(area.right + 10, area.y, 3, area.h)
            pygame.draw.rect(surface, theme.PANEL, track, border_radius=2)
            h = max(24, int(track.h * area.h / max(1, self.content_h)))
            y = track.y + int((track.h - h) * self.scroll / self.max_scroll)
            pygame.draw.rect(surface, theme.GOLD_DIM, (track.x, y, 3, h), border_radius=2)
        self.ui.draw(surface)
        footer = hovered.summary if hovered else (f"{len(self.entries)} entries  \u00b7  Tab: next section  \u00b7  "
                                                  "Click an entry to explore")
        draw_text(surface, footer, assets.font(16), (300, 646, W - 364, 48), theme.TEXT_MUTED)

    def _draw_host(self, surface):
        """The dealer as a character: portrait, name, profile and signature line."""
        a, s, r = self.app.assets, self.section, HOST_PANEL
        accent = theme.CHAOS_MAGENTA
        pygame.draw.rect(surface, (0x26, 0x1E, 0x2B), r, border_radius=14)
        pygame.draw.rect(surface, accent, r, 2, border_radius=14)
        portrait = a.image_fit(s.portrait, (104, 104))
        surface.blit(portrait, portrait.get_rect(topleft=(r.x + 14, r.y + 12)))
        img = a.font(theme.FONT_HEADING - 8, role="display").render(s.label, True, accent)
        surface.blit(img, img.get_rect(midleft=(r.x + 128, r.y + 56)))
        dealer = a.font(theme.FONT_TINY, bold=True).render("DEALER", True, theme.GOLD_DIM)
        surface.blit(dealer, dealer.get_rect(topleft=(r.x + 130, r.y + 78)))
        y = r.y + 128
        body = a.font(15)
        for paragraph in s.profile or (s.summary,):
            y += draw_text(surface, paragraph, body, (r.x + 22, y, r.w - 44, r.bottom - 70 - y), theme.TEXT) + 6
        if s.quote:
            draw_text(surface, "\u201c" + s.quote + "\u201d", a.font(15), (r.x + 22, y + 2, r.w - 44, 44), accent)


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
        draw_backdrop(surface, a, shade=215)
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
