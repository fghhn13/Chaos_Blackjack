"""Home: title, the current player and the next step, over the dealer's table.

The menu adapts to the player's state:
  - no players yet:   Start game (creates a player, then opens run setup);
                      Upgrades, Run history and the badge explain that they
                      need a player and point at Start game
  - unfinished run:   Continue run (with a summary) above New run
  - otherwise:        New run
Upgrades, Collection and Run history follow; Settings and Quit sit low.
"""

from __future__ import annotations

import math
import sqlite3

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import (
    DealerScene, EmptyBadge, MenuItem, PlayerBadge, TextButton, choose_player, current_player, draw_backdrop,
    draw_left_fade, draw_paragraph, run_summary,
)
from chaos_blackjack.gui.components.meta_run import run_loop_factory
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import WidgetGroup

W, H = LOGICAL_SIZE
MENU_X = 80
MENU_W = 430
FADE_IN = 0.25
POINT_TIME = 3.0  # how long Start game is highlighted after a "needs a player" click
NEED_PLAYER = "Tokens, upgrades and run history are kept by a player. Create one with Start game above."

_ERRORS = (ValueError, sqlite3.Error, OSError)


@register_scene("home")
class HomeScene(Scene):
    def on_enter(self, message: str = "", **params) -> None:
        self.dealer = DealerScene(self.app.assets)
        self.message = message
        self.busy = False
        self.age = 0.0
        self.point = 0.0
        self.refresh()

    # ---------------------------------------------------------------- state

    def refresh(self) -> None:
        self.player = current_player(self.app)
        self.pending = None
        if self.player is not None:
            try:
                self.pending = meta.pending_run(self.player.id)
            except _ERRORS:
                self.pending = None
            if self.pending is not None and self.pending.run_id in self.app.session.get("broken_runs", set()):
                self.pending = None
        self.build()

    def build(self) -> None:
        a = self.app.assets
        self.ui = WidgetGroup(keyboard=True)
        self.entries: dict[str, MenuItem] = {}
        y = 268

        def entry(key, text, callback, weight, height, detail="", chaos=False, note=""):
            nonlocal y
            item = MenuItem(a, (MENU_X, y, MENU_W, height), text, callback, weight=weight, detail=detail,
                            chaos=chaos, note=note)
            self.entries[key] = item
            self.ui.add(item)
            y += height + (18 if weight == "primary" else 6)
            return item

        if self.player is None:
            entry("start", "Start game", self.start_game, "primary", 84, "Create your player and take a seat.")
            y += 6
            entry("upgrades", "Upgrades", self.need_player, "secondary", 46, note="Needs a player")
            entry("codex", "Collection", self.open_collection, "secondary", 46)
            entry("history", "Run history", self.need_player, "secondary", 46, note="Needs a player")
        else:
            if self.pending is not None:
                entry("continue", "Continue run", self.continue_run, "primary", 84, run_summary(self.pending),
                      chaos=self.pending.mode == "chaos")
                entry("new", "New run", self.new_run, "secondary", 46)
            else:
                entry("new", "New run", self.new_run, "primary", 84, "Choose a table and take a seat.")
            y += 6
            entry("upgrades", "Upgrades", lambda: self.open("meta_shop", player_id=self.player.id), "secondary", 46)
            entry("codex", "Collection", self.open_collection, "secondary", 46)
            entry("history", "Run history", lambda: self.open("history", player_id=self.player.id), "secondary", 46)
        self.settings = TextButton(a, (MENU_X, 648, 120, 40), "Settings", lambda: self.open("meta_settings"))
        self.quit = TextButton(a, (MENU_X + 150, 648, 120, 40), "Quit", self.ask_quit, hotkey=pygame.K_ESCAPE)
        self.ui.add(self.settings)
        self.ui.add(self.quit)
        if self.player is not None:
            self.badge = PlayerBadge(a, self.player, lambda: self.open("player_select"))
        else:
            self.badge = EmptyBadge(a, self.need_player)
        self.ui.add(self.badge)

    # ---------------------------------------------------------------- actions

    def open(self, name: str, **params) -> None:
        if not self.busy:
            self.busy = True
            self.app.scenes.push(name, **params)

    def open_collection(self) -> None:
        self.open("codex", player_id=self.player.id if self.player else None, config=self.app.run_config)

    def new_run(self) -> None:
        self.open("run_setup", player_id=self.player.id)

    def start_game(self) -> None:
        free = next((s.slot for s in meta.list_slots() if s.player is None), None)
        if free is None:
            self.open("player_select")
            return

        def created(player):
            choose_player(self.app, player.id)
            self.app.scenes.push("run_setup", player_id=player.id)

        self.open("meta_name", title="Name your player", on_submit=lambda name: meta.create_player(free, name),
                  on_success=created)

    def continue_run(self) -> None:
        if self.busy or self.player is None:
            return
        try:
            started = meta.resume_run(self.player.id, loop_factory=run_loop_factory(self.app))
        except Exception:  # a corrupt or incompatible save must not crash the menu
            started = None
        if started is None:
            if self.pending is not None:
                self.app.session.setdefault("broken_runs", set()).add(self.pending.run_id)
            self.message = "That run could not be restored. Start a new run instead."
            self.refresh()
            return
        self.busy = True
        self.app.scenes.push("meta_table", started=started, player_id=self.player.id)

    def need_player(self) -> None:
        """A player-only entry was chosen before any player exists: explain, and
        point at Start game (highlight + keyboard focus, so Enter creates one)."""
        self.message = NEED_PLAYER
        self.point = POINT_TIME
        self.ui.set_focus(self.entries["start"])

    def ask_quit(self) -> None:
        self.open("confirm", message="Leave the table and quit?", confirm_text="Quit",
                  on_confirm=self.app.quit)

    # ---------------------------------------------------------------- frame

    def on_resume(self, result=None) -> None:
        self.busy = False
        self.refresh()

    def handle_event(self, event) -> None:
        if not self.busy:
            self.ui.handle_event(event)

    def update(self, dt: float) -> None:
        self.age += dt
        self.point = max(0.0, self.point - dt)
        self.dealer.update(dt)
        self.ui.update(dt)

    def draw(self, surface) -> None:
        a = self.app.assets
        draw_backdrop(surface, a, shade=70)
        self.dealer.draw(surface)
        draw_left_fade(surface)
        title = a.font(theme.FONT_TITLE + 8, role="display")
        surface.blit(title.render("Chaos", True, theme.GOLD), (MENU_X - 4, 70))
        surface.blit(title.render("Blackjack", True, theme.IVORY), (MENU_X - 4, 136))
        tagline = a.font(theme.FONT_BODY).render("The dealer bends the rules. Sit down anyway.", True,
                                                 theme.CHAOS_MAGENTA)
        surface.blit(tagline, (MENU_X, 222))
        self.ui.draw(surface)
        if self.point > 0 and "start" in self.entries:
            self.draw_pointer(surface, self.entries["start"].rect)
        if self.message:
            last = max((e.rect.bottom for e in self.entries.values()), default=500)
            draw_paragraph(surface, a, self.message, (MENU_X, last + 18, MENU_W, 44), color=theme.CHAOS_MAGENTA)
        if self.age < FADE_IN:
            veil = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1 - self.age / FADE_IN))))
            surface.blit(veil, (0, 0))

    def draw_pointer(self, surface, rect) -> None:
        """Pulsing gold outline and a "Start here" tag beside Start game."""
        a = self.app.assets
        pulse = 0.5 + 0.5 * math.sin((POINT_TIME - self.point) * 7)
        ring = rect.inflate(14 + int(pulse * 8), 14 + int(pulse * 8))
        pygame.draw.rect(surface, theme.GOLD, ring, 2, border_radius=16)
        tag = a.font(theme.FONT_SMALL, bold=True).render("‹  Start here", True, theme.GOLD)
        surface.blit(tag, tag.get_rect(midleft=(ring.right + 14 + int(pulse * 6), rect.centery)))
