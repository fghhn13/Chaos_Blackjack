"""Save management: three player slots behind the home screen's player badge.

Play makes a slot the current player and returns home; Create, Rename and
Delete (with confirmation) live here only. Selection never changes a
balance profile.
"""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import (
    MARGIN, back_button, choose_player, current_player, draw_glow, run_summary,
)
from chaos_blackjack.gui.components.meta_screen import MetaScreen, text
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup, fit_text

ROW_Y = 150
ROW_H = 128
ROW_GAP = 18
ROW_W = 1152


@register_scene("player_select")
class PlayerSelectScene(MetaScreen):
    title = "Players"
    subtitle = "Three save slots. Tokens, upgrades and run history belong to each player."

    def on_enter(self, **params):
        self.setup()
        self.refresh()

    def refresh(self):
        self.slots = self.action(meta.list_slots) or []
        current = current_player(self.app)
        self.current_id = current.id if current else None
        self.pending = {}
        for slot in self.slots:
            if slot.player is not None:
                self.pending[slot.slot] = self.action(lambda p=slot.player: meta.pending_run(p.id))
        a = self.app.assets
        self.ui = WidgetGroup(back_button(a, self.app.scenes.pop), keyboard=True)
        self.buttons = {}
        for slot in self.slots:
            y = ROW_Y + (slot.slot - 1) * (ROW_H + ROW_GAP)
            right = MARGIN + ROW_W - 24
            if slot.player is None:
                actions = (("create", "Create player", 220, lambda s=slot.slot: self.create(s), "primary"),)
            else:
                p = slot.player
                playing = p.id == self.current_id
                actions = (
                    ("delete", "Delete", 120, lambda p=p: self.delete(p), "ghost"),
                    ("rename", "Rename", 120, lambda p=p: self.rename(p), "ghost"),
                    ("continue", "Playing" if playing else "Play", 150, lambda pid=p.id: self.select(pid),
                     "primary"),
                )
            for key, label, width, callback, style in actions:
                b = Button(a, (right - width, y + (ROW_H - 50) // 2, width, 50), label, callback, style=style,
                           font_size=theme.FONT_BODY, key_hint="")
                if key == "continue" and slot.player.id == self.current_id:
                    b.selected = True
                right -= width + 12
                self.buttons[(slot.slot, key)] = b
            # Primary first for keyboard order.
            for key in ("continue", "create", "rename", "delete"):
                if (slot.slot, key) in self.buttons:
                    self.ui.add(self.buttons[(slot.slot, key)])

    def select(self, player_id):
        if self.leaving:
            return
        choose_player(self.app, player_id)
        self.leaving = True
        self.app.scenes.pop()

    def create(self, slot):
        def created(player):
            choose_player(self.app, player.id)
            self.app.scenes.pop()  # back home with the new player

        self.navigate("meta_name", title=f"New player in slot {slot}",
                      on_submit=lambda name: meta.create_player(slot, name), on_success=created)

    def rename(self, player):
        self.navigate("meta_name", title="Rename player", value=player.name,
                      on_submit=lambda name: meta.rename_player(player.id, name))

    def delete(self, player):
        self.navigate("confirm", message=f"Delete {player.name}? Tokens, upgrades and run history will be lost.",
                      confirm_text="Delete", on_confirm=lambda: self.remove(player.id))

    def remove(self, player_id):
        self.action(lambda: meta.delete_player(player_id))
        if self.app.session.get("player_id") == player_id:
            choose_player(self.app, None)
        self.refresh()

    def on_resume(self, result=None):
        super().on_resume(result)
        self.refresh()

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        for slot in self.slots:
            y = ROW_Y + (slot.slot - 1) * (ROW_H + ROW_GAP)
            row = pygame.Rect(MARGIN, y, ROW_W, ROW_H)
            p = slot.player
            playing = p is not None and p.id == self.current_id
            if playing:
                draw_glow(surface, (row.x + 60, row.centery), 90, theme.GOLD, 4)
            pygame.draw.rect(surface, (0x1E, 0x25, 0x23), row, border_radius=14)
            pygame.draw.rect(surface, theme.GOLD if playing else (0x34, 0x3B, 0x38), row, 2 if playing else 1,
                             border_radius=14)
            text(surface, a, f"SLOT {slot.slot}", (row.x + 28, y + 22), size=14, color=theme.GOLD_DIM)
            name_font = a.font(30)
            name = fit_text(name_font, p.name if p else "Empty slot", 470)
            surface.blit(name_font.render(name, True, theme.IVORY if p else theme.TEXT_MUTED), (row.x + 28, y + 44))
            if p:
                stats = (f"{p.tokens} tokens   ·   {p.stats.runs} run{'' if p.stats.runs == 1 else 's'}   ·   "
                         f"{p.stats.victories} victor{'y' if p.stats.victories == 1 else 'ies'}")
                text(surface, a, stats, (row.x + 30, y + 88), size=16, color=theme.GOLD, width=470)
                pending = self.pending.get(slot.slot)
                if pending is not None:
                    text(surface, a, "Unfinished run: " + run_summary(pending), (row.x + 110, y + 22), size=14,
                         color=theme.CHAOS_MAGENTA, width=420)
            else:
                text(surface, a, "A fresh seat. Create a player to start earning tokens.", (row.x + 30, y + 88),
                     size=16, color=theme.TEXT_MUTED, width=520)
        self.ui.draw(surface)
        hint = a.font(theme.FONT_TINY).render("Up / Down to move  ·  Enter to choose  ·  Esc to go back", True,
                                              theme.TEXT_MUTED)
        surface.blit(hint, hint.get_rect(bottomright=(MARGIN + ROW_W, 680)))
