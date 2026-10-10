"""Three named player slots; selection never changes a balance profile."""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text, paragraph
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup


@register_scene("player_select")
class PlayerSelectScene(MetaScreen):
    title = "Choose your player"
    subtitle = "Three slots. Your tokens, upgrades and run history stay with your player."

    def on_enter(self, **params):
        self.setup()
        self.refresh()

    def refresh(self):
        self.slots = self.action(meta.list_slots) or []
        self.ui = WidgetGroup(Button(self.app.assets, (64, 640, 240, 52), "Main menu",
                                    lambda: self.app.scenes.reset("menu"), style="ghost", hotkey=pygame.K_ESCAPE))
        self.buttons = {}
        for slot in self.slots:
            x = 64 + (slot.slot - 1) * 392
            if slot.player is None:
                button = Button(self.app.assets, (x + 24, 433, 302, 56), "Create player",
                                lambda s=slot.slot: self.create(s))
                self.buttons[(slot.slot, "create")] = button
                self.ui.add(button)
                continue
            p = slot.player
            for key, rect, label, callback in (
                ("continue", (x + 24, 365, 302, 56), "Continue", lambda pid=p.id: self.open_player(pid)),
                ("rename", (x + 24, 441, 142, 48), "Rename", lambda p=p: self.rename(p)),
                ("delete", (x + 184, 441, 142, 48), "Delete", lambda p=p: self.delete(p)),
            ):
                b = Button(self.app.assets, rect, label, callback, style="primary" if key == "continue" else "ghost", font_size=20)
                self.buttons[(slot.slot, key)] = b
                self.ui.add(b)

    def open_player(self, player_id):
        self.navigate("hub", player_id=player_id)

    def create(self, slot):
        self.navigate("meta_name", title=f"Create player in slot {slot}",
                      on_submit=lambda name: meta.create_player(slot, name),
                      on_success=lambda player: self.app.scenes.push("hub", player_id=player.id))

    def rename(self, player):
        self.navigate("meta_name", title="Rename player", value=player.name,
                      on_submit=lambda name: meta.rename_player(player.id, name))

    def delete(self, player):
        self.navigate("confirm", message="Delete this player, upgrades and history?",
                      confirm_text="Delete", on_confirm=lambda: self.remove(player.id))

    def remove(self, player_id):
        self.action(lambda: meta.delete_player(player_id))
        self.refresh()

    def on_resume(self, result=None):
        super().on_resume(result)
        self.refresh()

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        for slot in self.slots:
            x = 64 + (slot.slot - 1) * 392
            panel(surface, (x, 160, 350, 390))
            text(surface, a, f"SLOT {slot.slot}", (x + 24, 185), size=16, color=theme.GOLD)
            p = slot.player
            text(surface, a, p.name if p else "Empty slot", (x + 24, 226), size=30, width=302)
            if p:
                text(surface, a, f"{p.tokens} tokens", (x + 24, 280), color=theme.GOLD)
                text(surface, a, f"{p.stats.runs} runs  /  {p.stats.victories} victories", (x + 24, 312), size=16, width=302)
                text(surface, a, f"Best bankroll: {p.stats.best_money}", (x + 24, 338), size=16, width=302)
            else:
                paragraph(surface, a, "A fresh start. Earn tokens by playing, then prepare your next run.",
                          (x + 24, 291, 302, 110))
        self.ui.draw(surface)
