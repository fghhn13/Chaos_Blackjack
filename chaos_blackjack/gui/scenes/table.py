"""Table scene — plays a run through GameController.

The scene never decides rules. Each frame it reads `controller.view()` to
show/enable widgets and drains notices into handlers. Automatic steps (chaos
resolution, dealer draws) are paced by timers so they can be animated later.

Extending:
  * new player action  -> add a row to ACTION_BUTTONS (+ controller method)
  * react to an event  -> self.subscribe(NoticeKind.X, handler)
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import Action, GameView, TablePhase
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.bet_panel import BetPanel
from chaos_blackjack.gui.components.cards import CARD_SIZE, CardRenderer, deck_position, layout_hand
from chaos_blackjack.gui.components.hud import EventFeed, draw_status_bar
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import BAD, notice_line, outcome_banner
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE

DEALER_Y = 200
PLAYER_Y = 440
BANNER_Y = 320
ACTION_Y = 600

DEALER_STEP_DELAY = 0.7  # seconds between dealer decisions
CHAOS_DELAY = 0.4        # pause before the chaos AI acts
RUN_END_DELAY = 1.5      # let the last result sink in before the ending

# (action id, label, hotkey, style, controller method)
ACTION_BUTTONS: tuple[tuple[str, str, int, str, str], ...] = (
    (Action.HIT, "Hit  H", pygame.K_h, "primary", "hit"),
    (Action.STAND, "Stand  S", pygame.K_s, "primary", "stand"),
    (Action.DOUBLE, "Double  D", pygame.K_d, "primary", "double_down"),
    (Action.SURRENDER, "Surrender  R", pygame.K_r, "ghost", "surrender"),
)

NoticeHandler = Callable[[Notice], None]


@register_scene("table")
class TableScene(Scene):
    def on_enter(self, controller: GameController | None = None, **params) -> None:
        a = self.app.assets
        self.controller = controller or GameController(
            RunConfig(enable_chaos=self.app.prefs.enable_chaos)
        )
        self.cards = CardRenderer(a)
        self.feed = EventFeed(a, (24, 330))
        self.bet_panel = BetPanel(a, (W // 2, ACTION_Y + 30), self._deal, initial=10)

        bw, gap = 150, 16
        x0 = W // 2 - (len(ACTION_BUTTONS) * (bw + gap) - gap) // 2
        self.action_buttons: dict[str, Button] = {}
        for i, (action, label, key, style, method) in enumerate(ACTION_BUTTONS):
            self.action_buttons[action] = Button(
                a, (x0 + i * (bw + gap), ACTION_Y, bw, 56), label,
                self._command(method), style=style, hotkey=key,
            )
        self.next_button = Button(a, (W // 2 - 100, ACTION_Y, 200, 56), "Next Round  Enter",
                                  self._command("next_round"), hotkey=pygame.K_RETURN)
        self.ui = WidgetGroup(*self.action_buttons.values(), self.next_button)

        self._handlers: dict[str, list[NoticeHandler]] = {}
        self.subscribe("*", self._feed_notice)
        self._timer = 0.0
        self._ending_opened = False
        self.view: GameView = self.controller.view()
        self._sync_widgets()

    # ----------------------------------------------------------- notices

    def subscribe(self, kind: str, handler: NoticeHandler) -> None:
        """`kind="*"` receives every notice."""
        self._handlers.setdefault(kind, []).append(handler)

    def _pump_notices(self) -> None:
        for n in self.controller.drain_notices():
            for h in [*self._handlers.get(n.kind, []), *self._handlers.get("*", [])]:
                h(n)

    def _feed_notice(self, n: Notice) -> None:
        line = notice_line(n)
        if line is not None:
            self.feed.push(*line)

    # ---------------------------------------------------------- commands

    def _command(self, method: str) -> Callable[[], None]:
        def run() -> None:
            try:
                getattr(self.controller, method)()
            except ActionError as e:
                self.feed.push(str(e), BAD)
            self._after_command()

        return run

    def _deal(self, amount: int) -> None:
        try:
            self.controller.place_bet(amount)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _after_command(self) -> None:
        self._timer = 0.0
        self._pump_notices()
        self.view = self.controller.view()
        self._sync_widgets()

    # ------------------------------------------------------------- frame

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.scenes.push(
                "confirm",
                message="Return to the main menu? This run will be lost.",
                on_confirm=lambda: self.app.scenes.reset("menu"),
            )
            return
        if self.view.phase == TablePhase.BETTING:
            self.bet_panel.handle_event(event)
        else:
            self.ui.handle_event(event)

    def update(self, dt: float) -> None:
        self.feed.update(dt)
        self._timer += dt
        phase = self.view.phase
        if phase == TablePhase.CHAOS and self._timer >= CHAOS_DELAY:
            # Synchronous for now; phase 4 moves LLM calls off the render thread.
            self._command("resolve_chaos")()
        elif phase == TablePhase.DEALER_TURN and self._timer >= DEALER_STEP_DELAY:
            self._command("dealer_step")()
        elif phase == TablePhase.RUN_OVER and not self._ending_opened and self._timer >= RUN_END_DELAY:
            self._ending_opened = True
            v = self.view
            self.app.scenes.replace(
                "ending",
                kind=v.run_end.kind if v.run_end else "defeat",
                money=v.money,
                rounds=v.last_result.round if v.last_result else v.round,
            )

    def _sync_widgets(self) -> None:
        v = self.view
        player_turn = v.phase == TablePhase.PLAYER_TURN
        for action, button in self.action_buttons.items():
            button.visible = player_turn
            button.enabled = v.can(action)
        self.next_button.visible = v.phase == TablePhase.ROUND_OVER
        if v.phase == TablePhase.BETTING:
            self.bet_panel.set_limits(v.bet_min, v.bet_max)

    # -------------------------------------------------------------- draw

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        v = self.view
        surface.blit(a.image("table_background", LOGICAL_SIZE), (0, 0))
        self._draw_deck(surface, v)
        if v.dealer_cards:
            total = "?" if v.dealer_total is None else str(v.dealer_total)
            self._draw_hand(surface, v.dealer_cards, DEALER_Y, f"Dealer  {total}")
        if v.player_cards:
            self._draw_hand(surface, v.player_cards, PLAYER_Y, f"You  {v.player_total}")

        if v.phase == TablePhase.BETTING:
            self.bet_panel.draw(surface)
        elif v.phase in (TablePhase.ROUND_OVER, TablePhase.RUN_OVER) and v.last_result:
            self._draw_banner(surface, v)
        elif v.phase == TablePhase.CHAOS:
            self._draw_center_text(surface, "The Chaos AI is thinking...", theme.CHAOS_MAGENTA)
        elif v.phase == TablePhase.DEALER_TURN:
            self._draw_center_text(surface, "Dealer is playing...", theme.TEXT_MUTED)

        self.ui.draw(surface)
        self.feed.draw(surface)
        draw_status_bar(surface, a, v)

    def _draw_deck(self, surface: pygame.Surface, v: GameView) -> None:
        rect = deck_position()
        back = self.cards.back(CARD_SIZE)
        for i in range(3):
            surface.blit(back, rect.move(-i * 2, -i * 2))
        if v.deck_count:
            n = self.app.assets.font(theme.FONT_SMALL).render(f"{v.deck_count} left", True, theme.TEXT_MUTED)
            surface.blit(n, n.get_rect(midtop=(rect.centerx, rect.bottom + 8)))

    def _draw_hand(self, surface: pygame.Surface, cards, y: int, label: str) -> None:
        rects = layout_hand(len(cards), (W // 2, y))
        for card, rect in zip(cards, rects):
            shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=8)
            surface.blit(shadow, rect.move(3, 4))
            surface.blit(self.cards.render(card, rect.size), rect)
        font = self.app.assets.font(theme.FONT_BODY, bold=True)
        img = font.render(label, True, theme.IVORY)
        pos = (rects[0].left - 16, y) if rects else (W // 2, y)
        surface.blit(img, img.get_rect(midright=pos))

    def _draw_banner(self, surface: pygame.Surface, v: GameView) -> None:
        head, detail, color = outcome_banner(v.last_result)
        band = pygame.Surface((W, 66), pygame.SRCALPHA)
        band.fill((0, 0, 0, 170))
        surface.blit(band, (0, BANNER_Y - 33))
        a = self.app.assets
        h = a.font(theme.FONT_HEADING, bold=True).render(head, True, color)
        d = a.font(theme.FONT_BODY).render(detail, True, theme.TEXT)
        surface.blit(h, h.get_rect(midright=(W // 2 - 20, BANNER_Y)))
        surface.blit(d, d.get_rect(midleft=(W // 2 + 4, BANNER_Y)))

    def _draw_center_text(self, surface: pygame.Surface, text: str, color) -> None:
        img = self.app.assets.font(theme.FONT_BODY).render(text, True, color)
        surface.blit(img, img.get_rect(center=(W // 2, ACTION_Y + 28)))
