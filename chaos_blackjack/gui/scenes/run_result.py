"""Settle a player's finished run once and show its token breakdown."""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup


@register_scene("run_result")
class RunResultScene(MetaScreen):
    def on_enter(self, run_id, player_id, controller, **params):
        self.setup()
        self.run_id, self.player_id, self.controller = run_id, player_id, controller
        self.reward = None
        self.settle()

    def settle(self):
        if self.reward is not None:
            return
        self.message = ""
        self.reward = self.action(lambda: meta.finish_run(self.run_id, self.controller))
        victory = self.reward is not None and self.reward.result == "victory"
        self.title = "Victory" if victory else "Run complete" if self.reward else "Could not settle this run"
        self.subtitle = f"Final bankroll: {self.controller.run.money}  /  Rounds: {self.controller.last_result.round if self.controller.last_result else max(0, self.controller.run.round - 1)}"
        self.back = Button(self.app.assets, (470, 640, 340, 52), "Continue", self.back_to_hub,
                           enabled=self.reward is not None, hotkey=pygame.K_RETURN)
        self.ui = WidgetGroup(self.back)
        if self.reward is None:
            self.ui.add(Button(self.app.assets, (470, 520, 340, 52), "Retry", self.settle))
        else:
            self.title = "Victory" if victory else "Defeat"
            self.app.audio.play("ending_victory" if victory else "ending_bankrupt")

    def back_to_hub(self):
        if not self.leaving:
            self.leaving = True
            self.app.scenes.reset("home")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.reward:
            self.back_to_hub()
        else:
            super().handle_event(event)

    def draw(self, surface):
        super().draw(surface)
        panel(surface, (300, 162, 680, 394))
        a = self.app.assets
        if self.reward:
            text(surface, a, f"+{self.reward.tokens} tokens", (350, 200), size=48, color=theme.GOLD)
            for i, (label, amount) in enumerate(self.reward.breakdown):
                text(surface, a, label, (350, 292 + i * 40), width=485)
                text(surface, a, f"{amount:+d}", (860, 292 + i * 40), color=theme.GOLD)
            text(surface, a, f"Total tokens: {self.reward.player.tokens}", (350, 493), size=24)
        self.ui.draw(surface)
