"""Left table column: the Chaos AI's portrait, mood, speech and active rules.

The panel only reads `GameView` and notices. Mood is a presentation choice:
the portrait reacts to what just happened (a rule landing, a bust, a win).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Callable

import pygame

from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import GameView, RuleView, TablePhase
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.texts import asset_name
from chaos_blackjack.gui.widgets import Widget, draw_heading, draw_panel, draw_tooltip, fit_text, wrap_text

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

PORTRAIT = 200
RULE_ROW = 44
RULE_ICON = 32
MAX_RULE_ROWS = 4

# Round outcome (RoundResult.outcome) -> how the house feels about it.
OUTCOME_MOOD = {"dealer": "laugh", "player": "angry", "blackjack": "angry", "surrender": "smug", "push": "calm"}
NOTICE_MOOD = {
    NoticeKind.ROUND_STARTED: "calm",
    NoticeKind.RULE_MODIFIER_APPLIED: "smug",
    NoticeKind.CHAOS_NARRATION: "smug",
    NoticeKind.PLAYER_BUST: "laugh",
    NoticeKind.DEALER_BLACKJACK: "laugh",
    NoticeKind.PLAYER_BLACKJACK: "angry",
    NoticeKind.DEALER_BUSTS: "angry",
}

IDLE_LINE = "Place your bet. I'm watching."
ROUND_LINE = "Cards are out. Your move."
OUTCOME_LINE = {
    "dealer": "The house always wins.",
    "player": "Enjoy it while it lasts.",
    "blackjack": "Beginner's luck.",
    "push": "A draw. How dull.",
    "surrender": "Wise. Cowardly, but wise.",
}
BUST_LINE = "Too greedy!"


def mood_face(assets: "AssetManager", mood: str) -> str:
    """Portrait id for `mood`; falls back to the calm art while a mood has none."""
    face = f"chaos_{mood}"
    if not assets.has_file(face) and assets.has_file("chaos_calm"):
        return "chaos_calm"
    return face
OFF_LINE = "Chaos mode is off. Plain blackjack tonight."


class ChaosPanel(Widget):
    def __init__(self, assets: "AssetManager", rect: pygame.Rect | tuple[int, int, int, int],
                 on_poke: Callable[[], object] | None = None) -> None:
        self.assets = assets
        self.rect = pygame.Rect(rect)
        self.mood = "calm"
        self.speech: str | None = None
        self.chaos_enabled = False
        self.rules: tuple[RuleView, ...] = ()
        self.rule_rects: list[tuple[pygame.Rect, RuleView]] = []
        self.hovered: RuleView | None = None
        self._mouse = (0, 0)
        self.on_poke = on_poke
        self.poke_enabled = False

    @property
    def portrait_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, PORTRAIT, PORTRAIT)
        rect.midtop = (self.rect.centerx, self.rect.y + 12)
        return rect

    @property
    def log_area(self) -> pygame.Rect:
        """Space below the rules list for the event feed (grows when few rules are active)."""
        rows = max(1, min(len(self.rules), MAX_RULE_ROWS)) if self.chaos_enabled else 1
        top = self._rules_top() + rows * RULE_ROW + 4 + 30  # + "Table log" heading
        return pygame.Rect(self.rect.x + 14, top, self.rect.w - 28, self.rect.bottom - 10 - top)

    # -------------------------------------------------------------- state

    def sync(self, v: GameView) -> None:
        self.chaos_enabled = v.chaos_enabled
        self.rules = v.active_rules
        self.poke_enabled = bool(self.on_poke and v.chaos_enabled and v.phase in (
            TablePhase.BETTING, TablePhase.PLAYER_TURN, TablePhase.ROUND_OVER,
        ))
        if not v.chaos_enabled:
            self.mood = "calm"

    def react(self, n: Notice) -> None:
        if not self.chaos_enabled:
            return
        if n.kind in (NoticeKind.CHAOS_NARRATION, NoticeKind.CHAOS_POKE_REPLY):
            self.speech = str(n.data.get("text") or n.text) or self.speech
        elif n.kind == NoticeKind.RULE_MODIFIER_APPLIED:
            self.speech = f"New rule: {asset_name(str(n.data.get('rule_id')))}. Good luck."
        elif n.kind == NoticeKind.ROUND_STARTED:
            self.speech = ROUND_LINE
        elif n.kind == NoticeKind.PLAYER_BUST:
            self.speech = BUST_LINE
        if n.kind == NoticeKind.ROUND_SETTLED:
            outcome = getattr(n.data.get("result"), "outcome", "")
            mood = OUTCOME_MOOD.get(outcome)
            if outcome in OUTCOME_LINE and self.speech != BUST_LINE:
                self.speech = OUTCOME_LINE[outcome]
        else:
            mood = NOTICE_MOOD.get(n.kind)
        if mood:
            self.mood = mood

    def handle_event(self, event: pygame.event.Event) -> bool:
        if (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                and self.poke_enabled and self.on_poke is not None
                and self.portrait_rect.collidepoint(event.pos)):
            self.on_poke()
            return True
        if event.type == pygame.MOUSEMOTION:
            self._mouse = event.pos
            self.hovered = next((r for rect, r in self.rule_rects if rect.collidepoint(event.pos)), None)
        return False

    # --------------------------------------------------------------- draw

    def _heading_y(self) -> int:
        # portrait, name row (30), speech bubble (70), gap
        return self.rect.y + 12 + PORTRAIT + 4 + 30 + 70 + 12

    def _rules_top(self) -> int:
        return self._heading_y() + 30

    def draw(self, surface: pygame.Surface) -> None:
        a = self.assets
        r = self.rect
        draw_panel(surface, r)
        inner_w = r.w - 28

        portrait = a.image_fit(mood_face(a, self.mood), (PORTRAIT, PORTRAIT))
        surface.blit(portrait, portrait.get_rect(midtop=(r.centerx, r.y + 12)))
        if self.poke_enabled:
            hint = a.font(theme.FONT_TINY).render("Click to ask", True, theme.IVORY)
            label = pygame.Rect(0, 0, hint.get_width() + 18, hint.get_height() + 8)
            label.midbottom = (self.portrait_rect.centerx, self.portrait_rect.bottom - 4)
            pygame.draw.rect(surface, theme.DARK, label, border_radius=6)
            surface.blit(hint, hint.get_rect(center=label.center))

        y = r.y + 12 + PORTRAIT + 4
        name = a.font(theme.FONT_BODY + 2, role="display").render("Chaos AI", True, theme.GOLD)
        mood = a.font(theme.FONT_TINY).render(self.mood if self.chaos_enabled else "off duty", True, theme.TEXT_MUTED)
        surface.blit(name, (r.x + 14, y))
        surface.blit(mood, mood.get_rect(bottomright=(r.right - 14, y + name.get_height() - 2)))

        self._draw_speech(surface, pygame.Rect(r.x + 12, y + 34, r.w - 24, 66))

        draw_heading(surface, a, "Active rules", (r.x + 14, self._heading_y()), inner_w)
        y = self._rules_top()
        self.rule_rects = []
        small = a.font(theme.FONT_SMALL, bold=True)
        tiny = a.font(theme.FONT_TINY)
        log = self.log_area
        draw_heading(surface, a, "Table log", (r.x + 14, log.y - 30), inner_w)
        if not self.chaos_enabled or not self.rules:
            text = "Chaos off" if not self.chaos_enabled else "None yet"
            surface.blit(tiny.render(text, True, theme.TEXT_MUTED), (r.x + 14, y + 4))
            return
        shown = self.rules[:MAX_RULE_ROWS]
        for i, rule in enumerate(shown):
            row = pygame.Rect(r.x + 8, y + i * RULE_ROW, r.w - 16, RULE_ROW - 4)
            if rule is self.hovered:
                pygame.draw.rect(surface, theme.FELT, row, border_radius=8)
            surface.blit(a.image(rule.id, (RULE_ICON, RULE_ICON)), (row.x + 6, row.centery - RULE_ICON // 2))
            tx = row.x + RULE_ICON + 14
            tw = row.right - tx - 6
            surface.blit(small.render(fit_text(small, asset_name(rule.id), tw), True, theme.CHAOS_MAGENTA), (tx, row.y + 2))
            surface.blit(tiny.render(fit_text(tiny, rule.description, tw), True, theme.TEXT_MUTED), (tx, row.y + 21))
            self.rule_rects.append((row, rule))
        if len(self.rules) > MAX_RULE_ROWS:
            more = tiny.render(f"+{len(self.rules) - MAX_RULE_ROWS} more", True, theme.TEXT_MUTED)
            surface.blit(more, more.get_rect(topright=(r.right - 14, y + MAX_RULE_ROWS * RULE_ROW - 4)))

    def _draw_speech(self, surface: pygame.Surface, box: pygame.Rect) -> None:
        if not self.chaos_enabled:
            text, color = OFF_LINE, theme.TEXT_MUTED
        else:
            text, color = (self.speech or IDLE_LINE), theme.IVORY
        pygame.draw.rect(surface, theme.DARK, box, border_radius=10)
        pygame.draw.rect(surface, theme.CHAOS_PURPLE, box, 1, border_radius=10)
        tip = [(box.x + 26, box.y), (box.x + 36, box.y - 8), (box.x + 46, box.y)]
        pygame.draw.polygon(surface, theme.DARK, tip)
        pygame.draw.lines(surface, theme.CHAOS_PURPLE, False, tip, 1)
        font = self.assets.font(theme.FONT_SMALL)
        lines = wrap_text(font, f"“{text}”", box.w - 20, max_lines=3)
        lh = font.get_linesize()
        y = box.centery - lh * len(lines) // 2
        for line in lines:
            surface.blit(font.render(line, True, color), (box.x + 10, y))
            y += lh

    def draw_overlay(self, surface: pygame.Surface) -> None:
        if self.hovered is not None:
            draw_tooltip(surface, self.assets, f"{asset_name(self.hovered.id)}: {self.hovered.description}",
                         (self._mouse[0] + 16, self._mouse[1] + 12))
