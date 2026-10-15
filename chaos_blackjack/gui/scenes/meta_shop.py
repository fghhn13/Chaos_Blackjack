"""Shop: the one place tokens are spent.

Three areas, each split by series (the Classic Table, then "Dealers" with one
tab per dealer such as Poker Head; a dealer with nothing in an area is left
out):

* Upgrades: permanent upgrades. An upgrade tied to a mode belongs to that
  mode's series.
* Cosmetics: decks, tables, chip sets and avatars, grouped by slot, with a live
  table preview. Looks earned through achievements are listed locked with how
  to get them. A bought look can be equipped here or in the Wardrobe.
* Starter items: consumables brought into a run. One tied to a mode belongs to
  that mode's series; otherwise to the series whose tables sell the item.

Everything comes from the meta API's offers and the lists scroll, so new
content needs no layout changes. Design: docs/design/COSMETICS_ACHIEVEMENTS.md.
"""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.cosmetics import COSMETIC_SLOTS, SLOT_LABELS, get_cosmetic
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import MARGIN, apply_loadout, back_button, draw_paragraph, mode_name
from chaos_blackjack.gui.components.meta_screen import MetaScreen
from chaos_blackjack.gui.components.wardrobe import CosmeticRow, draw_look, draw_table_preview
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, ScrollColumn, WidgetGroup, draw_focus_ring, fit_text, wrap_text
from chaos_blackjack.modes import EXPANSIONS_LABEL, get_mode, get_series, item_series, series_list

AREAS = (("upgrades", "Upgrades"), ("cosmetics", "Cosmetics"), ("starter", "Starter items"))
AREA_NOTES = {
    "upgrades": "Permanent upgrades apply to every run you start.",
    "cosmetics": "Looks change only the art. Equip them here or in your Wardrobe.",
    "starter": "Starter items wait in your bag; choose which to bring in New run.",
}
LIST = pygame.Rect(MARGIN, 248, 1140, 340)
COSMETIC_LIST = pygame.Rect(MARGIN, 248, 640, 340)
PREVIEW = pygame.Rect(MARGIN + 676, 248, 476, 268)


class UpgradeRow(Button):
    """One offer. The row is the buy button; the right edge says what a click does."""

    def __init__(self, assets, offer, icon, on_buy):
        super().__init__(assets, (0, 0, 10, 86), offer.name, on_buy, key_hint="", enabled=offer.can_buy)
        self.offer = offer
        self.icon = icon

    def draw(self, surface):
        if not self.visible:
            return
        a, r, o = self.assets, self.rect, self.offer
        hover = self.hovered and self.enabled
        pygame.draw.rect(surface, (0x2A, 0x31, 0x2D) if hover else (0x1E, 0x25, 0x23), r, border_radius=12)
        pygame.draw.rect(surface, theme.GOLD if hover else (0x34, 0x3B, 0x38), r, 1, border_radius=12)
        x = r.x + 20
        if self.icon:
            icon = a.image_fit(self.icon, (52, 52))
            surface.blit(icon, icon.get_rect(midleft=(x, r.centery)))
            x += 68
        price = ("Max level" if o.next_cost is None else f"Buy  ·  {o.next_cost} chips")
        pill_font = a.font(theme.FONT_SMALL, bold=True)
        pill = pygame.Rect(0, 0, max(150, pill_font.size(price)[0] + 30), 38)
        pill.midright = (r.right - 18, r.centery - (8 if o.reason and not o.can_buy and o.next_cost is not None else 0))
        pygame.draw.rect(surface, (0x3B, 0x34, 0x24) if self.enabled else (0x22, 0x28, 0x26), pill, border_radius=19)
        pygame.draw.rect(surface, theme.GOLD if self.enabled else (0x3A, 0x40, 0x3E), pill, 1, border_radius=19)
        label = pill_font.render(price, True, theme.IVORY if self.enabled else theme.TEXT_MUTED)
        surface.blit(label, label.get_rect(center=pill.center))
        if o.reason and not o.can_buy and o.next_cost is not None:
            tiny = a.font(theme.FONT_TINY)
            reason = tiny.render(fit_text(tiny, o.reason, 240), True, theme.TEXT_MUTED)
            surface.blit(reason, reason.get_rect(midtop=(pill.centerx, pill.bottom + 4)))
        text_w = pill.x - x - 24
        name_font = a.font(theme.FONT_BODY, bold=True)
        surface.blit(name_font.render(fit_text(name_font, o.name, text_w - 160), True, theme.IVORY), (x, r.y + 14))
        status_x = x + min(name_font.size(o.name)[0], text_w - 160) + 16
        if o.mode:
            tag_font = a.font(theme.FONT_TINY, bold=True)
            tag = tag_font.render(f"{mode_name(o.mode).upper()} ONLY", True, theme.CHAOS_MAGENTA)
            surface.blit(tag, (status_x, r.y + 19))
            status_x += tag.get_width() + 14
        if o.kind == "permanent":
            for level in range(min(o.max_level, 12)):
                pygame.draw.circle(surface, theme.GOLD if level < o.owned else theme.FELT_LIGHT,
                                   (status_x + 6 + level * 14, r.y + 26), 5)
        else:
            owned = a.font(theme.FONT_SMALL).render(f"Owned ×{o.owned}", True, theme.GOLD)
            surface.blit(owned, (status_x, r.y + 17))
        small = a.font(theme.FONT_SMALL)
        for i, line in enumerate(wrap_text(small, o.description, text_w, max_lines=2)):
            surface.blit(small.render(line, True, theme.TEXT_MUTED), (x, r.y + 44 + i * small.get_linesize()))
        if self.focused and self.enabled:
            draw_focus_ring(surface, r)


class HeadingRow(Button):
    """A slot heading inside the cosmetics list (not clickable or focusable)."""

    focusable = False

    def __init__(self, assets, text):
        super().__init__(assets, (0, 0, 10, 30), text, None, key_hint="", enabled=False, sound=False)

    def draw(self, surface):
        if not self.visible:
            return
        img = self.assets.font(theme.FONT_TINY, bold=True).render(self.text.upper(), True, theme.GOLD_DIM)
        surface.blit(img, (self.rect.x, self.rect.y + 8))
        pygame.draw.line(surface, theme.GOLD_DIM, (self.rect.x, self.rect.bottom - 2),
                         (self.rect.right, self.rect.bottom - 2), 1)


@register_scene("meta_shop")
class MetaShopScene(MetaScreen):
    title = "Shop"

    def on_enter(self, player_id, area=None, series=None, kind=None, **params):
        self.setup()
        self.player_id = player_id
        if area is None and kind is not None:  # earlier callers named the kind
            area = "starter" if kind == "consumable" else "upgrades"
        self.area = area or self.app.session.get("shop_area", self.areas[0][0])
        if self.area not in dict(self.areas):
            self.area = self.areas[0][0]
        self.series = series or self.app.session.get("shop_series", "core")
        self.scroll = 0
        self.refresh()

    # ------------------------------------------------------------------ data

    @property
    def profile(self):
        return self.app.run_config.balance_profile

    def upgrade_item(self, upgrade_id) -> str:
        u = next((u for u in self.app.balance.meta_upgrades if u.upgrade_id == upgrade_id), None)
        return str(dict(u.params).get("item", "")) if u is not None else ""

    icon = upgrade_item  # a starter item's icon is its item

    def series_of(self, offer) -> str:
        """The series an offer belongs to (see the module docstring)."""
        cosmetic = getattr(offer, "cosmetic", None)
        if cosmetic is not None:
            return cosmetic.series
        if offer.mode:
            try:
                return get_mode(offer.mode).series
            except KeyError:
                return offer.mode
        item = self.upgrade_item(offer.upgrade_id) if offer.kind == "consumable" else ""
        return item_series(item, self.app.run_config) if item else "core"

    @property
    def areas(self):
        """The shop's areas; only Cosmetics while the profile sells no meta upgrades."""
        if self.app.balance.meta_upgrades_enabled:
            return AREAS
        return tuple(x for x in AREAS if x[0] == "cosmetics")

    def area_offers(self, area):
        if area == "cosmetics":
            return self.cosmetic_offers
        kind = "permanent" if area == "upgrades" else "consumable"
        return [o for o in self.upgrade_offers if o.kind == kind]

    def refresh(self):
        self.player = self.action(lambda: meta.get_player(self.player_id))
        self.upgrade_offers = self.action(lambda: meta.meta_shop(self.player_id, self.profile)) or []
        self.cosmetic_offers = self.action(lambda: meta.wardrobe(self.player_id, None, self.profile)) or []
        self.loadout = self.action(lambda: meta.loadout(self.player_id)) or {}
        offers = self.area_offers(self.area)
        present = {self.series_of(o) for o in offers}
        # Core first, then the expansions that have something in this area.
        self.series_options = [s for s in series_list() if not s.expansion or s.id in present]
        if self.series not in {s.id for s in self.series_options}:
            self.series = "core"
        self.visible_offers = [o for o in offers if self.series_of(o) == self.series]
        self.subtitle = "Spend vault chips between runs. A dealer's looks go on sale once you beat the dealer."
        self.build()

    # ---------------------------------------------------------------- widgets

    def build(self):
        a = self.app.assets
        self.ui = WidgetGroup(keyboard=True)
        self.area_tabs = {}
        x = MARGIN
        for key, label in self.areas:
            count = len(self.area_offers(key))
            text = f"{label}  {count}"
            width = max(150, a.font(theme.FONT_BODY).size(text)[0] + 48)
            tab = Button(a, (x, 136, width, 44), text, lambda k=key: self.pick_area(k), style="ghost",
                         font_size=theme.FONT_BODY, key_hint="")
            tab.selected = key == self.area
            if tab.selected:
                tab.style = "primary"
            self.area_tabs[key] = tab
            self.ui.add(tab)
            x += width + 10
        # Series: the Classic Table, then "Dealers" and one tab per dealer with content here.
        self.series_tabs = {}
        self.expansions_label_x = None
        x = MARGIN
        for s in self.series_options:
            if s.expansion and self.expansions_label_x is None:
                x += 10
                self.expansions_label_x = x
                x += a.font(theme.FONT_TINY, bold=True).size(EXPANSIONS_LABEL.upper())[0] + 12
            count = sum(1 for o in self.area_offers(self.area) if self.series_of(o) == s.id)
            text = f"{s.name}  {count}"
            width = a.font(theme.FONT_SMALL).size(text)[0] + 40
            tab = Button(a, (x, 194, width, 38), text, lambda sid=s.id: self.pick_series(sid), style="ghost",
                         font_size=theme.FONT_SMALL, key_hint="")
            tab.selected = s.id == self.series
            if tab.selected and s.expansion:
                tab.style = "chaos"
            self.series_tabs[s.id] = tab
            self.ui.add(tab)
            x += width + 8
        self.rows = {}
        self.buy_buttons = self.rows  # kept for callers that look rows up by id
        if self.area == "cosmetics":
            self.list = ScrollColumn(COSMETIC_LIST, gap=8)
            for slot in COSMETIC_SLOTS:
                looks = [o for o in self.visible_offers if o.cosmetic.slot == slot]
                if not looks:
                    continue
                self.list.add(HeadingRow(a, SLOT_LABELS[slot]))
                for offer in looks:
                    self.rows[offer.cosmetic.id] = self.list.add(
                        CosmeticRow(a, offer, lambda o=offer: self.choose(o)))
        else:
            self.list = ScrollColumn(LIST, gap=10)
            for offer in self.visible_offers:
                row = UpgradeRow(a, offer, self.icon(offer.upgrade_id), lambda uid=offer.upgrade_id: self.buy(uid))
                self.rows[offer.upgrade_id] = self.list.add(row)
        self.list.scroll_by(self.scroll)
        self.ui.add(self.list)
        self.ui.add(back_button(a, self.app.scenes.pop))

    # --------------------------------------------------------------- actions

    def pick_area(self, area):
        self.area, self.scroll, self.message = area, 0, ""
        self.app.session["shop_area"] = area
        self.refresh()

    def pick_series(self, series_id):
        self.series, self.scroll, self.message = series_id, 0, ""
        self.app.session["shop_series"] = series_id
        self.refresh()

    def _keep_focus(self, key):
        self.scroll = self.list.scroll
        self.refresh()
        row = self.rows.get(key)
        if row is not None and row.enabled:
            self.ui.set_focus(row)

    def buy(self, upgrade_id):
        self.message = ""
        if self.action(lambda: meta.buy_upgrade(self.player_id, upgrade_id, self.profile)) is not None:
            name = next((o.name for o in self.upgrade_offers if o.upgrade_id == upgrade_id), upgrade_id)
            self.message = f"{name} purchased."
        self._keep_focus(upgrade_id)

    def choose(self, offer):
        """Buy a look for sale; equip one already owned."""
        self.message = ""
        c = offer.cosmetic
        if not offer.owned:
            if self.action(lambda: meta.buy_cosmetic(self.player_id, c.id, self.profile)) is not None:
                self.message = f"{c.name} purchased. Click it again to equip it, or change looks in your Wardrobe."
        elif self.action(lambda: meta.equip(self.player_id, c.id)) is not None:
            apply_loadout(self.app, self.player_id)
            self.message = f"{c.name} equipped."
        self._keep_focus(c.id)

    def update(self, dt):
        self.ui.update(dt)

    # ---------------------------------------------------------------- drawing

    def preview_looks(self):
        """The loadout with the hovered (or focused) look swapped in."""
        looks = {slot: get_cosmetic(cid) for slot, cid in self.loadout.items()}
        shown = next((r.offer.cosmetic for r in self.rows.values()
                      if isinstance(r, CosmeticRow) and r.visible and (r.hovered or r.focused)), None)
        if shown is not None:
            looks[shown.slot] = shown
        return looks, shown

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        if self.expansions_label_x is not None:
            label = a.font(theme.FONT_TINY, bold=True).render(EXPANSIONS_LABEL.upper(), True, theme.GOLD_DIM)
            surface.blit(label, label.get_rect(midleft=(self.expansions_label_x, 213)))
        note = AREA_NOTES.get(self.area, "")
        if note:
            img = a.font(theme.FONT_SMALL).render(note, True, theme.TEXT_MUTED)
            surface.blit(img, img.get_rect(midright=(MARGIN + 1152, 213)))
        if self.area == "cosmetics":
            looks, shown = self.preview_looks()
            if all(looks.values()):
                draw_table_preview(surface, a, looks, PREVIEW)
            if shown is not None:
                y = PREVIEW.bottom + 14
                name_font = a.font(theme.FONT_BUTTON, bold=True)
                surface.blit(name_font.render(fit_text(name_font, shown.name, PREVIEW.w - 160), True, theme.IVORY),
                             (PREVIEW.x, y))
                small = a.font(theme.FONT_SMALL)
                for i, line in enumerate(wrap_text(small, shown.description, PREVIEW.w - 160, max_lines=2)):
                    surface.blit(small.render(line, True, theme.TEXT_MUTED), (PREVIEW.x, y + 34 + i * 22))
                if shown.slot in ("avatar", "chips"):
                    draw_look(surface, a, shown, pygame.Rect(PREVIEW.right - 150, y, 150, 60))
        if not self.visible_offers:
            name = get_series(self.series).name
            draw_paragraph(surface, a, f"Nothing for {name} here yet.", (MARGIN, LIST.y + 10, 900, 40))
        self.ui.draw(surface)
