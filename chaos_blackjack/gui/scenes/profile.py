"""Profile: the current player's avatar and record, Wardrobe and Achievements.

Opened from the player badge on Home. Wardrobe lists every look per slot from
the meta API (equip, or buy with tokens and equip); the live preview shows the
hovered look together with the rest of the loadout. Switch player opens the
save slots; choosing another player returns home.
Design: docs/design/COSMETICS_ACHIEVEMENTS.md §8.
"""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.cosmetics import COSMETIC_SLOTS, SLOT_LABELS, get_cosmetic
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import MARGIN, apply_loadout, back_button, draw_section
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text
from chaos_blackjack.gui.components.wardrobe import (
    AchievementRow, CosmeticRow, draw_look, draw_table_preview,
)
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, ScrollColumn, WidgetGroup, fit_text, wrap_text

TABS = (("overview", "Overview"), ("wardrobe", "Wardrobe"), ("achievements", "Achievements"))
WARDROBE_LIST = pygame.Rect(MARGIN, 250, 640, 340)
PREVIEW = pygame.Rect(MARGIN + 676, 196, 476, 268)
ACHIEVEMENT_LIST = pygame.Rect(MARGIN, 236, 1140, 354)
STATS = (
    ("runs", "Runs finished"), ("victories", "Runs won"), ("rounds", "Rounds played"),
    ("hands_won", "Hands won"), ("blackjacks", "Blackjacks"), ("win_streak", "Best win streak"),
)


@register_scene("profile")
class ProfileScene(MetaScreen):
    title = "Profile"

    def on_enter(self, player_id, tab=None, slot=None, **params):
        self.setup()
        self.player_id = player_id
        self.tab = tab or self.app.session.get("profile_tab", "overview")
        self.slot = slot or self.app.session.get("wardrobe_slot", "card_back")
        self.scroll = 0
        self.refresh()

    # ------------------------------------------------------------------ data

    def refresh(self):
        profile = self.app.run_config.balance_profile
        self.player = self.action(lambda: meta.get_player(self.player_id))
        if self.player is None:
            return
        self.title = self.player.name  # also avoids the display font's "fi" ligature in "Profile"
        self.subtitle = "Your record, your looks and what you have achieved."
        self.loadout = self.action(lambda: meta.loadout(self.player_id)) or {}
        self.achievements = self.action(lambda: meta.achievements(self.player_id, profile)) or []
        self.player = self.action(lambda: meta.get_player(self.player_id)) or self.player  # backfill may pay
        self.offers = []
        self.totals = {}
        if self.tab == "wardrobe":
            self.offers = self.action(lambda: meta.wardrobe(self.player_id, self.slot, profile)) or []
        elif self.tab == "overview":
            self.totals = self.action(lambda: meta.player_stats(self.player_id)) or {}
            self.best = self.action(lambda: meta.player_stats(self.player_id, best=True)) or {}
            looks = self.action(lambda: meta.wardrobe(self.player_id, None, profile)) or []
            self.owned_looks, self.all_looks = sum(o.owned for o in looks), len(looks)
        self.build()

    def build(self):
        a = self.app.assets
        self.ui = WidgetGroup(keyboard=True)
        self.tabs = {}
        x = MARGIN
        for key, label in TABS:
            width = a.font(theme.FONT_BODY).size(label)[0] + 48
            tab = Button(a, (x, 136, width, 44), label, lambda k=key: self.set_tab(k), style="ghost",
                         font_size=theme.FONT_BODY, key_hint="")
            tab.selected = key == self.tab
            self.tabs[key] = tab
            self.ui.add(tab)
            x += width + 10
        self.rows = {}
        self.list = None
        if self.tab == "overview":
            self.rename_button = Button(a, (MARGIN, 470, 170, 46), "Rename", self.rename, style="ghost",
                                        font_size=theme.FONT_BODY, key_hint="")
            self.avatar_button = Button(a, (MARGIN + 182, 470, 200, 46), "Change avatar",
                                        lambda: self.open_wardrobe("avatar"), style="ghost",
                                        font_size=theme.FONT_BODY, key_hint="")
            self.ui.add(self.rename_button)
            self.ui.add(self.avatar_button)
        elif self.tab == "wardrobe":
            self.slot_tabs = {}
            x = MARGIN
            for slot in COSMETIC_SLOTS:
                label = SLOT_LABELS[slot]
                width = a.font(theme.FONT_SMALL).size(label)[0] + 36
                b = Button(a, (x, 198, width, 36), label, lambda s=slot: self.set_slot(s), style="ghost",
                           font_size=theme.FONT_SMALL, key_hint="")
                b.selected = slot == self.slot
                self.slot_tabs[slot] = b
                self.ui.add(b)
                x += width + 8
            self.list = ScrollColumn(WARDROBE_LIST, gap=10)
            for offer in self.offers:
                self.rows[offer.cosmetic.id] = self.list.add(
                    CosmeticRow(a, offer, lambda o=offer: self.choose(o)))
        else:
            self.list = ScrollColumn(ACHIEVEMENT_LIST, gap=8)
            for state in sorted(self.achievements, key=lambda s: (not s.unlocked, -s.progress / s.goal)):
                look = get_cosmetic(state.reward_cosmetic) if state.reward_cosmetic else None
                self.rows[state.achievement.id] = self.list.add(
                    AchievementRow(a, state, look.name if look else None))
        if self.list is not None:
            self.list.scroll_by(self.scroll)
            self.ui.add(self.list)
        self.switch_button = Button(a, (MARGIN + 1152 - 220, 642, 220, 50), "Switch player", self.switch,
                                    style="ghost", font_size=theme.FONT_BODY, key_hint="")
        self.ui.add(self.switch_button)
        self.ui.add(back_button(a, self.app.scenes.pop))

    # --------------------------------------------------------------- actions

    def set_tab(self, tab):
        self.tab, self.scroll, self.message = tab, 0, ""
        self.app.session["profile_tab"] = tab
        self.refresh()

    def set_slot(self, slot):
        self.slot, self.scroll, self.message = slot, 0, ""
        self.app.session["wardrobe_slot"] = slot
        self.refresh()

    def open_wardrobe(self, slot):
        self.tab = "wardrobe"
        self.app.session["profile_tab"] = "wardrobe"
        self.set_slot(slot)

    def choose(self, offer):
        """Equip an owned look; buy (then equip) one that is for sale."""
        self.message = ""
        c = offer.cosmetic
        profile = self.app.run_config.balance_profile
        bought = not offer.owned
        if bought and self.action(lambda: meta.buy_cosmetic(self.player_id, c.id, profile)) is None:
            self.refresh()
            return
        if self.action(lambda: meta.equip(self.player_id, c.id)) is not None:
            apply_loadout(self.app, self.player_id)
            self.message = f"{c.name} {'purchased and ' if bought else ''}equipped."
        self.scroll = self.list.scroll if self.list else 0
        self.refresh()

    def rename(self):
        self.navigate("meta_name", title="Rename player", value=self.player.name,
                      on_submit=lambda name: meta.rename_player(self.player_id, name))

    def switch(self):
        self.navigate("player_select")

    def on_resume(self, result=None):
        super().on_resume(result)
        if self.app.session.get("player_id") != self.player_id:
            self.leaving = True
            self.app.scenes.pop()  # another player was chosen (or this one deleted): back home
            return
        self.refresh()

    def update(self, dt):
        self.ui.update(dt)

    # ---------------------------------------------------------------- drawing

    def draw(self, surface):
        super().draw(surface)
        if self.player is None:
            self.ui.draw(surface)
            return
        if self.tab == "overview":
            self.draw_overview(surface)
        elif self.tab == "wardrobe":
            self.draw_wardrobe(surface)
        else:
            done = sum(s.unlocked for s in self.achievements)
            text(surface, self.app.assets, f"{done} of {len(self.achievements)} unlocked", (MARGIN, 200),
                 size=theme.FONT_BODY, color=theme.GOLD)
            if not self.achievements:
                text(surface, self.app.assets, "No achievements yet.", (MARGIN, 250), color=theme.TEXT_MUTED)
        self.ui.draw(surface)

    def draw_overview(self, surface):
        a, p = self.app.assets, self.player
        avatar = a.image(p.avatar, (168, 168))
        surface.blit(avatar, (MARGIN, 206))
        name_font = a.font(theme.FONT_HEADING, bold=True)
        surface.blit(name_font.render(fit_text(name_font, p.name, 320), True, theme.IVORY), (MARGIN + 192, 218))
        text(surface, a, f"Slot {p.slot}", (MARGIN + 194, 268), size=theme.FONT_SMALL, color=theme.GOLD_DIM)
        text(surface, a, f"{p.tokens} tokens", (MARGIN + 194, 300), size=theme.FONT_BUTTON, color=theme.GOLD)
        done = sum(s.unlocked for s in self.achievements)
        text(surface, a, f"Achievements  {done} / {len(self.achievements)}", (MARGIN + 194, 344),
             size=theme.FONT_SMALL, color=theme.TEXT_MUTED)
        text(surface, a, f"Looks owned  {self.owned_looks} / {self.all_looks}", (MARGIN + 194, 368),
             size=theme.FONT_SMALL, color=theme.TEXT_MUTED)
        box = pygame.Rect(MARGIN + 560, 200, 592, 300)
        panel(surface, box)
        y = draw_section(surface, a, "Record", (box.x + 28, box.y + 22), box.w - 56)
        for i, (stat, label) in enumerate(STATS):
            col, row = i % 2, i // 2
            x = box.x + 28 + col * 280
            yy = y + 8 + row * 70
            value = self.best.get(stat, 0) if stat == "win_streak" else self.totals.get(stat, 0)
            text(surface, a, str(value), (x, yy), size=theme.FONT_HEADING - 4, color=theme.IVORY)
            text(surface, a, label, (x, yy + 38), size=theme.FONT_SMALL, color=theme.TEXT_MUTED)
        best = a.font(theme.FONT_SMALL).render(f"Best bankroll: {p.stats.best_money}", True, theme.GOLD_DIM)
        surface.blit(best, best.get_rect(bottomright=(box.right - 28, box.bottom - 18)))

    def preview_looks(self):
        looks = {slot: get_cosmetic(cid) for slot, cid in self.loadout.items()}
        shown = None
        for row in self.rows.values():
            if isinstance(row, CosmeticRow) and row.visible and (row.hovered or row.focused):
                shown = row.offer.cosmetic
                break
        if shown is None:
            shown = get_cosmetic(self.loadout.get(self.slot, "")) or None
        if shown is not None:
            looks[shown.slot] = shown
        return looks, shown

    def draw_wardrobe(self, surface):
        a = self.app.assets
        looks, shown = self.preview_looks()
        if all(looks.values()):
            draw_table_preview(surface, a, looks, PREVIEW)
        if shown is not None:
            y = PREVIEW.bottom + 16
            name_font = a.font(theme.FONT_BUTTON, bold=True)
            surface.blit(name_font.render(fit_text(name_font, shown.name, PREVIEW.w), True, theme.IVORY),
                         (PREVIEW.x, y))
            small = a.font(theme.FONT_SMALL)
            for i, line in enumerate(wrap_text(small, shown.description, PREVIEW.w, max_lines=2)):
                surface.blit(small.render(line, True, theme.TEXT_MUTED), (PREVIEW.x, y + 36 + i * 22))
            if shown.slot in ("avatar", "chips"):
                draw_look(surface, a, shown, pygame.Rect(PREVIEW.right - 150, y, 150, 64))
        if not self.offers:
            text(surface, a, "Nothing in this section yet.", (WARDROBE_LIST.x, WARDROBE_LIST.y + 10),
                 color=theme.TEXT_MUTED)
