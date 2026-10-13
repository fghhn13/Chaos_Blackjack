"""The table host (native part `core.host`): portrait, mood and speech.

The panel only reads `GameView` and notices. Mood is a presentation choice:
the portrait reacts to what just happened (a rule landing, a bust, a win).
An AI with a persona (content packs) brings its own name, portraits and lines;
without one the built-in Chaos AI look and lines below apply.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Callable

import pygame

from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import GameView, TablePhase
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.anim import Tween, out_back
from chaos_blackjack.gui.texts import asset_name
from chaos_blackjack.gui.widgets import Widget, wrap_text

if TYPE_CHECKING:
    from chaos_blackjack.content.ai_profile import Persona
    from chaos_blackjack.gui.assets import AssetManager

PORTRAIT = 200
HEIGHT = 12 + PORTRAIT + 4 + 30 + 70 + 6  # portrait, name row, speech bubble

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

# Notice -> persona event (see content.ai_profile.PERSONA_EVENTS).
PERSONA_NOTICE_EVENT = {
    NoticeKind.ROUND_STARTED: "round_started",
    NoticeKind.RULE_MODIFIER_APPLIED: "rule_applied",
    NoticeKind.CHAOS_NARRATION: "narration",
    NoticeKind.CHAOS_POKE_REPLY: "poke",
    NoticeKind.ITEM_USED: "item_used",
    NoticeKind.PLAYER_BUST: "player_bust",
    NoticeKind.PLAYER_BLACKJACK: "player_blackjack",
    NoticeKind.DEALER_BLACKJACK: "dealer_blackjack",
    NoticeKind.DEALER_BUSTS: "dealer_busts",
}


class ChaosPanel(Widget):
    def __init__(self, assets: "AssetManager", rect: pygame.Rect | tuple[int, int, int, int],
                 on_poke: Callable[[], object] | None = None, persona: "Persona | None" = None) -> None:
        self.assets = assets
        self.rect = pygame.Rect(rect)
        self.persona = persona
        self._turn = 0  # rotates persona lines
        self._busted = False
        self.mood = persona.default if persona else "calm"
        self.speech: str | None = None
        self.chaos_enabled = False
        self.on_poke = on_poke
        self.poke_enabled = False
        self._pop: Tween | None = None  # portrait bounce when the mood changes

    @property
    def portrait_rect(self) -> pygame.Rect:
        rect = pygame.Rect(0, 0, PORTRAIT, PORTRAIT)
        rect.midtop = (self.rect.centerx, self.rect.y + 12)
        return rect

    # -------------------------------------------------------------- state

    def sync(self, v: GameView) -> None:
        self.chaos_enabled = v.chaos_enabled
        self.poke_enabled = bool(self.on_poke and v.chaos_enabled and v.phase in (
            TablePhase.BETTING, TablePhase.PLAYER_TURN, TablePhase.ROUND_OVER,
        ))
        if not v.chaos_enabled:
            self.mood = self.persona.moods.get("off", self.persona.default) if self.persona else "calm"

    def react(self, n: Notice) -> None:
        if not self.chaos_enabled:
            return
        if self.persona is not None:
            self._react_persona(n)
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
        if mood and mood != self.mood:
            self.mood = mood
            self._pop = Tween(0.4, ease=out_back)

    def _react_persona(self, n: Notice) -> None:
        p = self.persona
        assert p is not None
        if n.kind == NoticeKind.ROUND_STARTED:
            self._busted = False
        if n.kind == NoticeKind.ROUND_SETTLED:
            event = f"outcome_{getattr(n.data.get('result'), 'outcome', '')}"
        else:
            event = PERSONA_NOTICE_EVENT.get(n.kind, "")
        if n.kind in (NoticeKind.CHAOS_NARRATION, NoticeKind.CHAOS_POKE_REPLY):
            self.speech = str(n.data.get("text") or n.text) or self.speech
        elif not (n.kind == NoticeKind.ROUND_SETTLED and self._busted):  # keep the bust remark
            line = p.line(event, self._turn)
            if line is not None:
                rule = asset_name(str(n.data.get("rule_id", ""))) if n.kind == NoticeKind.RULE_MODIFIER_APPLIED else ""
                self.speech = line.replace("{rule}", rule)
                self._turn += 1
        if n.kind == NoticeKind.PLAYER_BUST:
            self._busted = True
        mood = p.moods.get(event)
        if mood and mood != self.mood:
            self.mood = mood
            self._pop = Tween(0.4, ease=out_back)

    def _face(self) -> str:
        return self.persona.asset_id(self.mood) if self.persona else mood_face(self.assets, self.mood)

    def update(self, dt: float) -> None:
        if self._pop is not None:
            self._pop.elapsed += dt
            if self._pop.done:
                self._pop = None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                and self.poke_enabled and self.on_poke is not None
                and self.portrait_rect.collidepoint(event.pos)):
            self.on_poke()
            return True
        return False

    # --------------------------------------------------------------- draw

    def draw(self, surface: pygame.Surface) -> None:
        a = self.assets
        r = self.rect
        portrait = a.image_fit(self._face(), (PORTRAIT, PORTRAIT))
        if self._pop is not None:
            k = 0.86 + 0.14 * self._pop.value
            w, h = portrait.get_size()
            portrait = pygame.transform.smoothscale(portrait, (max(1, round(w * k)), max(1, round(h * k))))
        surface.blit(portrait, portrait.get_rect(midtop=(r.centerx, r.y + 12)))
        if self.poke_enabled:
            hint = a.font(theme.FONT_TINY).render("Click to ask", True, theme.IVORY)
            label = pygame.Rect(0, 0, hint.get_width() + 18, hint.get_height() + 8)
            label.midbottom = (self.portrait_rect.centerx, self.portrait_rect.bottom - 4)
            pygame.draw.rect(surface, theme.DARK, label, border_radius=6)
            surface.blit(hint, hint.get_rect(center=label.center))

        y = r.y + 12 + PORTRAIT + 4
        title = self.persona.name if self.persona else "Chaos AI"
        name = a.font(theme.FONT_BODY + 2, role="display").render(title, True, theme.GOLD)
        mood_text = self.mood.replace("_", " ") if self.chaos_enabled else "off duty"
        mood = a.font(theme.FONT_TINY).render(mood_text, True, theme.TEXT_MUTED)
        surface.blit(name, (r.x + 14, y))
        surface.blit(mood, mood.get_rect(bottomright=(r.right - 14, y + name.get_height() - 2)))
        self._draw_speech(surface, pygame.Rect(r.x + 12, y + 34, r.w - 24, 66))

    def _draw_speech(self, surface: pygame.Surface, box: pygame.Rect) -> None:
        p = self.persona
        if not self.chaos_enabled:
            text, color = (p and p.line("off")) or OFF_LINE, theme.TEXT_MUTED
        else:
            text, color = (self.speech or (p and p.line("idle")) or IDLE_LINE), theme.IVORY
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
