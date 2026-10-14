"""Rows and the live preview for the Profile screen's Wardrobe and Achievements tabs.

Everything is drawn from the meta API's offers and states, so new cosmetics
and achievements need no layout changes.
"""

from __future__ import annotations

import pygame

from chaos_blackjack.cosmetics import Cosmetic
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.widgets import Button, draw_focus_ring, fit_text, wrap_text

RARITY_COLORS = {
    "common": theme.TEXT_MUTED,
    "rare": (0x7F, 0xA6, 0xC4),
    "epic": theme.CHAOS_MAGENTA,
    "legendary": theme.GOLD,
}
ROW_FILL = (0x1E, 0x25, 0x23)
ROW_FILL_HOVER = (0x2A, 0x31, 0x2D)
ROW_EDGE = (0x34, 0x3B, 0x38)


def draw_look(surface: pygame.Surface, assets, cosmetic: Cosmetic, box: pygame.Rect) -> None:
    """A cosmetic's own art fitted in `box` (a chip set shows its four chips, a
    deck its back and face). Previews never follow the equipped aliases, so each
    look shows itself."""
    m = cosmetic.asset_map()
    if cosmetic.slot == "deck":
        half = pygame.Rect(box.x, box.y, box.w // 2 - 2, box.h)
        for i, base in enumerate(("card_back", "card_front_blank")):
            img = assets.image_fit(m[base], half.size, alias=False)
            surface.blit(img, img.get_rect(center=half.move(i * (box.w // 2 + 2), 0).center))
        return
    if cosmetic.slot == "chips":
        size = min(box.h, box.w // 2)
        for i, base in enumerate(("chip_1", "chip_5", "chip_10", "chip_25")):
            img = assets.image(m[base], (size, size), alias=False)
            surface.blit(img, img.get_rect(center=(box.x + size // 2 + i * (box.w - size) // 3, box.centery)))
        return
    img = assets.image_fit(m[next(iter(m))], box.size, alias=False)
    surface.blit(img, img.get_rect(center=box.center))


def action_label(offer) -> str:
    if offer.equipped:
        return "Equipped"
    if offer.owned:
        return "Equip"
    if offer.price is not None:
        return f"Buy  ·  {offer.price} chips"
    return "Locked"


class CosmeticRow(Button):
    """One look. The row is its button: buy it (Shop) or equip it (Shop and Wardrobe)."""

    def __init__(self, assets, offer, on_click):
        enabled = (offer.owned and not offer.equipped) or offer.can_buy
        super().__init__(assets, (0, 0, 10, 84), offer.cosmetic.name, on_click, key_hint="", enabled=enabled)
        self.offer = offer

    def draw(self, surface):
        if not self.visible:
            return
        a, r, o, c = self.assets, self.rect, self.offer, self.offer.cosmetic
        hover = self.hovered and self.enabled
        pygame.draw.rect(surface, ROW_FILL_HOVER if self.hovered else ROW_FILL, r, border_radius=12)
        edge = theme.GOLD if o.equipped or hover else ROW_EDGE
        pygame.draw.rect(surface, edge, r, 2 if o.equipped else 1, border_radius=12)
        thumb = pygame.Rect(r.x + 14, r.y + 10, 112, r.h - 20)
        draw_look(surface, a, c, thumb)
        if not o.owned:
            veil = pygame.Surface(thumb.size, pygame.SRCALPHA)
            veil.fill((0x17, 0x1C, 0x1B, 120))
            surface.blit(veil, thumb)
        label = action_label(o)
        pill_font = a.font(theme.FONT_SMALL, bold=True)
        pill = pygame.Rect(0, 0, max(120, pill_font.size(label)[0] + 30), 36)
        pill.midright = (r.right - 16, r.centery)
        active = self.enabled
        pygame.draw.rect(surface, (0x3B, 0x34, 0x24) if active else (0x22, 0x28, 0x26), pill, border_radius=18)
        pygame.draw.rect(surface, theme.GOLD if active or o.equipped else (0x3A, 0x40, 0x3E), pill, 1,
                         border_radius=18)
        color = theme.IVORY if active else theme.GOLD if o.equipped else theme.TEXT_MUTED
        img = pill_font.render(label, True, color)
        surface.blit(img, img.get_rect(center=pill.center))
        x = thumb.right + 16
        width = pill.x - x - 14
        name_font = a.font(theme.FONT_BODY, bold=True)
        name = fit_text(name_font, c.name, width - 90)
        surface.blit(name_font.render(name, True, theme.IVORY if o.owned else theme.TEXT), (x, r.y + 12))
        tiny = a.font(theme.FONT_TINY, bold=True)
        rarity = tiny.render(c.rarity.upper(), True, RARITY_COLORS.get(c.rarity, theme.TEXT_MUTED))
        surface.blit(rarity, (x + name_font.size(name)[0] + 12, r.y + 17))
        small = a.font(theme.FONT_SMALL)
        detail = c.description if o.owned else o.unlock_hint
        if not o.owned and o.reason and o.price is not None and not o.can_buy:
            detail = f"{o.unlock_hint}  ·  {o.reason}"
        for i, line in enumerate(wrap_text(small, detail, width, max_lines=2)):
            surface.blit(small.render(line, True, theme.TEXT_MUTED), (x, r.y + 42 + i * small.get_linesize()))
        if self.focused and self.enabled:
            draw_focus_ring(surface, r)


class AchievementRow(Button):
    """One achievement: progress and reward. Rows only take focus so the
    keyboard can scroll the list."""

    def __init__(self, assets, state, cosmetic_names: tuple[str, ...] = ()):
        super().__init__(assets, (0, 0, 10, 74), state.achievement.name, None, key_hint="", sound=False)
        self.state = state
        self.cosmetic_names = cosmetic_names or state.reward_cosmetics

    def draw(self, surface):
        if not self.visible:
            return
        a, r, s = self.assets, self.rect, self.state
        ach = s.achievement
        secret = ach.hidden and not s.unlocked
        pygame.draw.rect(surface, ROW_FILL_HOVER if self.hovered else ROW_FILL, r, border_radius=12)
        pygame.draw.rect(surface, theme.GOLD if s.unlocked else ROW_EDGE, r, 1, border_radius=12)
        medal = (r.x + 40, r.centery)
        pygame.draw.circle(surface, (0x3B, 0x34, 0x24) if s.unlocked else (0x22, 0x28, 0x26), medal, 22)
        pygame.draw.circle(surface, theme.GOLD if s.unlocked else (0x3A, 0x40, 0x3E), medal, 22, 2)
        if s.unlocked:  # drawn, so no font needs a check mark glyph
            pygame.draw.lines(surface, theme.GOLD, False, [(medal[0] - 9, medal[1]), (medal[0] - 3, medal[1] + 7),
                                                           (medal[0] + 10, medal[1] - 7)], 3)
        elif secret:
            mark = a.font(theme.FONT_BODY, bold=True).render("?", True, theme.TEXT_MUTED)
            surface.blit(mark, mark.get_rect(center=medal))
        reward_parts = []
        if s.reward_tokens:
            reward_parts.append(f"+{s.reward_tokens} chips")
        reward_parts += list(self.cosmetic_names)
        reward = "  ·  ".join(reward_parts)
        small = a.font(theme.FONT_SMALL)
        reward_img = a.font(theme.FONT_SMALL, bold=True).render(reward, True,
                                                                theme.GOLD if s.unlocked else theme.TEXT_MUTED)
        surface.blit(reward_img, reward_img.get_rect(topright=(r.right - 20, r.y + 14)))
        x = r.x + 78
        width = r.right - x - reward_img.get_width() - 40
        name_font = a.font(theme.FONT_BODY, bold=True)
        name = "???" if secret else ach.name
        surface.blit(name_font.render(fit_text(name_font, name, width), True,
                                      theme.IVORY if s.unlocked else theme.TEXT), (x, r.y + 12))
        desc = "A hidden achievement." if secret else ach.description
        surface.blit(small.render(fit_text(small, desc, width), True, theme.TEXT_MUTED), (x, r.y + 42))
        if s.unlocked:
            done = a.font(theme.FONT_TINY).render("Unlocked", True, theme.GOLD_DIM)
            surface.blit(done, done.get_rect(bottomright=(r.right - 20, r.bottom - 12)))
        elif s.goal > 1:
            bar = pygame.Rect(0, 0, 200, 8)
            bar.bottomright = (r.right - 20, r.bottom - 16)
            pygame.draw.rect(surface, (0x2A, 0x31, 0x2D), bar, border_radius=4)
            fill = bar.copy()
            fill.w = int(bar.w * s.progress / s.goal)
            if fill.w:
                pygame.draw.rect(surface, theme.GOLD_DIM, fill, border_radius=4)
            count = a.font(theme.FONT_TINY).render(f"{s.progress} / {s.goal}", True, theme.TEXT_MUTED)
            surface.blit(count, count.get_rect(midright=(bar.x - 10, bar.centery)))
        if self.focused:
            draw_focus_ring(surface, r)


def draw_table_preview(surface: pygame.Surface, assets, looks: dict[str, Cosmetic], rect: pygame.Rect) -> None:
    """A small table showing a loadout together: felt, a card back and face, chip stacks and the avatar."""
    table = assets.image(looks["table"].asset_map()["table_background"], rect.size, alias=False)
    surface.blit(table, rect)
    pygame.draw.rect(surface, theme.GOLD_DIM, rect, 1, border_radius=4)
    deck = looks["deck"].asset_map()
    cx, cy = rect.centerx, rect.centery
    for base, dx in (("card_back", -88), ("card_front_blank", -8)):
        img = assets.image(deck[base], (74, 111), alias=False)
        surface.blit(img, img.get_rect(center=(cx + dx, cy - 6)))
    chips = looks["chips"].asset_map()
    for i, base in enumerate(("chip_25", "chip_10", "chip_5", "chip_1")):
        img = assets.image(chips[base], (46, 46), alias=False)
        for k in range(3 if i < 2 else 2):
            surface.blit(img, img.get_rect(center=(cx + 72 + i * 30, cy + 40 - k * 5)))
    avatar = assets.image(looks["avatar"].asset_map()["avatar"], (58, 58), alias=False)
    surface.blit(avatar, avatar.get_rect(topleft=(rect.x + 14, rect.y + 14)))
