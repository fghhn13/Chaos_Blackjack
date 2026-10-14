"""Shared look for the out-of-table screens: home, saves, run setup, upgrades,
collection, history and settings.

One backdrop, one header, one player badge and a few button shapes keep every
screen in the same visual language. The current player is chosen here too:
the last valid choice (kept in preferences) or the most recently played save.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack import meta
from chaos_blackjack.app.view import CardView
from chaos_blackjack.content.builtin_persona import default_persona
from chaos_blackjack.data.prefs import get_pref, set_pref
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.cards import CardRenderer
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, draw_focus_ring, fit_text, wrap_text

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

W, H = LOGICAL_SIZE
PLAYER_PREF = "gui.player_id"
MARGIN = 64


# ---------------------------------------------------------------- players


def current_player(app) -> meta.Player | None:
    """The player shown on the home screen: the last choice while it still
    exists, otherwise the most recently played save, otherwise slot order."""
    try:
        players = [s.player for s in meta.list_slots() if s.player is not None]
    except (ValueError, sqlite3.Error, OSError):
        return None
    if not players:
        return None
    wanted = app.session.get("player_id")
    if wanted is None:
        wanted = get_pref(PLAYER_PREF)
    chosen = next((p for p in players if p.id == wanted), None)
    if chosen is None:
        chosen = max(players, key=lambda p: (p.last_played_at or "", -p.slot))
    app.session["player_id"] = chosen.id
    apply_loadout(app, chosen.id)
    return chosen


def choose_player(app, player_id: int | None) -> None:
    app.session["player_id"] = player_id
    apply_loadout(app, player_id)
    try:
        set_pref(PLAYER_PREF, player_id)
    except (sqlite3.Error, OSError):
        pass  # the choice still holds for this session


def apply_loadout(app, player_id: int | None) -> None:
    """Draw the player's equipped cosmetics everywhere (none: the default looks)."""
    aliases: dict[str, str] = {}
    if player_id is not None:
        try:
            aliases = meta.asset_aliases(player_id)
        except (ValueError, sqlite3.Error, OSError):
            pass  # a missing or unreadable player shows the default looks
    app.assets.set_aliases(aliases)


def mode_name(mode_id: str) -> str:
    from chaos_blackjack.modes import get_mode

    try:
        return get_mode(mode_id).name
    except KeyError:
        return mode_id.replace("_", " ").title()


def run_summary(pending: meta.PendingRun) -> str:
    return f"{mode_name(pending.mode)}  ·  Round {max(1, pending.round)}  ·  {pending.money} chips"


# ---------------------------------------------------------------- drawing


def draw_backdrop(surface: pygame.Surface, assets: "AssetManager", *, shade: int = 150) -> None:
    """Menu art with a felt-dark wash; `shade` (0..255) keeps text readable."""
    surface.blit(assets.image("menu_background", LOGICAL_SIZE), (0, 0))
    wash = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
    wash.fill((*theme.DARK, shade))
    surface.blit(wash, (0, 0))


def draw_left_fade(surface: pygame.Surface, width: int = 620) -> None:
    """Darken the left side behind the title and menu, fading into the art."""
    fade = pygame.Surface((width, H), pygame.SRCALPHA)
    for x in range(0, width, 4):
        alpha = int(215 * (1 - x / width) ** 1.4)
        pygame.draw.rect(fade, (*theme.DARK, alpha), (x, 0, 4, H))
    surface.blit(fade, (0, 0))


def draw_header(surface: pygame.Surface, assets: "AssetManager", title: str, subtitle: str = "") -> None:
    font = assets.font(theme.FONT_HEADING + 4, role="display")
    surface.blit(font.render(fit_text(font, title, 700), True, theme.GOLD), (MARGIN, 34))
    if subtitle:
        small = assets.font(theme.FONT_SMALL + 1)
        surface.blit(small.render(fit_text(small, subtitle, 760), True, theme.TEXT_MUTED), (MARGIN + 2, 88))
    pygame.draw.line(surface, theme.GOLD_DIM, (MARGIN, 118), (W - MARGIN, 118), 1)


def draw_section(surface: pygame.Surface, assets: "AssetManager", label: str, pos: tuple[int, int], width: int) -> int:
    """Small-caps section label with a rule; returns the y below it."""
    img = assets.font(theme.FONT_TINY, bold=True).render(label.upper(), True, theme.GOLD_DIM)
    surface.blit(img, pos)
    y = pos[1] + img.get_height() + 5
    pygame.draw.line(surface, (*theme.GOLD_DIM,), (pos[0], y), (pos[0] + width, y), 1)
    return y + 10


def draw_paragraph(surface, assets, text: str, rect, *, color=theme.TEXT_MUTED, size: int = theme.FONT_SMALL) -> int:
    """Wrapped text inside `rect`; returns the y below the last line."""
    rect = pygame.Rect(rect)
    font = assets.font(size)
    line_h = font.get_linesize()
    y = rect.y
    for line in wrap_text(font, text, rect.w, max_lines=max(1, rect.h // line_h)):
        surface.blit(font.render(line, True, color), (rect.x, y))
        y += line_h
    return y


def draw_glow(surface: pygame.Surface, center: tuple[int, int], radius: int, color, strength: int = 7) -> None:
    glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -6):
        pygame.draw.circle(glow, (*color, strength), (radius, radius), r)
    surface.blit(glow, (center[0] - radius, center[1] - radius))


class DealerScene:
    """The right-hand vignette: the Chaos dealer behind a felt table edge,
    a few cards and chip stacks. Idle motion is slow and small."""

    def __init__(self, assets: "AssetManager", center_x: int = 905) -> None:
        self.assets = assets
        self.cards = CardRenderer(assets)
        self.cx = center_x
        self.time = 0.0
        self.mood = "neutral"

    def update(self, dt: float) -> None:
        self.time += dt
        # A brief welcoming gesture every few seconds; otherwise composed.
        self.mood = "welcome" if self.time % 7.0 > 5.6 else "neutral"

    def draw(self, surface: pygame.Surface, *, intensity: float = 1.0) -> None:
        a, t, cx = self.assets, self.time, self.cx
        bob = int(math.sin(t * 1.3) * 4)
        draw_glow(surface, (cx, 285 + bob), 230, theme.CHAOS_PURPLE, int(5 + 4 * intensity))
        face = a.image_fit(default_persona().asset_id(self.mood), (330, 330))
        surface.blit(face, face.get_rect(center=(cx, 290 + bob)))
        # Felt table edge in front of the dealer.
        table = pygame.Rect(0, 0, 980, 420)
        table.midtop = (cx + 40, 470)
        pygame.draw.ellipse(surface, theme.FELT, table)
        pygame.draw.ellipse(surface, theme.FELT_LIGHT, table.inflate(-60, -50), 2)
        pygame.draw.ellipse(surface, theme.GOLD_DIM, table, 3)
        # Cards slide in when the screen opens, then rest.
        arrive = min(1.0, t / 0.6)
        ease = 1 - (1 - arrive) ** 3
        cards = ((CardView("A", "♠"), -118, -9), (CardView("", "", face_up=False), -6, 4), (CardView("K", "♥"), 106, 11))
        for i, (card, dx, angle) in enumerate(cards):
            img = pygame.transform.rotozoom(self.cards.render(card, (84, 126)), angle, 1.0)
            x = cx + dx + int((1 - ease) * (260 + i * 40))
            y = 572 + int(math.sin(t * 0.9 + i) * 2)
            surface.blit(img, img.get_rect(center=(x, y)))
        for i, (value, x) in enumerate(((25, cx + 215), (10, cx + 275), (5, cx - 245))):
            chip = a.image(f"chip_{value}", (54, 54))
            for level in range(3 - i % 2):
                surface.blit(chip, chip.get_rect(center=(x, 612 - level * 7)))


# ---------------------------------------------------------------- widgets


class MenuItem(Button):
    """A home-menu entry. `weight` is primary (a gold slab with an optional
    summary line), secondary (outlined) or minor (text only)."""

    def __init__(self, assets, rect, text, on_click=None, *, weight="secondary", detail="",
                 chaos=False, note="", **kwargs) -> None:
        kwargs.setdefault("key_hint", "")
        super().__init__(assets, rect, text, on_click, **kwargs)
        self.weight = weight
        self.detail = detail
        self.chaos = chaos
        self.note = note  # e.g. "Needs a player": still clickable, drawn muted with a tag
        self.lift = 0.0

    def update(self, dt: float) -> None:
        target = 1.0 if (self.hovered or self.focused) and self.enabled else 0.0
        self.lift += (target - self.lift) * min(1.0, dt * 14)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        a = self.assets
        rect = self.rect.move(int(self.lift * 8), 0)
        accent = theme.CHAOS_MAGENTA if self.chaos else theme.GOLD
        if self.weight == "primary":
            fill = (0x3A, 0x2F, 0x3E) if self.chaos else (0x3B, 0x34, 0x24)
            hover = (0x4A, 0x3B, 0x4F) if self.chaos else (0x4C, 0x43, 0x2D)
            pygame.draw.rect(surface, hover if self.lift > 0.5 else fill, rect, border_radius=12)
            pygame.draw.rect(surface, accent, rect, 2, border_radius=12)
            title = a.font(theme.FONT_BUTTON + 4, bold=True).render(self.text, True, theme.IVORY)
            if self.detail:
                surface.blit(title, (rect.x + 26, rect.y + 12))
                small = a.font(theme.FONT_SMALL)
                detail = fit_text(small, self.detail, rect.w - 52)
                surface.blit(small.render(detail, True, accent), (rect.x + 27, rect.y + 48))
            else:
                surface.blit(title, title.get_rect(midleft=(rect.x + 26, rect.centery)))
            arrow = a.font(theme.FONT_BUTTON, bold=True).render("›", True, accent)
            surface.blit(arrow, arrow.get_rect(midright=(rect.right - 22, rect.centery - 2)))
        else:
            size = theme.FONT_BUTTON if self.weight == "secondary" else theme.FONT_BODY
            color = theme.IVORY if self.weight == "secondary" and not self.note else theme.TEXT_MUTED
            if self.lift > 0.05:
                color = theme.IVORY if not self.note else theme.TEXT
                bar = pygame.Rect(rect.x - 14, rect.y + 10, 3, rect.h - 20)
                pygame.draw.rect(surface, theme.GOLD_DIM if self.note else accent, bar, border_radius=2)
            label = a.font(size).render(self.text, True, color)
            label_rect = label.get_rect(midleft=(rect.x + 4, rect.centery))
            surface.blit(label, label_rect)
            if self.note:
                tag_font = a.font(theme.FONT_TINY, bold=True)
                tag = tag_font.render(self.note.upper(), True, theme.GOLD_DIM)
                box = tag.get_rect(midleft=(label_rect.right + 16, rect.centery)).inflate(14, 8)
                pygame.draw.rect(surface, theme.GOLD_DIM, box, 1, border_radius=box.h // 2)
                surface.blit(tag, tag.get_rect(center=box.center))
        if self.focused and self.enabled:
            draw_focus_ring(surface, rect)


class PlayerBadge(Button):
    """Top-right chip: the player's avatar, name and tokens; opens the profile."""

    def __init__(self, assets, player: meta.Player, on_click, *, right: int = W - MARGIN, top: int = 30) -> None:
        name_font = assets.font(theme.FONT_BODY, bold=True)
        name = fit_text(name_font, player.name, 230)
        tokens = f"{player.tokens} chips"
        width = name_font.size(name)[0] + assets.font(theme.FONT_SMALL).size(tokens)[0] + 100
        super().__init__(assets, (right - width, top, width, 46), name, on_click, key_hint="")
        self.tokens = tokens
        self.avatar = player.avatar

    def draw(self, surface: pygame.Surface) -> None:
        a, r = self.assets, self.rect
        fill = (0x2B, 0x31, 0x2E) if self.hovered else (0x1E, 0x25, 0x23)
        pygame.draw.rect(surface, fill, r, border_radius=23)
        pygame.draw.rect(surface, theme.GOLD if self.hovered else theme.GOLD_DIM, r, 1, border_radius=23)
        avatar = a.image(self.avatar, (36, 36))
        surface.blit(avatar, avatar.get_rect(center=(r.x + 24, r.centery)))
        name = a.font(theme.FONT_BODY, bold=True).render(self.text, True, theme.IVORY)
        surface.blit(name, name.get_rect(midleft=(r.x + 50, r.centery)))
        tokens = a.font(theme.FONT_SMALL).render(self.tokens, True, theme.GOLD)
        surface.blit(tokens, tokens.get_rect(midright=(r.right - 20, r.centery)))
        if self.focused:
            draw_focus_ring(surface, r, radius=27)
        if self.hovered:
            tip = a.font(theme.FONT_TINY).render("Profile", True, theme.TEXT_MUTED)
            surface.blit(tip, tip.get_rect(midtop=(r.centerx, r.bottom + 6)))


class EmptyBadge(Button):
    """Top-right placeholder while no player exists: says so and stays clickable."""

    def __init__(self, assets, on_click, *, right: int = W - MARGIN, top: int = 30) -> None:
        text = "No player yet"
        width = assets.font(theme.FONT_BODY).size(text)[0] + 70
        super().__init__(assets, (right - width, top, width, 46), text, on_click, key_hint="")

    def draw(self, surface: pygame.Surface) -> None:
        a, r = self.assets, self.rect
        fill = (0x2B, 0x31, 0x2E) if self.hovered else (0x1E, 0x25, 0x23)
        pygame.draw.rect(surface, fill, r, border_radius=23)
        pygame.draw.rect(surface, theme.GOLD_DIM, r, 1, border_radius=23)
        pygame.draw.circle(surface, theme.TEXT_MUTED, (r.x + 22, r.centery), 7, 1)
        label = a.font(theme.FONT_BODY).render(self.text, True, theme.TEXT_MUTED)
        surface.blit(label, label.get_rect(midleft=(r.x + 40, r.centery)))
        if self.focused:
            draw_focus_ring(surface, r, radius=27)


class OptionRow(Button):
    """A list row: icon, title, one detail line and a trailing note.

    `check` draws a check box (for multi-select lists); otherwise `selected`
    marks the single chosen row with an accent edge."""

    def __init__(self, assets, height: int, title: str, on_click=None, *, icon: str = "", detail: str = "",
                 note: str = "", check: bool | None = None, chaos: bool = False, enabled: bool = True,
                 tooltip: str = "") -> None:
        super().__init__(assets, (0, 0, 10, height), title, on_click, key_hint="", enabled=enabled,
                         tooltip=tooltip)
        self.icon = icon
        self.detail = detail
        self.note = note
        self.check = check
        self.chaos = chaos

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        a, r = self.assets, self.rect
        accent = theme.CHAOS_MAGENTA if self.chaos else theme.GOLD
        on = self.selected or bool(self.check)
        fill = (0x2A, 0x31, 0x2D) if self.hovered and self.enabled else (0x1E, 0x25, 0x23)
        if on:
            fill = (0x33, 0x2C, 0x36) if self.chaos else (0x31, 0x2E, 0x23)
        pygame.draw.rect(surface, fill, r, border_radius=10)
        edge = accent if on else (theme.GOLD_DIM if self.hovered and self.enabled else (0x34, 0x3B, 0x38))
        pygame.draw.rect(surface, edge, r, 2 if on else 1, border_radius=10)
        if self.selected:
            pygame.draw.rect(surface, accent, (r.x, r.y + 8, 4, r.h - 16), border_radius=2)
        x = r.x + 16
        muted = not self.enabled
        if self.icon:
            size = min(48, r.h - 16)
            icon = a.image_fit(self.icon, (size, size))
            if muted:
                icon = icon.copy()
                icon.set_alpha(100)
            surface.blit(icon, icon.get_rect(midleft=(x, r.centery)))
            x += size + 14
        right = r.right - 16
        if self.check is not None:
            box = pygame.Rect(0, 0, 22, 22)
            box.midright = (right, r.centery)
            pygame.draw.rect(surface, accent if self.check else theme.TEXT_MUTED, box, 2, border_radius=5)
            if self.check:
                pygame.draw.lines(surface, accent, False,
                                  [(box.x + 5, box.centery), (box.x + 9, box.bottom - 6), (box.right - 5, box.y + 5)], 3)
            right = box.x - 12
        if self.note:
            note_font = a.font(theme.FONT_SMALL, bold=True)
            note = note_font.render(self.note, True, accent if on else theme.TEXT_MUTED)
            surface.blit(note, note.get_rect(midright=(right, r.centery)))
            right -= note.get_width() + 14
        title_font = a.font(theme.FONT_BODY, bold=True)
        title_color = theme.TEXT_MUTED if muted else theme.IVORY
        title = title_font.render(fit_text(title_font, self.text, right - x), True, title_color)
        if self.detail:
            surface.blit(title, (x, r.centery - title.get_height() + 2))
            small = a.font(theme.FONT_TINY + 1)
            detail = small.render(fit_text(small, self.detail, right - x), True, theme.TEXT_MUTED)
            surface.blit(detail, (x, r.centery + 4))
        else:
            surface.blit(title, title.get_rect(midleft=(x, r.centery)))
        if self.focused and self.enabled:
            draw_focus_ring(surface, r)


class TextButton(Button):
    """Low-weight text action (Settings, Quit) that still shows focus."""

    def __init__(self, assets, rect, text, on_click=None, **kwargs) -> None:
        kwargs.setdefault("font_size", theme.FONT_BODY)
        super().__init__(assets, rect, text, on_click, style="ghost", **kwargs)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        color = theme.IVORY if self.hovered or self.focused else theme.TEXT_MUTED
        label = self.assets.font(self.font_size).render(self.text, True, color)
        rect = label.get_rect(midleft=(self.rect.x + 4, self.rect.centery))
        surface.blit(label, rect)
        if self.key_hint:
            cap = self.assets.font(theme.FONT_TINY, bold=True).render(self.key_hint, True, theme.TEXT_MUTED)
            surface.blit(cap, cap.get_rect(midleft=(rect.right + 10, rect.centery)))
        if self.hovered:
            pygame.draw.line(surface, theme.GOLD_DIM, (rect.x, rect.bottom + 2), (rect.right, rect.bottom + 2), 1)
        if self.focused:
            draw_focus_ring(surface, self.rect, radius=8)


def back_button(assets, on_click: Callable[[], None], text: str = "Back") -> Button:
    return Button(assets, (MARGIN, 642, 200, 50), text, on_click, style="ghost", hotkey=pygame.K_ESCAPE,
                  font_size=theme.FONT_BODY)


__all__ = [
    "DealerScene", "EmptyBadge", "MARGIN", "MenuItem", "OptionRow", "PLAYER_PREF", "PlayerBadge", "TextButton", "back_button",
    "apply_loadout", "choose_player", "current_player", "draw_backdrop", "draw_glow", "draw_header", "draw_left_fade",
    "draw_paragraph", "draw_section", "mode_name", "run_summary",
]
