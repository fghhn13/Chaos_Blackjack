"""Card rendering and hand layout.

Faces are composed at runtime: `card_front_blank` art + rank text + suit
shapes drawn as polygons (no font glyphs needed, per the no-text-in-art rule).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.app.view import CardView
from chaos_blackjack.gui import theme

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

CARD_SIZE = (100, 150)
RED_SUITS = frozenset({"♥", "♦"})
SUITS = ("♠", "♥", "♦", "♣")


def draw_suit(surface: pygame.Surface, suit: str, center: tuple[float, float], size: float, color) -> None:
    """Draw ♠ ♥ ♦ ♣ as shapes. `size` is the glyph height."""
    cx, cy = center
    s = size / 2
    if suit == "♦":
        pygame.draw.polygon(surface, color, [(cx, cy - s), (cx + s * 0.72, cy), (cx, cy + s), (cx - s * 0.72, cy)])
        return
    if suit in ("♥", "♠"):
        flip = -1 if suit == "♠" else 1
        r = s * 0.5
        lobe_y = cy - flip * s * 0.38
        pygame.draw.circle(surface, color, (cx - r * 0.95, lobe_y), r)
        pygame.draw.circle(surface, color, (cx + r * 0.95, lobe_y), r)
        tip = (cx, cy + flip * s * 0.95)
        pygame.draw.polygon(surface, color, [(cx - r * 1.9, lobe_y + flip * r * 0.25), (cx + r * 1.9, lobe_y + flip * r * 0.25), tip])
        if suit == "♠":
            pygame.draw.polygon(surface, color, [(cx, cy + s * 0.2), (cx + s * 0.35, cy + s), (cx - s * 0.35, cy + s)])
        return
    if suit == "♣":
        r = s * 0.42
        for dx, dy in ((0, -s * 0.48), (-s * 0.5, s * 0.05), (s * 0.5, s * 0.05)):
            pygame.draw.circle(surface, color, (cx + dx, cy + dy), r)
        pygame.draw.polygon(surface, color, [(cx, cy - s * 0.1), (cx + s * 0.35, cy + s), (cx - s * 0.35, cy + s)])
        return
    pygame.draw.circle(surface, color, (cx, cy), s * 0.6, max(1, int(s * 0.15)))


class CardRenderer:
    def __init__(self, assets: "AssetManager") -> None:
        self.assets = assets
        self._cache: dict[tuple[str, str, bool, tuple[int, int]], pygame.Surface] = {}

    def render(self, card: CardView, size: tuple[int, int] = CARD_SIZE) -> pygame.Surface:
        key = (card.rank, card.suit, card.face_up, size)
        surf = self._cache.get(key)
        if surf is None:
            surf = self._compose(card, size)
            self._cache[key] = surf
        return surf

    def back(self, size: tuple[int, int] = CARD_SIZE) -> pygame.Surface:
        return self.render(CardView("", "", face_up=False), size)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _compose(self, card: CardView, size: tuple[int, int]) -> pygame.Surface:
        if not card.face_up:
            return self.assets.image("card_back", size)
        w, h = size
        surf = self.assets.image("card_front_blank", size).copy()
        color = theme.SUIT_RED if card.suit in RED_SUITS else theme.INK
        font = self.assets.font(max(10, int(h * 0.17)), bold=True)
        rank = font.render(card.rank, True, color)
        pad = int(w * 0.09)
        surf.blit(rank, (pad, int(h * 0.04)))
        small = h * 0.1
        draw_suit(surf, card.suit, (pad + rank.get_width() / 2, h * 0.04 + rank.get_height() + small * 0.55), small, color)
        corner = pygame.transform.rotate(surf.subsurface((0, 0, w // 2, h // 2)).copy(), 180)
        surf.blit(corner, (w - w // 2, h - h // 2))
        draw_suit(surf, card.suit, (w / 2, h / 2), h * 0.3, color)
        return surf


def layout_hand(
    count: int,
    center: tuple[int, int],
    card_size: tuple[int, int] = CARD_SIZE,
    max_width: int = 640,
) -> list[pygame.Rect]:
    """Rects for `count` cards fanned left-to-right around `center`; cards
    overlap more as the hand grows so it never exceeds `max_width`."""
    if count <= 0:
        return []
    w, h = card_size
    step = w + 14
    if count > 1 and w + step * (count - 1) > max_width:
        step = (max_width - w) / (count - 1)
    total = w + step * (count - 1)
    x0 = center[0] - total / 2
    return [pygame.Rect(int(x0 + i * step), center[1] - h // 2, w, h) for i in range(count)]


def deck_position(card_size: tuple[int, int] = CARD_SIZE) -> pygame.Rect:
    """Where the shoe sits (also the origin of deal animations later)."""
    return pygame.Rect(1110, 90, *card_size)


__all__ = ["CARD_SIZE", "CardRenderer", "SUITS", "deck_position", "draw_suit", "layout_hand"]
