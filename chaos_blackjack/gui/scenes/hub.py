"""Player hub: prepare a run, spend tokens and revisit past runs."""

import pygame

from chaos_blackjack import meta
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.meta_screen import MetaScreen, panel, text, paragraph
from chaos_blackjack.gui.components.meta_run import run_loop_factory
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, WidgetGroup


@register_scene("hub")
class HubScene(MetaScreen):
    def on_enter(self, player_id, **params):
        self.setup()
        self.player_id = player_id
        self.mode_id = "normal"
        self.selected = set()
        self.consume_page = 0
        self.starting = False
        self.options, self.consumables = [], []
        self.pending_run = None
        self.title = "Player hub"
        self.refresh()

    @property
    def profile(self):
        return self.app.run_config.balance_profile

    def refresh(self):
        self.player = self.action(lambda: meta.get_player(self.player_id))
        if self.player is None:
            self.ui = WidgetGroup(Button(self.app.assets, (64, 640, 320, 52), "Choose player",
                lambda: self.app.scenes.reset("player_select"), style="ghost", hotkey=pygame.K_ESCAPE))
            return
        self.title = f"{self.player.name}'s hub"
        self.subtitle = f"{self.player.tokens} tokens  /  {self.player.stats.victories} victories  /  {self.player.stats.runs} runs"
        self.options = self.action(lambda: meta.modes(self.player_id)) or []
        unlocked = [o.mode.id for o in self.options if o.unlocked]
        if self.mode_id not in unlocked:
            self.mode_id = unlocked[0] if unlocked else ""
        self.consumables = [o for o in (self.action(lambda: meta.meta_shop(self.player_id, self.profile)) or [])
                            if o.kind == "consumable" and o.owned > 0]
        self.selected.intersection_update(o.upgrade_id for o in self.consumables)
        self.pending_run = self.action(lambda: meta.resume_run(self.player_id, loop_factory=run_loop_factory(self.app)))
        self.build_widgets()

    def build_widgets(self):
        a = self.app.assets
        self.ui = WidgetGroup()
        self.nav = {}
        for i, (name, label) in enumerate((("meta_shop", "Meta shop"), ("history", "History"),
                                           ("codex", "Codex"), ("meta_settings", "Settings"))):
            available = name in self.app.scenes.registry
            b = Button(a, (64, 175 + i * 86, 320, 62), label,
                       lambda name=name: self.navigate(name, player_id=self.player_id, config=self.app.run_config),
                       style="ghost", enabled=available,
                       tooltip="Codex is coming soon." if not available else "")
            self.nav[name] = b
            self.ui.add(b)
        self.ui.add(Button(a, (64, 640, 320, 52), "Choose player",
                           lambda: self.app.scenes.reset("player_select"), style="ghost", hotkey=pygame.K_ESCAPE))
        self.mode_buttons = {}
        for i, option in enumerate(self.options[:3]):
            width = 704 // max(1, min(3, len(self.options)))
            mode = option.mode
            b = Button(a, (464 + i * width, 170, width - 14, 58),
                       ("Selected: " if mode.id == self.mode_id else "") + mode.name,
                       lambda mid=mode.id: self.choose_mode(mid), enabled=option.unlocked,
                       style="chaos" if mode.id == "chaos" else "primary", font_size=20,
                       tooltip="This mode is locked." if not option.unlocked else "")
            self.mode_buttons[mode.id] = b
            self.ui.add(b)
        self.consume_buttons = {}
        self.consume_page = min(self.consume_page, max(0, (len(self.consumables) - 1) // 6))
        for i, offer in enumerate(self.consumables[self.consume_page * 6:self.consume_page * 6 + 6]):
            b = Button(a, (464 + (i % 2) * 356, 342 + (i // 2) * 58, 342, 48),
                       ("Bring: " if offer.upgrade_id in self.selected else "Leave: ") + f"{offer.name} x{offer.owned}",
                       lambda uid=offer.upgrade_id: self.toggle_consumable(uid), font_size=17,
                       tooltip=offer.description, style="primary" if offer.upgrade_id in self.selected else "ghost")
            self.consume_buttons[offer.upgrade_id] = b
            self.ui.add(b)
        if len(self.consumables) > 6:
            self.ui.add(Button(a, (464, 530, 160, 40), "Previous", lambda: self.change_page(-1),
                               enabled=self.consume_page > 0, font_size=18, style="ghost"))
            self.ui.add(Button(a, (1006, 530, 160, 40), "Next", lambda: self.change_page(1),
                               enabled=(self.consume_page + 1) * 6 < len(self.consumables), font_size=18, style="ghost"))
        self.start_button = Button(a, (464, 640, 342, 52), "Start run", self.start,
                                   hotkey=pygame.K_RETURN, enabled=bool(self.mode_id))
        self.continue_button = Button(a, (820, 640, 346, 52), "Continue saved run", self.resume,
                                      style="ghost", enabled=self.pending_run is not None)
        self.ui.add(self.start_button)
        self.ui.add(self.continue_button)

    def choose_mode(self, mode_id):
        if any(o.mode.id == mode_id and o.unlocked for o in self.options):
            self.mode_id = mode_id
            self.build_widgets()

    def toggle_consumable(self, upgrade_id):
        if upgrade_id in self.selected:
            self.selected.remove(upgrade_id)
        else:
            self.selected.add(upgrade_id)
        self.build_widgets()

    def change_page(self, delta):
        self.consume_page += delta
        self.build_widgets()

    def start(self):
        if self.starting or self.leaving:
            return
        if self.pending_run is not None:
            self.navigate("confirm", message="Replace your unfinished run?",
                          on_confirm=self.replace_run)
        else:
            self.begin_run()

    def replace_run(self):
        if self.action(lambda: (meta.abandon_run(self.pending_run.run_id), True)[1]):
            self.pending_run = None
            self.begin_run()

    def begin_run(self):
        if self.starting:
            return
        self.starting = True
        started = self.action(lambda: meta.start_run(self.player_id, self.mode_id,
                              consumables=sorted(self.selected), profile=self.profile,
                              loop_factory=run_loop_factory(self.app)))
        if started is None:
            self.starting = False
            self.leaving = False
            return
        self.selected.clear()
        self.app.scenes.push("meta_table", started=started, player_id=self.player_id)

    def resume(self):
        if self.starting or self.leaving:
            return
        started = self.action(lambda: meta.resume_run(self.player_id, loop_factory=run_loop_factory(self.app)))
        if started is None:
            self.message = self.message or "There is no saved run to continue."
            return
        self.starting = True
        self.app.scenes.push("meta_table", started=started, player_id=self.player_id)

    def on_resume(self, result=None):
        super().on_resume(result)
        self.starting = False
        self.refresh()

    def draw(self, surface):
        super().draw(surface)
        panel(surface, (438, 145, 752, 435))
        a = self.app.assets
        mode = next((o.mode for o in self.options if o.mode.id == self.mode_id), None)
        paragraph(surface, a, mode.description if mode else "No unlocked modes available.", (464, 248, 704, 46))
        text(surface, a, "Bring one copy of each selected consumable", (464, 304), size=19, color=theme.GOLD)
        if not self.consumables:
            paragraph(surface, a, "No consumables owned yet. Visit the meta shop to prepare your next run.",
                      (464, 358, 704, 100))
        text(surface, a, f"Best bankroll: {self.player.stats.best_money}" if self.player else "", (64, 546), size=18)
        self.ui.draw(surface)
