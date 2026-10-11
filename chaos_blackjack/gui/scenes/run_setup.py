"""Run setup: choose a mode, review the upgrades in effect, pick items to bring,
then confirm. Nothing is spent until the run actually starts.

The mode and item lists scroll, so new modes, challenges and consumables fit
without a new layout. Choices are remembered per player for this session.
"""

from __future__ import annotations

import sqlite3
from dataclasses import fields

import pygame

from chaos_blackjack import meta
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.lobby import (
    MARGIN, OptionRow, back_button, draw_glow, draw_paragraph, draw_section,
)
from chaos_blackjack.gui.components.chaos_panel import mood_face
from chaos_blackjack.gui.components.meta_run import run_loop_factory
from chaos_blackjack.gui.components.meta_screen import MetaScreen
from chaos_blackjack.gui.scene import register_scene
from chaos_blackjack.gui.widgets import Button, ScrollColumn, WidgetGroup, fit_text

MODES = pygame.Rect(MARGIN, 162, 300, 420)
SHOWCASE = pygame.Rect(394, 140, 452, 468)
RIGHT_X, RIGHT_W = 878, 338
ITEMS_TOP = 372

# Plain-English names for config values an upgrade or mode can change.
CONFIG_LABELS = {
    "start_money": "Starting bankroll",
    "target_money": "Target bankroll",
    "shop_slots": "Table shop shelf",
    "shop_refresh_rounds": "Shop restocks every",
    "dealer_stand_on": "Dealer stands on",
    "min_bet": "Minimum bet",
    "max_bet_fraction": "Maximum bet",
    "bring_kinds": "Item kinds to bring",
    "free_rerolls": "Free shop rerolls",
}
_HIDDEN = {"starting_items", "balance_profile", "balance_hash", "seed", "use_llm", "enable_chaos",
           "shop_bankroll_pct", "shop_price_floor"}


def _value(name: str, value) -> str:
    if name == "max_bet_fraction":
        return f"{value * 100:g}%"
    if name == "shop_refresh_rounds":
        return f"{value} rounds"
    return str(value)


def upgrade_effects(base: RunConfig, upgraded: RunConfig) -> list[str]:
    """Readable differences an owned upgrade makes to this run's numbers."""
    lines = []
    for f in fields(RunConfig):
        name = f.name
        if name in _HIDDEN:
            continue
        before, after = getattr(base, name, None), getattr(upgraded, name, None)
        if before == after:
            continue
        if name == "shop_prices" and before and after:
            total_before = sum(before.values()) or 1
            change = round((sum(after.values()) - total_before) * 100 / total_before)
            lines.append(f"Table shop prices {change:+d}%")
        elif name in CONFIG_LABELS:
            lines.append(f"{CONFIG_LABELS[name]}: {_value(name, before)} › {_value(name, after)}")
        else:
            lines.append(f"{name.replace('_', ' ').capitalize()} changed")
    return lines


@register_scene("run_setup")
class RunSetupScene(MetaScreen):
    title = "New run"
    subtitle = "Choose your table, check your edge, pack your pockets."

    def on_enter(self, player_id, **params):
        self.setup()
        self.player_id = player_id
        self.starting = False
        memory = self.app.session.setdefault("setup", {}).setdefault(player_id, {"mode": "", "bring": set()})
        self.memory = memory
        self.player = self.action(lambda: meta.get_player(player_id))
        if self.player is None:
            self.ui = WidgetGroup(back_button(self.app.assets, self.app.scenes.pop), keyboard=True)
            self.options, self.consumables, self.permanents = [], [], []
            return
        self.options = self.action(lambda: meta.modes(player_id)) or []
        offers = self.action(lambda: meta.meta_shop(player_id, self.profile)) or []
        self.consumables = [o for o in offers if o.kind == "consumable" and o.owned > 0]
        self.permanents = [o for o in offers if o.kind == "permanent" and o.owned > 0]
        self.pending = self.action(lambda: meta.pending_run(player_id))
        unlocked = [o.mode.id for o in self.options if o.unlocked]
        if memory["mode"] not in unlocked:
            memory["mode"] = unlocked[0] if unlocked else ""
        memory["bring"].intersection_update(o.upgrade_id for o in self.consumables)
        self.build()

    @property
    def profile(self):
        return self.app.run_config.balance_profile

    @property
    def mode_id(self) -> str:
        return self.memory["mode"]

    @property
    def selected(self) -> set[str]:
        return self.memory["bring"]

    @property
    def mode(self):
        return next((o.mode for o in self.options if o.mode.id == self.mode_id), None)

    # ---------------------------------------------------------------- widgets

    def build(self):
        a = self.app.assets
        self.ui = WidgetGroup(keyboard=True)
        self.mode_rows = {}
        modes = ScrollColumn(MODES, gap=10)
        for option in self.options:
            m = option.mode
            row = OptionRow(a, 76, m.name, lambda mid=m.id: self.choose_mode(mid), icon=m.icon,
                            detail=m.description if option.unlocked else "Locked: unlock it in Upgrades",
                            chaos=m.id == "chaos", enabled=option.unlocked)
            self.mode_rows[m.id] = modes.add(row)
        self.ui.add(modes)
        self.item_rows = {}
        items = ScrollColumn((RIGHT_X, ITEMS_TOP, RIGHT_W, 582 - ITEMS_TOP), gap=8)
        for offer in self.consumables:
            row = OptionRow(a, 58, offer.name, lambda uid=offer.upgrade_id: self.toggle_consumable(uid),
                            icon=self.item_icon(offer.upgrade_id), detail=f"Owned ×{offer.owned}",
                            check=False, tooltip=offer.description)
            self.item_rows[offer.upgrade_id] = items.add(row)
        self.ui.add(items)
        self.start_button = Button(a, (946, 640, 270, 54), "Start run", self.start, hotkey=pygame.K_RETURN)
        self.ui.add(self.start_button)
        self.ui.add(back_button(a, self.app.scenes.pop))
        self.sync()

    def sync(self):
        for mode_id, row in self.mode_rows.items():
            row.selected = mode_id == self.mode_id
        limit = self.bring_limit
        while len(self.selected) > limit:
            self.selected.discard(max(self.selected))  # e.g. Bag Space no longer owned
        full = len(self.selected) >= limit
        for upgrade_id, row in self.item_rows.items():
            row.check = upgrade_id in self.selected
            row.note = "Bring 1" if row.check else ""
            row.enabled = row.check or not full
        chaos = self.mode_id == "chaos"
        self.start_button.style = "chaos" if chaos else "primary"
        self.start_button.enabled = bool(self.mode_id) and not self.starting

    def item_icon(self, upgrade_id: str) -> str:
        u = next((u for u in self.app.balance.meta_upgrades if u.upgrade_id == upgrade_id), None)
        return str(dict(u.params).get("item", "")) if u is not None else ""

    # ---------------------------------------------------------------- choices

    def choose_mode(self, mode_id):
        if any(o.mode.id == mode_id and o.unlocked for o in self.options):
            self.memory["mode"] = mode_id
            self.sync()

    @property
    def bring_limit(self) -> int:
        """Consumable kinds this player may bring (Bag Space raises it)."""
        preview = self.preview_config()
        return preview[1].bring_kinds if preview else RunConfig.from_balance(self.app.balance).bring_kinds

    def toggle_consumable(self, upgrade_id):
        if upgrade_id not in self.selected and len(self.selected) >= self.bring_limit:
            self.message = f"Your bag holds {self.bring_limit} kinds of items. Bag Space in Upgrades adds more."
            return
        self.message = ""
        self.selected.symmetric_difference_update({upgrade_id})
        self.sync()

    def preview_config(self) -> tuple[RunConfig, RunConfig] | None:
        mode = self.mode
        if mode is None or self.player is None:
            return None
        try:
            base = mode.apply(RunConfig.from_balance(self.app.balance))
            upgraded, _ = meta.build_run_config(self.app.balance, mode, self.player.upgrades)
        except (ValueError, KeyError):
            return None
        return base, upgraded

    # ---------------------------------------------------------------- start

    def start(self):
        if self.starting or self.leaving or not self.mode_id:
            return
        if self.pending is not None:
            self.navigate("confirm", message="Abandon your unfinished run and start this one?",
                          confirm_text="Start new", on_confirm=self.replace_run)
        else:
            self.begin_run()

    def replace_run(self):
        if self.action(lambda: (meta.abandon_run(self.pending.run_id), True)[1]):
            self.pending = None
            self.begin_run()

    def begin_run(self):
        if self.starting:
            return
        self.starting = True
        self.message = ""
        try:
            started = meta.start_run(self.player_id, self.mode_id, consumables=sorted(self.selected),
                                     profile=self.profile, loop_factory=run_loop_factory(self.app))
        except (ValueError, sqlite3.Error, OSError) as exc:
            started = None
            self.message = str(exc)
        if started is None:
            self.starting = False
            self.leaving = False
            self.sync()
            return
        self.selected.clear()
        self.leaving = True
        self.app.scenes.replace("meta_table", started=started, player_id=self.player_id)

    def on_resume(self, result=None):
        super().on_resume(result)
        self.sync()

    # ---------------------------------------------------------------- frame

    def update(self, dt):
        self.ui.update(dt)

    def draw(self, surface):
        super().draw(surface)
        a = self.app.assets
        if self.player is None:
            self.ui.draw(surface)
            return
        draw_section(surface, a, "Mode", (MODES.x, 136), MODES.w)
        self.draw_showcase(surface)
        y = draw_section(surface, a, "Upgrades in effect", (RIGHT_X, 136), RIGHT_W)
        self.draw_upgrades(surface, y)
        y = draw_section(surface, a, f"Bring items  ({len(self.selected)}/{self.bring_limit} kinds)",
                         (RIGHT_X, ITEMS_TOP - 30), RIGHT_W)
        if not self.consumables:
            draw_paragraph(surface, a, "Your bag is empty. Consumables bought in Upgrades show up here.",
                           (RIGHT_X, ITEMS_TOP, RIGHT_W, 80))
        self.ui.draw(surface)
        note = "One copy of each checked item is used when the run starts." if self.consumables else ""
        if self.pending is not None:
            note = "You have an unfinished run. Starting asks before replacing it."
        if note:
            draw_paragraph(surface, a, note, (RIGHT_X, 594, RIGHT_W, 40),
                           color=theme.CHAOS_MAGENTA if self.pending else theme.TEXT_MUTED, size=theme.FONT_TINY + 1)
        hint = a.font(theme.FONT_TINY).render("Up / Down / Tab to move  ·  Space to choose  ·  Enter to start", True,
                                              theme.TEXT_MUTED)
        surface.blit(hint, hint.get_rect(midleft=(300, 667)))

    def draw_showcase(self, surface):
        a, r = self.app.assets, SHOWCASE
        mode = self.mode
        chaos = mode is not None and mode.id == "chaos"
        panel = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, ((0x26, 0x1E, 0x2B) if chaos else (0x1C, 0x2A, 0x25)) + (235,), panel.get_rect(),
                         border_radius=16)
        surface.blit(panel, r)
        pygame.draw.rect(surface, theme.CHAOS_MAGENTA if chaos else theme.GOLD_DIM, r, 2, border_radius=16)
        if mode is None:
            draw_paragraph(surface, a, "No mode is available yet.", r.inflate(-48, -48))
            return
        art = pygame.Rect(r.x, r.y + 12, r.w, 200)
        if chaos:
            draw_glow(surface, art.center, 120, theme.CHAOS_PURPLE, 10)
            face = a.image_fit(mood_face(a, "smug"), (190, 190))
            surface.blit(face, face.get_rect(center=art.center))
        else:
            draw_glow(surface, art.center, 110, theme.FELT_LIGHT, 10)
            icon = a.image_fit(mode.icon or "mode_normal", (150, 150))
            surface.blit(icon, icon.get_rect(center=art.center))
        title = a.font(theme.FONT_HEADING, role="display").render(mode.name, True,
                                                                   theme.CHAOS_MAGENTA if chaos else theme.GOLD)
        surface.blit(title, title.get_rect(midtop=(r.centerx, art.bottom + 4)))
        body = pygame.Rect(r.x + 28, art.bottom + 56, r.w - 56, r.bottom - art.bottom - 70)
        draw_paragraph(surface, a, self.mode_text(mode), body, color=theme.TEXT, size=theme.FONT_SMALL)

    def mode_text(self, mode) -> str:
        preview = self.preview_config()
        if preview is None:
            return mode.description
        try:
            from chaos_blackjack.codex import codex_entries

            entry = next(e for e in codex_entries("mode", preview[1]) if e.id == mode.id)
            return entry.detail(preview[1])
        except (StopIteration, ValueError, KeyError):
            return mode.description

    def draw_upgrades(self, surface, y):
        a = self.app.assets
        font = a.font(theme.FONT_SMALL)
        if not self.permanents:
            draw_paragraph(surface, a, "No permanent upgrades yet. Earn tokens and visit Upgrades.",
                           (RIGHT_X, y, RIGHT_W, 60))
            return
        preview = self.preview_config()
        effects = upgrade_effects(*preview) if preview else []
        lines = [(f"{o.name}", f"Lv {o.owned}/{o.max_level}") for o in self.permanents]
        bottom = ITEMS_TOP - 44
        for name, level in lines:
            if y + font.get_linesize() > bottom - 22 * min(2, len(effects)):
                surface.blit(font.render("…", True, theme.TEXT_MUTED), (RIGHT_X, y))
                y += font.get_linesize()
                break
            surface.blit(font.render(fit_text(font, name, RIGHT_W - 70), True, theme.IVORY), (RIGHT_X, y))
            lv = font.render(level, True, theme.GOLD)
            surface.blit(lv, lv.get_rect(topright=(RIGHT_X + RIGHT_W, y)))
            y += font.get_linesize()
        small = a.font(theme.FONT_TINY + 1)
        for line in effects:
            if y + small.get_linesize() > bottom:
                break
            surface.blit(small.render(fit_text(small, line, RIGHT_W), True, theme.GOLD), (RIGHT_X, y + 4))
            y += small.get_linesize()


__all__ = ["RunSetupScene", "upgrade_effects"]
