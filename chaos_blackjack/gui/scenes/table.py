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
from chaos_blackjack.gui.components.bet_panel import BetPanel, draw_bet_stack
from chaos_blackjack.gui.components.cards import CARD_SIZE, CardRenderer, layout_hand
from chaos_blackjack.gui.components.chaos_panel import ChaosPanel
from chaos_blackjack.gui.components.hud import EventFeed, draw_status_bar
from chaos_blackjack.gui.components.item_panel import ItemPanel
from chaos_blackjack.gui.components.table_fx import TableFx
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

# (action id, label, hotkey, style, controller method)
ACTION_BUTTONS: tuple[tuple[str, str, int, str, str], ...] = (
    (Action.HIT, "Hit", pygame.K_h, "primary", "hit"),
    (Action.STAND, "Stand", pygame.K_s, "primary", "stand"),
    (Action.DOUBLE, "Double", pygame.K_d, "primary", "double_down"),
    (Action.SURRENDER, "Surrender", pygame.K_r, "ghost", "surrender"),
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
        self.chaos_panel = ChaosPanel(a, LEFT_PANEL)
        self.item_panel = ItemPanel(a, RIGHT_PANEL, self._use_item)
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

        self._timer = 0.0
        self._ending_opened = False
        self.view: GameView = self.controller.view()
        self.fx = TableFx(self.view, bankroll_anchor=(136, 24), dealer_anchor=(W // 2, DEALER_Y - 40))
        self._handlers: dict[str, list[NoticeHandler]] = {}
        self.subscribe("*", self._feed_notice)
        self.subscribe("*", self.chaos_panel.react)
        self.subscribe("*", self.fx.react)
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

    def _use_item(self, item_id: str) -> None:
        try:
            self.controller.use_item(item_id)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _after_command(self) -> None:
        self._timer = 0.0
        prev = self.view
        self._pump_notices()
        self.view = self.controller.view()
        self.fx.view_changed(prev, self.view)
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
        self.feed.update(dt)
        self.fx.update(dt)
        self.chaos_panel.update(dt)
        if self.fx.busy:
            return  # automatic steps wait for cards to land; input is never blocked
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
        if v.dealer_cards:
            total = "?" if v.dealer_total is None else str(v.dealer_total)
            self._draw_hand(surface, v.dealer_cards, DEALER_Y, "dealer", total)
        if v.player_cards:
            self._draw_hand(surface, v.player_cards, PLAYER_Y, "player", str(v.player_total))
        self._draw_bet_zone(surface, v)  # after the hands: settling chips fly over the cards

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
        draw_status_bar(surface, a, v, money=self.fx.money_shown())
        self.fx.apply_glitch(surface)
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
        if v.phase in (TablePhase.ROUND_OVER, TablePhase.RUN_OVER):
            settled = self.fx.settle_position(STACK_CENTER)
            if settled is None:
                return  # chips have gone to the winner
            pos, amount, alpha = settled
            if amount or v.current_bet:
                draw_bet_stack(surface, self.app.assets, amount or v.current_bet, pos, alpha=alpha)
        elif v.player_cards and v.current_bet:
            x, y = STACK_CENTER
            draw_bet_stack(surface, self.app.assets, v.current_bet, (x, y + self.fx.chip_drop_offset()))

    def _draw_hand(self, surface: pygame.Surface, cards, y: int, hand: str, total: str) -> None:
        rects = layout_hand(len(cards), (W // 2, y), max_width=HAND_MAX_WIDTH)
        deck = self.item_panel.deck_rect
        for i, (card, rect) in enumerate(zip(cards, rects)):
            self.fx.draw_card(surface, self.cards, card, (hand, i), rect, deck)
        # Name + total pill above the hand.
        a = self.app.assets
        who = "You" if hand == "player" else "Dealer"
        if self.fx.hand_moving(hand):
            total = "…"  # don't give the total away before the cards land
        name = a.font(theme.FONT_SMALL, bold=True).render(who.upper(), True, theme.GOLD_DIM)
        value = a.font(theme.FONT_BODY, bold=True).render(total, True, theme.IVORY)
        pill = pygame.Rect(0, 0, name.get_width() + value.get_width() + 34, 30)
        pill.midbottom = (W // 2, y - CARD_SIZE[1] // 2 - 8)
        pygame.draw.rect(surface, theme.DARK, pill, border_radius=15)
        pygame.draw.rect(surface, theme.GOLD_DIM, pill, 1, border_radius=15)
        surface.blit(name, name.get_rect(midleft=(pill.x + 12, pill.centery)))
        surface.blit(value, value.get_rect(midright=(pill.right - 12, pill.centery)))

    def _draw_banner(self, surface: pygame.Surface, v: GameView) -> None:
        p = self.fx.banner_progress()
        if p <= 0:
            return
        fade = min(1.0, p)
        rise = round((1 - p) * 14)  # out_back overshoots, so the text settles with a small bounce
        head, detail, color = outcome_banner(v.last_result)
        width = CENTER_RIGHT - CENTER_LEFT
        band = pygame.Surface((width, 72), pygame.SRCALPHA)
        band.fill((*theme.DARK, round(215 * fade)))
        surface.blit(band, (CENTER_LEFT, BANNER_Y - 36))
        line_w = round(width * fade)
        pygame.draw.line(surface, color, (W // 2 - line_w // 2, BANNER_Y - 36), (W // 2 + line_w // 2, BANNER_Y - 36), 2)
        a = self.app.assets
        h = a.font(theme.FONT_HEADING, role="display").render(head, True, color)
        d = a.font(theme.FONT_BODY).render(detail, True, theme.TEXT)
        h.set_alpha(round(255 * fade))
        d.set_alpha(round(255 * fade))
        surface.blit(h, h.get_rect(midbottom=(W // 2, BANNER_Y + 6 + rise)))
        surface.blit(d, d.get_rect(midtop=(W // 2, BANNER_Y + 8 + rise)))

    def _draw_center_text(self, surface: pygame.Surface, text: str, color) -> None:
        img = self.app.assets.font(theme.FONT_BODY).render(text, True, color)
        surface.blit(img, img.get_rect(center=(W // 2, ACTION_Y + 28)))
