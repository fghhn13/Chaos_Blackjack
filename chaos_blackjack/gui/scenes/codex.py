"""Collection (codex) browser and detail scenes; providers own the content and demos."""

from __future__ import annotations

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex import CodexEntry, CodexSection, codex_sections, run_demo
from chaos_blackjack.codex.build_reference import CATEGORY_LABELS, STYLE_LABELS
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.codex_demo import CodexDemo
from chaos_blackjack.gui.components.codex_text import draw_text, wrap_text
from chaos_blackjack.gui.components.lobby import MARGIN, back_button, draw_backdrop, draw_header
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, WidgetGroup
from chaos_blackjack.modes import EXPANSIONS_LABEL
from chaos_blackjack.gui.touch import TOUCH_SCROLL

W, H = LOGICAL_SIZE
NOTE_H = 40
HOST_PANEL = pygame.Rect(MARGIN, 190, 188, 440)
GENERAL_AREA = pygame.Rect(268, 238, 620, 392)
HOST_AREA = pygame.Rect(268, 258, 620, 372)
PREVIEW_PANEL = pygame.Rect(908, 190, W - 948, 440)
PREVIEW_TEXT = pygame.Rect(926, 316, W - 984, 180)
DEMO_RECT = pygame.Rect(40, 110, 760, 510)
TEXT_PANEL = pygame.Rect(820, 110, W - 860, 510)
TEXT_RECT = TEXT_PANEL.inflate(-40, -40)


@register_scene("codex")
class CodexScene(Scene):
    """Series tabs, category/style filters, cards and an independent reference pane."""

    def on_enter(self, config: RunConfig | None = None, section: str | None = None, **params):
        self.config = config if config is not None else self.app.run_config
        self.sections = codex_sections(self.config)
        ids = [s.id for s in self.sections]
        self.current = section if section in ids else ids[0]
        self.scroll = 0
        self.category = self.style = "all"
        self.selected_entry = None
        self.detail_offset = 0
        self.reference = ""
        self.saved_sections = {}
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
        self.about = Button(assets, (HOST_PANEL.x + 12, 312, HOST_PANEL.w - 24, 30),
                            "Table rules", self._open_table, style="ghost", font_size=16, key_hint="")
        self.back = back_button(assets, self.app.scenes.pop)
        self.open_detail = Button(assets, (PREVIEW_PANEL.x + 18, 590, PREVIEW_PANEL.w - 36, 32),
                                  "Full details", self._open_detail, style="ghost", font_size=16, key_hint="")
        self.category_buttons = {}
        self.style_buttons = {}
        self.related_buttons = []
        self._select(self.current)

    # ------------------------------------------------------------------ data

    @property
    def section(self) -> CodexSection:
        return next(s for s in self.sections if s.id == self.current)

    @property
    def entries(self) -> tuple[CodexEntry, ...]:
        return self.section.entries

    @staticmethod
    def _category(entry):
        return entry.category or entry.kind

    @property
    def filtered_entries(self):
        return tuple(e for e in self.entries
                     if (self.category == "all" or self._category(e) == self.category)
                     and (self.style == "all" or e.style == self.style))

    def _save_section(self):
        selected = self.selected_entry
        self.saved_sections[self.current] = (self.category, self.style, self.scroll,
            (selected.kind, selected.id) if selected else None, self.detail_offset)

    def _select(self, section_id):
        if hasattr(self, "ui"):
            self._save_section()
        self.current = section_id
        self.category, self.style, self.scroll, selected, offset = self.saved_sections.get(
            section_id, ("all", "all", 0, None, 0))
        for sid, tab in self.tabs.items():
            expansion = next(s.expansion for s in self.sections if s.id == sid)
            tab.style = "ghost" if sid != section_id else ("chaos" if expansion else "primary")
        self.about.visible = self.about.enabled = self.section.mode is not None
        self._make_filters()
        self._layout()
        entry = next((e for e in self.filtered_entries if (e.kind, e.id) == selected), None)
        self._select_entry(entry or next(iter(self.filtered_entries), None))
        self._scroll_detail(offset)

    def _open_table(self):
        if self.section.mode is not None:
            self.app.scenes.push("codex_detail", entry=self.section.mode, config=self.config)

    def _open_detail(self):
        if self.selected_entry:
            self.app.scenes.push("codex_detail", entry=self.selected_entry, config=self.config)

    def _make_filters(self):
        assets = self.app.assets
        kinds = {self._category(e) for e in self.entries}
        labels = {**CATEGORY_LABELS, "core": "Core gifts", "permanent": "Permanents",
                  "item": "Consumables", "finance": "Financial products", "rule": "Chaos rules",
                  "environment": "Environment rules", "mode": "Tables", "ai": "Guest dealers"}
        categories = [("all", "All entries")] + [(k, labels.get(k, k.replace('_', ' ').title()))
            for k in ("mode", "core", "permanent", "item", "finance", "environment", "rule", "ai") if k in kinds]
        categories += [(k, k.replace('_', ' ').title()) for k in sorted(kinds - set(labels))]
        self.category_buttons = {}
        for index, (kind, label) in enumerate(categories):
            count = len(self.entries) if kind == "all" else sum(self._category(e) == kind for e in self.entries)
            b = Button(assets, (HOST_PANEL.x + 12, 362 + index * 34, HOST_PANEL.w - 24, 30),
                       f"{label} ({count})", lambda k=kind: self._filter(category=k),
                       style="ghost", font_size=14, key_hint="")
            b.selected = kind == self.category
            self.category_buttons[kind] = b
        self.style_buttons = {}
        if self.current == "poker_head":
            for index, (key, label) in enumerate((("all", "All builds"), *STYLE_LABELS.items())):
                b = Button(assets, (268 + index * 89, 216, 83, 30), label,
                           lambda s=key: self._filter(style=s), style="ghost", font_size=13, key_hint="")
                b.selected = key == self.style
                self.style_buttons[key] = b

    def _filter(self, *, category=None, style=None):
        if category is not None: self.category = category
        if style is not None: self.style = style
        self.scroll = 0
        self._make_filters()
        self._layout()
        entry = self.selected_entry if self.selected_entry in self.filtered_entries else next(iter(self.filtered_entries), None)
        self._select_entry(entry)

    def _select_entry(self, entry):
        self.selected_entry = entry
        self.detail_offset = 0
        self.reference = entry.detail(self.config) if entry else "No entries match these filters."
        self.open_detail.enabled = entry is not None
        self.open_detail.text = "Watch demo" if entry and entry.demo else "Full details"
        self.related_buttons = []
        if entry:
            by_id = {e.id: e for e in self.entries if e.kind == entry.kind}
            for entry_id in entry.related[:2]:
                if entry_id not in by_id: continue
                other = by_id[entry_id]
                self.related_buttons.append(Button(self.app.assets,
                    (PREVIEW_PANEL.x + 18, 524 + len(self.related_buttons) * 30, PREVIEW_PANEL.w - 36, 26),
                    other.name, lambda e=other: self._follow_related(e),
                    style="ghost", font_size=13, key_hint=""))
        self.ui = WidgetGroup(*self.tabs.values(), self.about, self.back, self.open_detail,
                              *self.category_buttons.values(), *self.style_buttons.values(), *self.related_buttons)

    def _follow_related(self, entry):
        if entry not in self.filtered_entries:
            self.category = self.style = "all"
            self._make_filters()
        self._select_entry(entry)
        self._reveal_selected()

    def _scroll_detail(self, pixels):
        font = self.app.assets.font(16)
        height = len(wrap_text(self.reference, font, PREVIEW_TEXT.w)) * (font.get_linesize() + 4)
        self.detail_max_scroll = max(0, height - PREVIEW_TEXT.h)
        self.detail_offset = max(0, min(self.detail_max_scroll, self.detail_offset + pixels))

    def _reveal_selected(self):
        self._layout()
        area = self._area()
        rect = next((r for r, e in self.tiles if e == self.selected_entry), None)
        if rect:
            if rect.top < area.top: self._scroll_by(rect.top - area.top)
            elif rect.bottom > area.bottom: self._scroll_by(rect.bottom - area.bottom)

    # ---------------------------------------------------------------- layout

    def _area(self) -> pygame.Rect:
        return HOST_AREA if self.current == "poker_head" else GENERAL_AREA

    def _layout(self):
        """Cards use the entire grid; categories live in the fixed sidebar."""
        area = self._area()
        tile, gap = (302, 180), 12
        per_row = max(1, (area.w + gap) // (tile[0] + gap))
        self.headings, self.notes, self.tiles = [], [], []
        entries = self.filtered_entries
        rows = (len(entries) + per_row - 1) // per_row
        self.content_h = max(0, rows * (tile[1] + gap) - gap)
        self.max_scroll = max(0, self.content_h - area.h)
        self.scroll = min(self.scroll, self.max_scroll)
        for index, entry in enumerate(entries):
            row, column = divmod(index, per_row)
            rect = pygame.Rect(area.x + column * (tile[0] + gap), area.y - self.scroll + row * (tile[1] + gap), *tile)
            self.tiles.append((rect, entry))
        if not entries:
            self.notes.append(("No entries match these filters.", area.y + 24))

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
            if PREVIEW_PANEL.collidepoint(self.app.mouse_pos()): self._scroll_detail(-event.y * 48)
            else: self._scroll_by(-event.y * 60)
        elif event.type == TOUCH_SCROLL and PREVIEW_PANEL.collidepoint(event.pos):
            self._scroll_detail(event.dy)
        elif event.type == TOUCH_SCROLL and self._area().collidepoint(event.pos):
            self._scroll_by(event.dy)
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
            entries = self.filtered_entries
            if entries:
                index = entries.index(self.selected_entry) if self.selected_entry in entries else 0
                delta = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1, pygame.K_UP: -2, pygame.K_DOWN: 2}[event.key]
                self._select_entry(entries[max(0, min(len(entries) - 1, index + delta))])
                self._reveal_selected()
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._open_detail()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._area().collidepoint(event.pos):
                for rect, entry in self.visible_tiles():
                    if rect.collidepoint(event.pos):
                        self._select_entry(entry)
                        return

    # ---------------------------------------------------------------- drawing

    def draw(self, surface):
        assets = self.app.assets
        draw_backdrop(surface, assets, shade=215)
        draw_header(surface, assets, "Collection", "Explore the dealers, learn their effects, and find connections for your next build.")
        if self.expansions_label_x is not None:
            label = assets.font(theme.FONT_TINY, bold=True).render(EXPANSIONS_LABEL.upper(), True, theme.GOLD_DIM)
            surface.blit(label, label.get_rect(midleft=(self.expansions_label_x, 155)))
        self._draw_host(surface)
        self._draw_preview(surface)
        count = f"{len(self.filtered_entries)} / {len(self.entries)} entries"
        draw_text(surface, count, assets.font(16), (268, 192, 620, 28), theme.GOLD_DIM)
        area = self._area()
        clip = surface.get_clip()
        surface.set_clip(area)
        for note, y in self.notes:
            draw_text(surface, note, assets.font(16), (area.x, y, area.w, NOTE_H), theme.TEXT_MUTED)
        mouse = self.app.mouse_pos()
        for rect, entry in self.tiles:
            hover = rect.collidepoint(mouse) and area.collidepoint(mouse)
            selected = entry == self.selected_entry
            pygame.draw.rect(surface, theme.PANEL, rect, border_radius=10)
            pygame.draw.rect(surface, theme.GOLD if selected else theme.GOLD_DIM if hover else theme.FELT_LIGHT,
                             rect, 2, border_radius=10)
            icon = assets.image_fit(entry.icon, (54, 54))
            surface.blit(icon, icon.get_rect(center=(rect.x + 40, rect.y + 40)))
            draw_text(surface, entry.name, assets.font(17, bold=True), (rect.x + 78, rect.y + 12, rect.w - 90, 50))
            category = CATEGORY_LABELS.get(self._category(entry), self._category(entry).title())
            style = STYLE_LABELS.get(entry.style, entry.style)
            tags = category + (" / " + style if style and style != category else "")
            draw_text(surface, tags, assets.font(13), (rect.x + 14, rect.y + 66, rect.w - 28, 22), theme.GOLD_DIM)
            draw_text(surface, entry.summary, assets.font(15), (rect.x + 14, rect.y + 91, rect.w - 28, 55))
            draw_text(surface, entry.price or ("Animated demo" if entry.demo else "Reference"), assets.font(13),
                      (rect.x + 14, rect.bottom - 35, rect.w - 28, 19), theme.GOLD)
            phase = entry.timing
            if entry.category == "permanent": phase = "1 permanent slot / " + ("Active" if entry.timing in ("Your turn", "Before betting") else "Automatic")
            draw_text(surface, phase, assets.font(12), (rect.x + 14, rect.bottom - 18, rect.w - 28, 18), theme.TEXT_MUTED)
        surface.set_clip(clip)
        if self.max_scroll:
            track = pygame.Rect(area.right + 10, area.y, 3, area.h)
            pygame.draw.rect(surface, theme.PANEL, track, border_radius=2)
            h = max(24, int(track.h * area.h / max(1, self.content_h)))
            y = track.y + int((track.h - h) * self.scroll / self.max_scroll)
            pygame.draw.rect(surface, theme.GOLD_DIM, (track.x, y, 3, h), border_radius=2)
        self.ui.draw(surface)
        footer = "Click to select / Enter: details / Arrows: select / Tab: dealer / Scroll: browse"
        draw_text(surface, footer, assets.font(14), (268, 650, W - 308, 40), theme.TEXT_MUTED)

    def _draw_host(self, surface):
        """Compact identity and table reference above the fixed category navigation."""
        a, s, r = self.app.assets, self.section, HOST_PANEL
        accent = theme.CHAOS_MAGENTA
        pygame.draw.rect(surface, (0x26, 0x1E, 0x2B), r, border_radius=14)
        pygame.draw.rect(surface, accent, r, 2, border_radius=14)
        if s.portrait:
            portrait = a.image_fit(s.portrait, (54, 54))
            surface.blit(portrait, portrait.get_rect(topleft=(r.x + 12, r.y + 12)))
        draw_text(surface, s.label, a.font(19, bold=True), (r.x + (76 if s.portrait else 12), r.y + 14,
                  r.w - (88 if s.portrait else 24), 50), accent)
        font = a.font(13)
        lines = wrap_text(s.profile[0] if s.profile else s.summary, font, r.w - 24)
        brief = lines[:2]
        if len(lines) > 2:
            last = brief[-1].rstrip()
            while last and font.size(last + "...")[0] > r.w - 24: last = last[:-1]
            brief[-1] = last + "..."
        draw_text(surface, "\n".join(brief), font, (r.x + 12, 260, r.w - 24, 2 * (font.get_linesize() + 4)), theme.TEXT_MUTED)
        draw_text(surface, "BROWSE BY TYPE", a.font(12, bold=True), (r.x + 12, 344, r.w - 24, 18), theme.GOLD_DIM)

    def _draw_preview(self, surface):
        a, r, entry = self.app.assets, PREVIEW_PANEL, self.selected_entry
        pygame.draw.rect(surface, theme.PANEL, r, border_radius=12)
        if entry is None:
            draw_text(surface, self.reference, a.font(18), r.inflate(-36, -36), theme.TEXT_MUTED)
            return
        icon = a.image_fit(entry.icon, (64, 64))
        surface.blit(icon, icon.get_rect(topleft=(r.x + 18, r.y + 14)))
        draw_text(surface, entry.name, a.font(20, bold=True), (r.x + 98, r.y + 14, r.w - 116, 72), theme.GOLD)
        label = CATEGORY_LABELS.get(self._category(entry), self._category(entry).title())
        style = STYLE_LABELS.get(entry.style, entry.style)
        if style and style != label: label += " / " + style
        draw_text(surface, label, a.font(13), (r.x + 18, 274, r.w - 36, 20), theme.GOLD_DIM)
        draw_text(surface, entry.price or entry.timing, a.font(13), (r.x + 18, 296, r.w - 36, 20), theme.TEXT_MUTED)
        draw_text(surface, self.reference, a.font(16), PREVIEW_TEXT, offset=self.detail_offset)
        self._scroll_detail(0)
        if self.detail_max_scroll:
            track = pygame.Rect(r.right - 10, PREVIEW_TEXT.y, 3, PREVIEW_TEXT.h)
            pygame.draw.rect(surface, theme.FELT_LIGHT, track, border_radius=2)
            height = max(18, int(track.h * track.h / (track.h + self.detail_max_scroll)))
            y = track.y + int((track.h - height) * self.detail_offset / self.detail_max_scroll)
            pygame.draw.rect(surface, theme.GOLD_DIM, (track.x, y, 3, height), border_radius=2)
        draw_text(surface, "RELATED EFFECTS" if self.related_buttons else "Scroll this panel to read more",
                  a.font(12), (r.x + 18, 502, r.w - 36, 20), theme.TEXT_MUTED)


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
        for button in (self.play, self.replay, self.previous, self.next):
            button.visible = available

    @property
    def text_panel(self):
        return TEXT_PANEL if self.demo.frames else pygame.Rect(360, 110, W - 400, 510)

    @property
    def text_rect(self):
        return self.text_panel.inflate(-40, -40)

    def _scroll_text(self, delta):
        rect = self.text_rect
        lines = wrap_text(self.detail, self.app.assets.font(theme.FONT_BODY), rect.w)
        height = len(lines) * (self.app.assets.font(theme.FONT_BODY).get_linesize() + 4)
        self.text_offset = max(0, min(max(0, height - rect.h), self.text_offset + delta))

    def handle_event(self, event):
        if event.type == pygame.MOUSEWHEEL:
            self._scroll_text(-event.y * 48)
        elif event.type == TOUCH_SCROLL and self.text_rect.collidepoint(event.pos):
            self._scroll_text(event.dy)
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
        panel = self.text_panel
        pygame.draw.rect(surface, theme.PANEL, panel, border_radius=10)
        draw_text(surface, self.detail, a.font(theme.FONT_BODY), self.text_rect, offset=self.text_offset)
        draw_text(surface, "Swipe, scroll or PgUp/PgDn for more", a.font(14), (panel.x, 624, panel.w, 22), theme.TEXT_MUTED)
        if self.demo.frames:
            self.demo.draw(surface, DEMO_RECT)
            draw_text(surface, f"{self.demo.index + 1} / {len(self.demo.frames)}", a.font(16), (668, 652, 120, 28), theme.TEXT_MUTED)
        else:
            summary_panel = pygame.Rect(40, 110, 300, 510)
            pygame.draw.rect(surface, theme.PANEL, summary_panel, border_radius=12)
            image = a.image_fit(self.entry.icon, (112, 112))
            surface.blit(image, image.get_rect(center=(summary_panel.centerx, 200)))
            draw_text(surface, self.demo_error or self.entry.summary, a.font(18),
                      (60, 290, 260, 240), theme.TEXT)
            draw_text(surface, self.entry.price, a.font(16), (60, 546, 260, 54), theme.GOLD)
        self.ui.draw(surface)
