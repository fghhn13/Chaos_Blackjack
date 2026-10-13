"""Table scene — plays a run through GameController.

The scene never decides rules. Controller snapshots and notice handlers stay
on the render thread. While chaos resolves in a worker, the scene renders its
cached snapshot without reading or mutating the controller. Dealer draws are
paced by a timer.

Extending:
  * new player action  -> add a row to ACTION_BUTTONS (+ controller method)
  * react to an event  -> self.subscribe(NoticeKind.X, handler)
  * new table information -> a part (app/parts.py) placed by the mode's layout
    (app/layout.py); the side columns and the run panel draw it.

Keys: Tab run panel, L its log, I its bag, 1-9 use an item (your turn), B shop.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import replace

import pygame

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import Action, GameView, TablePhase
from chaos_blackjack.contracts.chaos_interaction import PokeOutcome
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.bet_panel import BetPanel, draw_bet_stack
from chaos_blackjack.gui.components.cards import CARD_SIZE, CardRenderer, layout_hand
from chaos_blackjack.gui.components.chaos_panel import ChaosPanel
from chaos_blackjack.gui.components.hud import draw_status_bar
from chaos_blackjack.content.host_script import host_script
from chaos_blackjack.gui.components.intro import HostDialog
from chaos_blackjack.gui.components.side_column import (
    ButtonsBlock, DeckPileBlock, FeedBlock, HostBlock, SideColumn,
)
from chaos_blackjack.app.layout import layout_for
from chaos_blackjack.app.parts import PartContext
from chaos_blackjack.app.widgets import Act
from chaos_blackjack.gui.components.table_fx import TableFx
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import BAD, notice_line, outcome_banner
from chaos_blackjack.gui.widgets import Button, WidgetGroup
from chaos_blackjack.gui.worker import start_worker
from chaos_blackjack.modes import get_mode, intro_script

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
CHAOS_ERROR = "Chaos AI failed. Press Esc to leave the table."

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
    def on_enter(self, controller: GameController | None = None, intro: bool = False, **params) -> None:
        a = self.app.assets
        self.controller = controller or GameController(
            replace(self.app.run_config, enable_chaos=self.app.prefs.enable_chaos)
        )
        self.cards = CardRenderer(a)
        profile = self.controller.registry.resolve_ai(self.controller.config.ai_id)
        from chaos_blackjack.content.builtin_persona import host_persona
        config = self.controller.config
        persona = host_persona(config.host) if config.ai_id == "default" else getattr(profile, "persona", None)
        self.chaos_panel = ChaosPanel(a, LEFT_PANEL, self._poke, persona=persona)
        # The mode's host introduces a new run and comments on its end (AI_MODES.md §3);
        # resumed runs skip the introduction.
        self.persona = persona
        self.intro: HostDialog | None = None
        self.outro: HostDialog | None = None
        if intro and config.mode:
            try:
                table = self.controller.table
                beats = intro_script(get_mode(config.mode), config,
                                     summary=table.summary() if table is not None else None)
            except KeyError:
                beats = []
            if beats:
                self.intro = HostDialog(a, beats, persona)
        # Side columns: the mode's layout of parts (native blocks + widget parts).
        self.layout = layout_for(config.mode)
        self.deck_block = DeckPileBlock(a, self.cards, self._act, clickable=self.layout.tab("deck") is not None)
        self.feed_block = FeedBlock(a, self._act)
        self.buttons_block = ButtonsBlock(a, self._open_shop, self._open_panel)
        natives = {"core.host": HostBlock(self.chaos_panel), "core.deck_pile": self.deck_block,
                   "core.buttons": self.buttons_block, "core.feed": self.feed_block}
        self.left = SideColumn(a, LEFT_PANEL, self.layout.left, natives, self._act)
        self.right = SideColumn(a, RIGHT_PANEL, self.layout.right, natives, self._act)
        self.feed = self.feed_block.feed
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
        self._chaos_future: Future[None] | None = None
        self._chaos_failed = False
        self._closed = False
        self._poke_pending = False
        self._ending_opened = False
        self.view: GameView = self.controller.view()
        self.fx = TableFx(self.view, bankroll_anchor=(136, 24), dealer_anchor=(W // 2, DEALER_Y - 40),
                          audio=self.app.audio)
        self._handlers: dict[str, list[NoticeHandler]] = {}
        self.subscribe("*", self._feed_notice)
        self.subscribe("*", self.chaos_panel.react)
        self.subscribe("*", self.fx.react)
        self._sync_widgets()

    def on_exit(self) -> None:
        # In-flight network requests cannot be cancelled. The daemon finishes
        # against its old controller without touching this scene or delaying exit.
        self._closed = True
        self._chaos_future = None
        stop = getattr(self.app.audio, "stop", None)
        if stop is not None:
            stop()

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

    @property
    def deck_rect(self) -> pygame.Rect:
        """Where cards are dealt from (the shoe in the layout)."""
        return self.deck_block.pile_rect

    def _busy(self) -> bool:
        return self._closed or self._poke_pending or self._chaos_future is not None or self._chaos_failed

    def _open_panel(self, tab: str = "") -> None:
        if self._busy() or not self.layout.panel:
            return
        self.app.scenes.push("run_panel", controller=self.controller, layout=self.layout, tab=tab,
                             on_change=self._after_command)

    def _act(self, act: Act) -> None:
        """A clicked widget: GUI acts here, the rest through the controller."""
        if act.id == "gui:panel":
            self._open_panel(act.arg)
            return
        if self._busy() or not act.enabled:
            return
        try:
            result = self.controller.perform(act.id, act.arg)
            if getattr(result, "ok", True) is False and getattr(result, "message", ""):
                self.feed.push(result.message, BAD)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _quick_item(self, index: int) -> None:
        items = [i for i in self.view.items if i.count > 0]
        if index < len(items) and self.view.can(Action.USE_ITEM):
            self._use_item(items[index].id)

    def _command(self, method: str) -> Callable[[], None]:
        def run() -> None:
            if self._closed or self._poke_pending or self._chaos_future is not None or self._chaos_failed:
                return
            try:
                getattr(self.controller, method)()
            except ActionError as e:
                self.feed.push(str(e), BAD)
            self._after_command()

        return run

    def _deal(self, amount: int) -> None:
        if self._closed or self._poke_pending or self._chaos_future is not None or self._chaos_failed:
            return
        try:
            self.controller.place_bet(amount)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _use_item(self, item_id: str) -> None:
        if self._closed or self._poke_pending or self._chaos_future is not None or self._chaos_failed:
            return
        try:
            self.controller.use_item(item_id)
        except ActionError as e:
            self.feed.push(str(e), BAD)
        self._after_command()

    def _open_shop(self) -> None:
        if self._closed or self._poke_pending:
            return
        if self.view.can(Action.BUY):
            self.app.scenes.push("shop", controller=self.controller, on_change=self._after_command,
                                 on_poke=self._poke, portrait_rect=self.chaos_panel.portrait_rect)

    def _poke(self) -> bool:
        if self._closed or self._poke_pending or self._chaos_future is not None or self._chaos_failed:
            return False
        try:
            request = self.controller.prepare_poke()
        except ActionError:
            return False
        # Several queued clicks can arrive before push() is applied.
        self._poke_pending = True
        self.chaos_panel.poke_enabled = False
        self.app.scenes.push("chaos_poke", request=request, llm=self.controller.loop.pipeline.llm,
                             on_reply=self._accept_poke)
        return True

    def _accept_poke(self, outcome: PokeOutcome) -> None:
        if self._closed:
            return
        self._poke_pending = False
        self.controller.accept_poke_reply(outcome.request, outcome.reply)
        self._after_command()

    def _after_command(self) -> None:
        # Shop callbacks and modal resumes share this refresh path. A worker
        # owns the controller until update() consumes its completed result.
        if self._closed or self._poke_pending or self._chaos_future is not None or self._chaos_failed:
            return
        self._timer = 0.0
        prev = self.view
        self._pump_notices()
        self.view = self.controller.view()
        self.fx.view_changed(prev, self.view)
        self._sync_widgets()

    def on_resume(self, result=None) -> None:
        self._after_command()

    # ------------------------------------------------------------- frame

    def intro_open(self) -> bool:
        return self.dialog() is not None

    def dialog(self) -> HostDialog | None:
        """The host dialog that currently takes input, if any."""
        for d in (self.intro, self.outro):
            if d is not None and not d.done:
                return d
        return None

    def outro_finished(self) -> bool:
        """At the end of a run the host says a few lines first; True once they are
        done (or the host has nothing to say). Call only when the run is over."""
        if self.outro is None:
            v = self.view
            event = "victory" if v.run_end is not None and v.run_end.kind == "victory" else "defeat"
            config = self.controller.config
            host = config.host if config.ai_id == "default" else None
            beats = host_script(host, event, mode=config.mode) if config.ai_id == "default" else []
            self.outro = HostDialog(self.app.assets, beats, self.persona, finish="Enter for results")
        return self.outro.done
    def handle_event(self, event: pygame.event.Event) -> None:
        if self._closed or self._poke_pending:
            return
        if self.intro_open():
            self.dialog().handle_event(event)
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self._open_panel()
                return
            if event.key in (pygame.K_l, pygame.K_i):
                self._open_panel("log" if event.key == pygame.K_l else "bag")
                return
            if pygame.K_1 <= event.key <= pygame.K_9 and self.view.phase == TablePhase.PLAYER_TURN:
                self._quick_item(event.key - pygame.K_1)
                return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.scenes.push(
                "confirm",
                message="Return to the main menu? This run will be lost.",
                on_confirm=lambda: self.app.scenes.reset("home"),
            )
            return
        if self.right.handle_event(event) or self.left.handle_event(event):
            return
        if self.view.phase == TablePhase.BETTING:
            self.bet_panel.handle_event(event)
        else:
            self.ui.handle_event(event)

    def update(self, dt: float) -> None:
        if self._closed or self._poke_pending:
            return
        self.left.update(dt)
        self.right.update(dt)
        self.fx.update(dt)
        if self.fx.busy:
            return  # automatic steps wait for cards to land; input is never blocked
        self._timer += dt
        if self._chaos_future is not None:
            if self._chaos_future.done():
                result = self._chaos_future
                self._chaos_future = None
                try:
                    result.result()
                except Exception:
                    # Do not retry a potentially billed call or expose backend
                    # errors. Keep the cached table and allow leaving it.
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
            start_worker(_resolve_chaos, (self.controller, result), name="chaos-ai")
        elif phase == TablePhase.DEALER_TURN and self._timer >= DEALER_STEP_DELAY:
            self._command("dealer_step")()
        elif (phase == TablePhase.RUN_OVER and not self._ending_opened and self._timer >= RUN_END_DELAY
              and self.outro_finished()):
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
        ctx = PartContext(self.controller, v) if not self._busy() else None
        self.left.sync(v, ctx)
        self.right.sync(v, ctx)

    # -------------------------------------------------------------- draw

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        v = self.view
        surface.blit(a.image("table_background", LOGICAL_SIZE), (0, 0))
        self.left.draw(surface)
        self.right.draw(surface)
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
            if self._chaos_failed:
                self._draw_center_text(surface, CHAOS_ERROR, BAD)
            else:
                self._draw_chaos_thinking(surface)
        elif v.phase == TablePhase.DEALER_TURN:
            self._draw_center_text(surface, "Dealer is playing...", theme.TEXT_MUTED)

        self.ui.draw(surface)
        draw_status_bar(surface, a, v, money=self.fx.money_shown())
        self.fx.apply_glitch(surface)
        self.left.draw_overlay(surface)
        self.right.draw_overlay(surface)
        if self.intro_open():
            self.dialog().draw(surface)

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
        deck = self.deck_rect
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

    def _draw_chaos_thinking(self, surface: pygame.Surface) -> None:
        """Procedural placeholder animation; no additional art is required."""
        img = self.app.assets.font(theme.FONT_BODY).render(
            f"{self.chaos_panel.persona.name if self.chaos_panel.persona else 'Chaos AI'} is thinking...", True, theme.CHAOS_MAGENTA,
        )
        surface.blit(img, img.get_rect(center=(W // 2, ACTION_Y + 14)))
        active = int(self._timer / 0.25) % 3
        for i in range(3):
            color = theme.CHAOS_MAGENTA if i == active else theme.CHAOS_PURPLE
            radius = 5 if i == active else 3
            pygame.draw.circle(surface, color, (W // 2 + (i - 1) * 18, ACTION_Y + 42), radius)
