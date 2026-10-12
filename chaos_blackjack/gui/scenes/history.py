"""Paged run records with readable summary details from the meta API."""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import back_button, mode_name
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text, paragraph
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup, wrap_text
from chaos_blackjack.gui.touch import TOUCH_SCROLL

DETAIL_RECT = pygame.Rect(614, 315, 566, 222)


@register_scene("history")
class HistoryScene(MetaScreen):
    title = "Run history"

    def on_enter(self, player_id, **params):
        self.setup()
        self.player_id = player_id
        self.player = self.action(lambda: meta.get_player(player_id))
        self.records = self.action(lambda: meta.history(player_id)) or []
        self.page = 0
        self.detail_scroll = 0
        self._touch_pixels = 0
        self.selected = self.records[0] if self.records else None
        self.subtitle = "Choose a run to revisit its result, upgrades and discoveries."
        self.build_widgets()

    def build_widgets(self):
        self.ui = WidgetGroup(keyboard=True)
        self.record_buttons = {}
        for i, record in enumerate(self.records[self.page * 7:self.page * 7 + 7]):
            label = f"#{record.id}  {mode_name(record.mode)}  ·  {(record.result or 'In progress').title()}"
            b = Button(self.app.assets, (64, 155 + i * 56, 488, 46), label,
                       lambda r=record: self.select(r), font_size=18, style="ghost", key_hint="")
            b.selected = bool(self.selected and record.id == self.selected.id)
            self.record_buttons[record.id] = b
            self.ui.add(b)
        self.ui.add(back_button(self.app.assets, self.app.scenes.pop))
        self.ui.add(Button(self.app.assets, (288, 642, 130, 50), "Previous", lambda: self.turn_page(-1),
                           enabled=self.page > 0, style="ghost", font_size=20))
        self.ui.add(Button(self.app.assets, (422, 642, 130, 50), "Next", lambda: self.turn_page(1),
                           enabled=(self.page + 1) * 7 < len(self.records), style="ghost", font_size=20))

    def select(self, record):
        self.selected = record
        self.detail_scroll = 0
        self._touch_pixels = 0
        self.build_widgets()

    def turn_page(self, delta):
        self.page = max(0, min(self.page + delta, max(0, (len(self.records) - 1) // 7)))
        self.selected = self.records[self.page * 7] if self.records else None
        self.detail_scroll = 0
        self._touch_pixels = 0
        self.build_widgets()

    def detail_lines(self):
        r = self.selected
        if r is None:
            return []
        summary = r.summary
        lines = [f"Balance profile: {r.balance_profile or '-'}",
                 f"Chaos AI: {summary.get('chaos_ai') or 'None'}",
                 f"Blackjacks: {summary.get('blackjacks', 0)}  /  Doubles: {summary.get('doubles', 0)}  /  Surrenders: {summary.get('surrenders', 0)}"]
        for label, values in (("Upgrades", r.upgrades), ("Rules seen", summary.get("rules_seen", {})),
                              ("Items used", summary.get("items_used", {})), ("Items bought", summary.get("items_bought", {}))):
            value = ", ".join(f"{k.replace('_', ' ')} x{v}" for k, v in values.items()) or "None"
            lines.append(f"{label}: {value}")
        font = self.app.assets.font(16)
        return [wrapped for line in lines for wrapped in wrap_text(font, line, 550, max_lines=10000)]

    def handle_event(self, event):
        delta = 0
        if event.type == TOUCH_SCROLL and DETAIL_RECT.collidepoint(event.pos):
            height = self.app.assets.font(16).get_linesize()
            pixels = getattr(self, "_touch_pixels", 0) + event.dy
            delta = int(pixels / height)
            self._touch_pixels = pixels - delta * height
        elif event.type == pygame.MOUSEWHEEL:
            delta = -event.y * 3
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            delta = -3 if event.key == pygame.K_PAGEUP else 3
        if delta:
            capacity = 222 // self.app.assets.font(16).get_linesize()
            self.detail_scroll = max(0, min(self.detail_scroll + delta, max(0, len(self.detail_lines()) - capacity)))
        else:
            super().handle_event(event)

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        panel(surface, (584, 145, 632, 425))
        r = self.selected
        if r is None:
            paragraph(surface, a, "No runs yet. Start a new run from the main menu; its story will appear here.",
                      (616, 182, 560, 150))
        else:
            text(surface, a, f"Run #{r.id}  /  {(r.result or 'In progress').title()}", (612, 169), size=28,
                 color=theme.GOLD, width=570)
            text(surface, a, r.started_at, (614, 213), size=16, width=566)
            text(surface, a, f"{mode_name(r.mode)}  /  {r.rounds or 0} rounds  /  {r.tokens_earned or 0} tokens", (614, 246), width=566)
            text(surface, a, f"Final bankroll: {r.final_money if r.final_money is not None else '-'}  /  Peak: {r.peak_money if r.peak_money is not None else '-'}",
                 (614, 280), width=566)
            lines = self.detail_lines()
            line_height = a.font(16).get_linesize()
            capacity = 222 // line_height
            for i, line in enumerate(lines[self.detail_scroll:self.detail_scroll + capacity]):
                text(surface, a, line, (614, 315 + i * line_height), size=16, color=theme.TEXT_MUTED)
            if len(lines) > capacity:
                text(surface, a, "Swipe / Wheel / Page Up / Page Down to scroll details", (614, 547), size=14, color=theme.GOLD)
        self.ui.draw(surface)
