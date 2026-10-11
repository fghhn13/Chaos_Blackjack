"""Reuse the table presentation while routing a player's run to meta results."""

import sqlite3

import pygame

from chaos_blackjack import meta
from chaos_blackjack.app.controller import ActionError
from chaos_blackjack.app.view import Action, TablePhase
from chaos_blackjack.content.ai_profile import build_pipeline
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.scenes.table import TableScene, RUN_END_DELAY
from chaos_blackjack.gui.texts import BAD
from chaos_blackjack.registry import get_registry


def run_loop_factory(app):
    """Preserve the GUI's explicit backend choice when the API builds a run."""
    choice = app.run_config.use_llm
    pipeline = build_pipeline("default", get_registry(), use_llm=choice)
    return lambda dispatcher: GameLoop(dispatcher=dispatcher, pipeline=pipeline)


@register_scene("meta_table")
class MetaTableScene(TableScene):
    def on_enter(self, started, player_id, **params):
        self.run_id, self.player_id = started.run_id, player_id
        self.finishing = False
        self.abandoned = False
        self.exit_pending = False
        self.save_name = f"player-{player_id}-run-{self.run_id}"
        super().on_enter(controller=started.controller)
        self.checkpoint()

    def checkpoint(self):
        if (self._closed or self._poke_pending or self._chaos_future is not None
                or self._chaos_failed or not self.view.can(Action.SAVE)):
            return
        try:
            self.controller.save(self.save_name)
        except (ActionError, sqlite3.Error, OSError):
            self.feed.push("Could not save this run. Your current game can continue.", BAD)

    def _after_command(self):
        super()._after_command()
        self.checkpoint()

    def handle_event(self, event):
        if self._closed or self._poke_pending or self.exit_pending:
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.exit_pending = True
            self.app.scenes.push("confirm", message="Abandon this run and return to the main menu?",
                                 on_confirm=self.abandon, confirm_text="Abandon")
            return
        super().handle_event(event)

    def abandon(self):
        try:
            meta.abandon_run(self.run_id)
        except (meta.MetaError, sqlite3.Error, OSError) as exc:
            self.feed.push(str(exc), BAD)
            return
        self.abandoned = True
        self.app.scenes.reset("home")

    def on_resume(self, result=None):
        self.exit_pending = False
        super().on_resume(result)

    def update(self, dt):
        if self.view.phase != TablePhase.RUN_OVER:
            super().update(dt)
            return
        if self._closed or self._ending_opened:
            return
        self.feed.update(dt)
        self.fx.update(dt)
        self.chaos_panel.update(dt)
        if self.fx.busy:
            return
        self._timer += dt
        if self._timer >= RUN_END_DELAY:
            self._ending_opened = self.finishing = True
            self.app.scenes.replace("run_result", run_id=self.run_id,
                                    player_id=self.player_id, controller=self.controller)

    def on_exit(self):
        super().on_exit()
        if not self.finishing and not self.abandoned:
            # Explicit scene navigation abandons the run; closing the application
            # leaves its latest checkpoint available through resume_run.
            meta.abandon_run(self.run_id)
