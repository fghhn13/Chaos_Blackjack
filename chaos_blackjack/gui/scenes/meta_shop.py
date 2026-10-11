"""Upgrades: spend tokens on permanent upgrades and consumables.

Everything comes from the meta API's offers. Categories are the offer kinds
present, and the list scrolls, so new upgrades need no layout changes.
"""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import MARGIN, back_button, draw_paragraph
from chaos_blackjack.gui.components.meta_screen import MetaScreen
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, ScrollColumn, WidgetGroup, draw_focus_ring, fit_text, wrap_text

LIST = pygame.Rect(MARGIN, 206, 1140, 380)
KIND_LABELS = {"permanent": "Permanent", "consumable": "Consumables"}
KIND_NOTES = {
    "permanent": "Permanent upgrades apply to every run you start.",
    "consumable": "Consumables wait in your bag; choose which to bring in New run.",
}


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
        price = ("Max level" if o.next_cost is None else f"Buy  ·  {o.next_cost} tokens")
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


@register_scene("meta_shop")
class MetaShopScene(MetaScreen):
    title = "Upgrades"

    def on_enter(self, player_id, kind=None, **params):
        self.setup()
        self.player_id = player_id
        self.kind = kind or self.app.session.get("upgrades_tab", "permanent")
        self.scroll = 0
        self.refresh()

    def refresh(self):
        self.player = self.action(lambda: meta.get_player(self.player_id))
        self.offers = self.action(lambda: meta.meta_shop(self.player_id, self.app.run_config.balance_profile)) or []
        self.kinds = list(dict.fromkeys(o.kind for o in self.offers)) or ["permanent"]
        if self.kind not in self.kinds:
            self.kind = self.kinds[0]
        self.subtitle = "Spend tokens between runs. Your bankroll stays at the table."
        self.visible_offers = [o for o in self.offers if o.kind == self.kind]
        a = self.app.assets
        self.ui = WidgetGroup(keyboard=True)
        self.tabs = {}
        x = MARGIN
        for k in self.kinds:
            label = KIND_LABELS.get(k, k.replace("_", " ").title())
            width = a.font(theme.FONT_BODY).size(label)[0] + 48
            tab = Button(a, (x, 136, width, 44), label, lambda k=k: self.tab(k), style="ghost",
                         font_size=theme.FONT_BODY, key_hint="")
            tab.selected = k == self.kind
            self.tabs[k] = tab
            self.ui.add(tab)
            x += width + 10
        self.list = ScrollColumn(LIST, gap=10)
        self.buy_buttons = {}
        for offer in self.visible_offers:
            row = UpgradeRow(a, offer, self.icon(offer.upgrade_id), lambda uid=offer.upgrade_id: self.buy(uid))
            self.buy_buttons[offer.upgrade_id] = self.list.add(row)
        self.list.scroll_by(self.scroll)
        self.ui.add(self.list)
        self.ui.add(back_button(a, self.app.scenes.pop))

    def icon(self, upgrade_id):
        u = next((u for u in self.app.balance.meta_upgrades if u.upgrade_id == upgrade_id), None)
        return str(dict(u.params).get("item", "")) if u is not None else ""

    def tab(self, kind):
        self.kind, self.scroll = kind, 0
        self.app.session["upgrades_tab"] = kind
        self.message = ""
        self.refresh()

    def buy(self, upgrade_id):
        self.message = ""
        result = self.action(lambda: meta.buy_upgrade(self.player_id, upgrade_id, self.app.run_config.balance_profile))
        if result is not None:
            name = next((o.name for o in self.offers if o.upgrade_id == upgrade_id), upgrade_id)
            self.message = f"{name} purchased."
        self.scroll = self.list.scroll
        focus = self.ui.focus.offer.upgrade_id if isinstance(self.ui.focus, UpgradeRow) else None
        self.refresh()
        if focus in self.buy_buttons and self.buy_buttons[focus].enabled:
            self.ui.set_focus(self.buy_buttons[focus])

    def update(self, dt):
        self.ui.update(dt)

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        note = KIND_NOTES.get(self.kind, "")
        if note:
            img = a.font(theme.FONT_SMALL).render(note, True, theme.TEXT_MUTED)
            surface.blit(img, img.get_rect(bottomright=(MARGIN + 1152, 172)))
        if not self.visible_offers:
            draw_paragraph(surface, a, "Nothing to buy in this section yet.", (MARGIN, LIST.y + 10, 800, 40))
        self.ui.draw(surface)
