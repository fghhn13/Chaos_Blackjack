"""Settle a player's finished run once and show its token breakdown and unlocks."""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.cosmetics import get_cosmetic
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import apply_loadout, draw_section
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text
from chaos_blackjack.gui.components.wardrobe import draw_look
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup, fit_text

UNLOCK_X, UNLOCK_W = 650, 470
CARD_H, CARD_GAP = 66, 10
MAX_CARDS = 5


@register_scene("run_result")
class RunResultScene(MetaScreen):
    def on_enter(self, run_id, player_id, controller, **params):
        self.setup()
        self.run_id, self.player_id, self.controller = run_id, player_id, controller
        self.reward = None
        self.equip_buttons = {}
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
            for i, u in enumerate(self.cards()):
                if self.looks(u):
                    y = 214 + i * (CARD_H + CARD_GAP)
                    b = Button(self.app.assets, (UNLOCK_X + UNLOCK_W - 112, y + (CARD_H - 38) // 2, 96, 38), "Equip",
                               lambda aid=u.achievement_id: self.equip(aid), style="ghost",
                               font_size=theme.FONT_SMALL, key_hint="")
                    self.equip_buttons[u.achievement_id] = b
                    self.ui.add(b)

    def cards(self):
        return self.reward.unlocked[:MAX_CARDS] if self.reward else ()

    @staticmethod
    def looks(unlock):
        """The new looks an unlock gave that this version knows."""
        return [c for c in map(get_cosmetic, unlock.cosmetic_ids) if c is not None]

    def equip(self, achievement_id):
        """Equip every look an achievement gave (one per slot)."""
        unlock = next(u for u in self.reward.unlocked if u.achievement_id == achievement_id)
        looks = self.looks(unlock)
        if all(self.action(lambda c=c: meta.equip(self.player_id, c.id)) is not None for c in looks):
            apply_loadout(self.app, self.player_id)
            button = self.equip_buttons[achievement_id]
            button.text, button.enabled = "Equipped", False
            slots = {c.slot for c in looks}
            for other_id, other in self.equip_buttons.items():
                other_unlock = next(u for u in self.reward.unlocked if u.achievement_id == other_id)
                if other_id != achievement_id and slots & {c.slot for c in self.looks(other_unlock)}:
                    other.text, other.enabled = "Equip", True

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
        a = self.app.assets
        unlocked = bool(self.reward and self.reward.unlocked)
        if unlocked:
            panel(surface, (120, 162, 1040, 420))
            left, value_x, width, step, top = 160, 560, 380, 32, 268
        else:
            panel(surface, (300, 162, 680, 394))
            left, value_x, width, step, top = 350, 860, 485, 40, 292
        if self.reward:
            text(surface, a, f"+{self.reward.tokens} tokens", (left, 200), size=48, color=theme.GOLD)
            for i, (label, amount) in enumerate(self.reward.breakdown):
                text(surface, a, label, (left, top + i * step), width=width, size=18 if unlocked else 20)
                text(surface, a, f"{amount:+d}", (value_x, top + i * step), color=theme.GOLD)
            text(surface, a, f"Total tokens: {self.reward.player.tokens}", (left, 520 if unlocked else 493),
                 size=24)
        if unlocked:
            self.draw_unlocks(surface)
        self.ui.draw(surface)

    def draw_unlocks(self, surface):
        a = self.app.assets
        draw_section(surface, a, "Achievements unlocked", (UNLOCK_X, 186), UNLOCK_W)
        for i, u in enumerate(self.cards()):
            card = pygame.Rect(UNLOCK_X, 214 + i * (CARD_H + CARD_GAP), UNLOCK_W, CARD_H)
            pygame.draw.rect(surface, (0x26, 0x2B, 0x24), card, border_radius=10)
            pygame.draw.rect(surface, theme.GOLD_DIM, card, 1, border_radius=10)
            looks = self.looks(u)
            look = looks[0] if looks else None
            x = card.x + 16
            if look is not None:
                draw_look(surface, a, look, pygame.Rect(x, card.y + 9, 72, CARD_H - 18))
                x += 86
            right = card.right - (124 if look is not None else 16)
            name_font = a.font(theme.FONT_BODY, bold=True)
            surface.blit(name_font.render(fit_text(name_font, u.name, right - x), True, theme.IVORY), (x, card.y + 10))
            parts = [f"+{u.tokens} tokens"] if u.tokens else []
            if looks:
                parts.append(("New look: " if len(looks) == 1 else "New looks: ") + ", ".join(c.name for c in looks))
            small = a.font(theme.FONT_SMALL)
            reward = fit_text(small, "  ·  ".join(parts), right - x)
            surface.blit(small.render(reward, True, theme.GOLD), (x, card.y + 38))
        extra = len(self.reward.unlocked) - MAX_CARDS
        if extra > 0:
            text(surface, a, f"+{extra} more in your Profile", (UNLOCK_X, 214 + MAX_CARDS * (CARD_H + CARD_GAP)),
                 size=theme.FONT_SMALL, color=theme.TEXT_MUTED)
