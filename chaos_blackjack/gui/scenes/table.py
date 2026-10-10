"""Table scene — plays a run through GameController.

The scene never decides rules. Controller snapshots and notice handlers stay
on the render thread. While chaos resolves in a worker, the scene renders its
cached snapshot without reading or mutating the controller. Dealer draws are
paced by a timer.

Extending:
  * new player action  -> add a row to ACTION_BUTTONS (+ controller method)
  * react to an event  -> self.subscribe(NoticeKind.X, handler)
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from threading import Thread

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import Action, GameView, TablePhase
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.bet_panel import BetPanel, draw_bet_stack
from chaos_blackjack.gui.components.cards import CARD_SIZE, CardRenderer, layout_hand
from chaos_blackjack.gui.components.chaos_panel import ChaosPanel
from chaos_blackjack.gui.components.hud import EventFeed, draw_status_bar
from chaos_blackjack.gui.components.item_panel import ItemPanel
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import BAD, notice_line, outcome_banner
from chaos_blackjack.gui.widgets import Button, WidgetGroup

W, H = LOGICAL_SIZE

# Three columns: Chaos AI + rules | play area | shoe + items.
LEFT_PANEL = pygame.Rect(16, 60, 240, 644)
RIGHT_PANEL = pygame.Rect(W - 16 - 240, 60, 240, 644)
CENTER_LEFT, CENTER_RIGHT = LEFT_PANEL.right + 16, RIGHT_PANEL.left - 16
HAND_MAX_WIDTH = CENTER_RIGHT - CENTER_LEFT - 80

DEALER_Y = 192   # card centres
PLAYER_Y = 510
BET_ZONE = pygame.Rect(0, 0, 300, 80)
BET_ZONE.center = (W // 2, 332)
STACK_CENTER = (BET_ZONE.centerx, BET_ZONE.centery + 6)
BANNER_Y = BET_ZONE.centery
ACTION_Y = 616
FEED_LINE = 22  # px per event-feed line

DEALER_STEP_DELAY = 0.7  # seconds between dealer decisions
CHAOS_DELAY = 0.4        # pause before the chaos AI acts
RUN_END_DELAY = 1.5      # let the last result sink in before the ending
CHAOS_ERROR = "Chaos AI failed. Press Esc to return to the menu."

# (action id, label, hotkey, style, controller method)
ACTION_BUTTONS: tuple[tuple[str, str, int, str, str], ...] = (
    (Action.HIT, "Hit", pygame.K_h, "primary", "hit"),
    (Action.STAND, "Stand", pygame.K_s, "primary", "stand"),
    (Action.DOUBLE, "Double", pygame.K_d, "primary", "double_down"),
    (Action.SURRENDER, "Surrender", pygame.K_r, "ghost", "surrender"),
)

NoticeHandler = Callable[[Notice], None]


def _resolve_chaos(controller: GameController, result: Future[None]) -> None:
    """Own the controller until completion; never call Pygame or scene handlers."""
    try:
        controller.resolve_chaos()
    except Exception as exc:
        result.set_exception(exc)
    else:
        result.set_result(None)


@register_scene("table")
class TableScene(Scene):
    def on_enter(self, controller: GameController | None = None, **params) -> None:
        a = self.app.assets
        self.controller = controller or GameController(
            RunConfig(enable_chaos=self.app.prefs.enable_chaos)
        )
        self.cards = CardRenderer(a)
        self.chaos_panel = ChaosPanel(a, LEFT_PANEL)
        self.item_panel = ItemPanel(a, RIGHT_PANEL, self._use_item, self._open_shop)
        log = self.chaos_panel.log_area
        self.feed = EventFeed(a, log.topleft, max_lines=log.h // FEED_LINE, max_width=log.w, align_top=True)
        self.bet_panel = BetPanel(a, (W // 2, ACTION_Y + 30), self._deal, initial=10,
                                  stack_center=STACK_CENTER)

        bw, gap = 160, 16
        x0 = W // 2 - (len(ACTION_BUTTONS) * (bw + gap) - gap) // 2
        self.action_buttons: dict[str, Button] = {}
        for i, (action, label, key, style, method) in enumerate(ACTION_BUTTONS):
            self.action_buttons[action] = Button(
                a, (x0 + i * (bw + gap), ACTION_Y, bw, 56), label,
                self._command(method), style=style, hotkey=key,
            )
        self.next_button = Button(a, (W // 2 - 100, ACTION_Y, 200, 56), "Next Round",
                                  self._command("next_round"), hotkey=pygame.K_RETURN)
        self.ui = WidgetGroup(*self.action_buttons.values(), self.next_button)

        self._handlers: dict[str, list[NoticeHandler]] = {}
        self.subscribe("*", self._feed_notice)
        self.subscribe("*", self.chaos_panel.react)
        self._timer = 0.0
        self._chaos_future: Future[None] | None = None
        self._chaos_failed = False
        self._closed = False
        self._ending_opened = False
        self.view: GameView = self.controller.view()
        self._sync_widgets()

    def on_exit(self) -> None:
        # In-flight network requests cannot be cancelled. The daemon finishes
        # against its old controller without touching this scene or delaying exit.
        self._closed = True
        self._chaos_future = None

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
            if self._closed or self._chaos_future is not None or self._chaos_failed:
                return
            try:
                getattr(self.controller, method)()
            except ActionError as e:
                self.feed.push(str(e), BAD)
            self._after_command()

        return run

    def _deal(self, amount: int) -> None:
        if self._closed or self._chaos_future is not None or self._chaos_failed:
            return
        try:
            self.controller.place_bet(amount)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _use_item(self, item_id: str) -> None:
        if self._closed or self._chaos_future is not None or self._chaos_failed:
            return
        try:
            self.controller.use_item(item_id)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _open_shop(self) -> None:
        if self.view.can(Action.BUY):
            self.app.scenes.push("shop", controller=self.controller, on_change=self._after_command)

    def on_resume(self, result=None) -> None:
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
        if self.item_panel.handle_event(event):
            return
        self.chaos_panel.handle_event(event)
        if self.view.phase == TablePhase.BETTING:
            self.bet_panel.handle_event(event)
        else:
            self.ui.handle_event(event)

    def update(self, dt: float) -> None:
        if self._closed:
            return
        self.feed.update(dt)
        self._timer += dt
        if self._chaos_future is not None:
            if self._chaos_future.done():
                result = self._chaos_future
                self._chaos_future = None
                try:
                    result.result()
                except Exception:
                    # Do not retry a potentially billed call or expose backend
                    # errors. Keep the cached table and allow returning to menu.
                    self._chaos_failed = True
                    self.feed.push(CHAOS_ERROR, BAD)
                else:
                    self._after_command()
            return
        phase = self.view.phase
        if phase == TablePhase.CHAOS and not self._chaos_failed and self._timer >= CHAOS_DELAY:
            result = Future()
            self._chaos_future = result
            # A daemon avoids waiting for a slow network request at app shutdown.
            Thread(target=_resolve_chaos, args=(self.controller, result),
                   name="chaos-ai", daemon=True).start()
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
        self.chaos_panel.sync(v)
        self.item_panel.sync(v)
        log = self.chaos_panel.log_area
        self.feed.anchor = log.topleft
        self.feed.max_lines = max(2, log.h // FEED_LINE)

    # -------------------------------------------------------------- draw

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        v = self.view
        surface.blit(a.image("table_background", LOGICAL_SIZE), (0, 0))
        self.chaos_panel.draw(surface)
        self.item_panel.draw(surface)
        self._draw_deck(surface, v)
        self._draw_bet_zone(surface, v)
        if v.dealer_cards:
            total = "?" if v.dealer_total is None else str(v.dealer_total)
            self._draw_hand(surface, v.dealer_cards, DEALER_Y, "Dealer", total)
        if v.player_cards:
            self._draw_hand(surface, v.player_cards, PLAYER_Y, "You", str(v.player_total))

        if v.phase == TablePhase.BETTING:
            self.bet_panel.draw(surface)
        elif v.phase in (TablePhase.ROUND_OVER, TablePhase.RUN_OVER) and v.last_result:
            self._draw_banner(surface, v)
        elif v.phase == TablePhase.CHAOS:
            if self._chaos_failed:
                self._draw_center_text(surface, CHAOS_ERROR, BAD)
            else:
                self._draw_chaos_thinking(surface)
        elif v.phase == TablePhase.DEALER_TURN:
            self._draw_center_text(surface, "Dealer is playing...", theme.TEXT_MUTED)

        self.ui.draw(surface)
        self.feed.draw(surface)
        draw_status_bar(surface, a, v)
        self.chaos_panel.draw_overlay(surface)
        self.item_panel.draw_overlay(surface)

    def _draw_deck(self, surface: pygame.Surface, v: GameView) -> None:
        rect = self.item_panel.deck_rect
        back = self.cards.back(CARD_SIZE)
        for i in range(3):
            surface.blit(back, rect.move(-i * 2, -i * 2))
        if v.deck_count:
            n = self.app.assets.font(theme.FONT_SMALL).render(f"{v.deck_count} cards left", True, theme.TEXT_MUTED)
            surface.blit(n, n.get_rect(midtop=(rect.centerx, rect.bottom + 8)))

    def _draw_bet_zone(self, surface: pygame.Surface, v: GameView) -> None:
        """Betting circle on the felt; shows the wager while a round is live."""
        zone = pygame.Surface(BET_ZONE.size, pygame.SRCALPHA)
        pygame.draw.ellipse(zone, (0, 0, 0, 40), zone.get_rect())
        pygame.draw.ellipse(zone, (*theme.GOLD_DIM, 160), zone.get_rect(), 2)
        surface.blit(zone, BET_ZONE)
        if v.phase == TablePhase.BETTING:
            return  # the bet panel draws the pending amount here
        if v.player_cards and v.current_bet:
            draw_bet_stack(surface, self.app.assets, v.current_bet, STACK_CENTER)

    def _draw_hand(self, surface: pygame.Surface, cards, y: int, who: str, total: str) -> None:
        rects = layout_hand(len(cards), (W // 2, y), max_width=HAND_MAX_WIDTH)
        for card, rect in zip(cards, rects):
            shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=8)
            surface.blit(shadow, rect.move(3, 4))
            surface.blit(self.cards.render(card, rect.size), rect)
        # Name + total pill above the hand.
        a = self.app.assets
        name = a.font(theme.FONT_SMALL, bold=True).render(who.upper(), True, theme.GOLD_DIM)
        value = a.font(theme.FONT_BODY, bold=True).render(total, True, theme.IVORY)
        pill = pygame.Rect(0, 0, name.get_width() + value.get_width() + 34, 30)
        pill.midbottom = (W // 2, y - CARD_SIZE[1] // 2 - 8)
        pygame.draw.rect(surface, theme.DARK, pill, border_radius=15)
        pygame.draw.rect(surface, theme.GOLD_DIM, pill, 1, border_radius=15)
        surface.blit(name, name.get_rect(midleft=(pill.x + 12, pill.centery)))
        surface.blit(value, value.get_rect(midright=(pill.right - 12, pill.centery)))

    def _draw_banner(self, surface: pygame.Surface, v: GameView) -> None:
        head, detail, color = outcome_banner(v.last_result)
        width = CENTER_RIGHT - CENTER_LEFT
        band = pygame.Surface((width, 72), pygame.SRCALPHA)
        band.fill((*theme.DARK, 215))
        surface.blit(band, (CENTER_LEFT, BANNER_Y - 36))
        pygame.draw.line(surface, color, (CENTER_LEFT, BANNER_Y - 36), (CENTER_RIGHT - 1, BANNER_Y - 36), 2)
        a = self.app.assets
        h = a.font(theme.FONT_HEADING, role="display").render(head, True, color)
        d = a.font(theme.FONT_BODY).render(detail, True, theme.TEXT)
        surface.blit(h, h.get_rect(midbottom=(W // 2, BANNER_Y + 6)))
        surface.blit(d, d.get_rect(midtop=(W // 2, BANNER_Y + 8)))

    def _draw_center_text(self, surface: pygame.Surface, text: str, color) -> None:
        img = self.app.assets.font(theme.FONT_BODY).render(text, True, color)
        surface.blit(img, img.get_rect(center=(W // 2, ACTION_Y + 28)))

    def _draw_chaos_thinking(self, surface: pygame.Surface) -> None:
        """Procedural placeholder animation; no additional art is required."""
        img = self.app.assets.font(theme.FONT_BODY).render(
            "The Chaos AI is thinking...", True, theme.CHAOS_MAGENTA,
        )
        surface.blit(img, img.get_rect(center=(W // 2, ACTION_Y + 14)))
        active = int(self._timer / 0.25) % 3
        for i in range(3):
            color = theme.CHAOS_MAGENTA if i == active else theme.CHAOS_PURPLE
            radius = 5 if i == active else 3
            pygame.draw.circle(surface, color, (W // 2 + (i - 1) * 18, ACTION_Y + 42), radius)
