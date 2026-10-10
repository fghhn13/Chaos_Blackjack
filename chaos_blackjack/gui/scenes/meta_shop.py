"""A token shop driven entirely by the meta API's offers."""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text, paragraph
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup


@register_scene("meta_shop")
class MetaShopScene(MetaScreen):
    title = "Meta shop"

    def on_enter(self, player_id, **params):
        self.setup()
        self.player_id = player_id
        self.kind = "permanent"
        self.page = 0
        self.refresh()

    def refresh(self):
        self.player = self.action(lambda: meta.get_player(self.player_id))
        self.offers = self.action(lambda: meta.meta_shop(self.player_id, self.app.run_config.balance_profile)) or []
        self.subtitle = f"{self.player.tokens} tokens  /  Upgrades carry into your next run." if self.player else ""
        self.visible_offers = [o for o in self.offers if o.kind == self.kind]
        self.page = max(0, min(self.page, max(0, (len(self.visible_offers) - 1) // 6)))
        self.ui = WidgetGroup(
            Button(self.app.assets, (64, 134, 250, 48), "Permanent upgrades", lambda: self.tab("permanent"), font_size=20),
            Button(self.app.assets, (330, 134, 250, 48), "Consumables", lambda: self.tab("consumable"), font_size=20),
            Button(self.app.assets, (64, 640, 240, 52), "Back to hub", self.app.scenes.pop,
                   style="ghost", hotkey=pygame.K_ESCAPE),
            Button(self.app.assets, (800, 640, 190, 52), "Previous", lambda: self.turn_page(-1),
                   style="ghost", enabled=self.page > 0),
            Button(self.app.assets, (1010, 640, 190, 52), "Next", lambda: self.turn_page(1),
                   style="ghost", enabled=(self.page + 1) * 6 < len(self.visible_offers)),
        )
        self.buy_buttons = {}
        for i, offer in enumerate(self.current):
            x, y = 64 + (i % 2) * 580, 204 + (i // 2) * 120
            b = Button(self.app.assets, (x + 388, y + 14, 156, 44),
                       "Max level" if offer.next_cost is None else f"Buy: {offer.next_cost}",
                       lambda uid=offer.upgrade_id: self.buy(uid), font_size=18,
                       enabled=offer.can_buy, tooltip=offer.reason)
            self.buy_buttons[offer.upgrade_id] = b
            self.ui.add(b)

    @property
    def current(self):
        return self.visible_offers[self.page * 6:self.page * 6 + 6]

    def tab(self, kind):
        self.kind, self.page = kind, 0
        self.refresh()

    def turn_page(self, delta):
        self.page += delta
        self.refresh()

    def buy(self, upgrade_id):
        result = self.action(lambda: meta.buy_upgrade(self.player_id, upgrade_id, self.app.run_config.balance_profile))
        if result is not None:
            self.message = "Purchased. Your next run will use this upgrade."
        self.refresh()

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        for i, offer in enumerate(self.current):
            x, y = 64 + (i % 2) * 580, 204 + (i // 2) * 120
            panel(surface, (x, y, 556, 106))
            text(surface, a, offer.name, (x + 16, y + 12), color=theme.GOLD, width=352)
            if offer.kind == "permanent":
                text(surface, a, f"Level {offer.owned}/{offer.max_level}", (x + 16, y + 40), size=16)
                for level in range(min(offer.max_level, 16)):
                    pygame.draw.circle(surface, theme.GOLD if level < offer.owned else theme.FELT_LIGHT,
                                       (x + 165 + level * 11, y + 49), 4)
            else:
                text(surface, a, f"Owned: {offer.owned}  /  Used once when brought", (x + 16, y + 40), size=16)
            paragraph(surface, a, offer.description, (x + 16, y + 63, 360, 34), size=15)
            text(surface, a, offer.reason, (x + 388, y + 65), size=14, width=156)
        if not self.current:
            paragraph(surface, a, "No upgrades available in this section.", (64, 232, 800, 80))
        text(surface, a, f"Page {self.page + 1}", (620, 658), size=18)
        self.ui.draw(surface)
