"""Procedural stand-ins for every manifest asset.

They exist so the game is fully playable before (or without) generated art.
Each function takes the target size and returns a new Surface.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.theme import Color

FontGetter = Callable[[int], pygame.font.Font]


def _lerp(a: Color, b: Color, t: float) -> Color:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _vertical_gradient(size: tuple[int, int], top: Color, bottom: Color) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size)
    for y in range(h):
        pygame.draw.line(surf, _lerp(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    return surf


def _vignette(surf: pygame.Surface, strength: int = 160) -> None:
    """Darken toward the edges with stacked translucent frames."""
    w, h = surf.get_size()
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    band = max(1, min(w, h) // 5)
    for i in range(band):
        alpha = int(strength * (1 - i / band) ** 2 / band * 4)
        pygame.draw.rect(shade, (0, 0, 0, min(255, alpha)), (i, i, w - 2 * i, h - 2 * i), 1)
    surf.blit(shade, (0, 0))


def _label(surf: pygame.Surface, text: str, font: pygame.font.Font, color: Color, center) -> None:
    img = font.render(text, True, color)
    surf.blit(img, img.get_rect(center=center))


# ---------------------------------------------------------------- backgrounds

def felt_table(felt: Color, felt_light: Color, rail: Color) -> Callable[..., pygame.Surface]:
    """A felt table in any colours (the default table and table cosmetics)."""

    def draw(size, fonts: FontGetter) -> pygame.Surface:
        w, h = size
        surf = pygame.Surface(size)
        surf.fill(theme.DARK)
        cx, cy = w / 2, h / 2
        max_r = math.hypot(cx, cy)
        for r in range(int(max_r), 0, -6):
            t = r / max_r
            pygame.draw.circle(surf, _lerp(felt_light, felt, min(1.0, t * 1.3)), (cx, cy), r)
        edge = pygame.Rect(0, 0, int(w * 0.86), int(h * 0.78))
        edge.center = (int(cx), int(cy))
        pygame.draw.ellipse(surf, rail, edge, max(2, w // 400))
        _vignette(surf)
        return surf

    return draw


table_background = felt_table(theme.FELT, theme.FELT_LIGHT, theme.GOLD_DIM)


def menu_background(size, fonts: FontGetter) -> pygame.Surface:
    w, h = size
    surf = _vertical_gradient(size, (0x14, 0x10, 0x1C), theme.DARK)
    rng = [(0.12, 0.18, 0.5), (0.31, 0.04, 0.3), (0.58, 0.12, 0.6), (0.77, 0.03, 0.4)]
    for y, height, length in rng:
        bar = pygame.Surface((int(w * length), max(2, int(h * height * 0.08))), pygame.SRCALPHA)
        bar.fill((*theme.CHAOS_MAGENTA, 50))
        surf.blit(bar, (int(w * (1 - length)), int(h * y)))
    pygame.draw.circle(surf, (*theme.CHAOS_PURPLE,), (int(w * 0.78), int(h * 0.55)), int(h * 0.28), 3)
    _vignette(surf)
    return surf


def _ending(size, fonts: FontGetter, top: Color, glow: Color) -> pygame.Surface:
    w, h = size
    surf = _vertical_gradient(size, top, theme.DARK)
    g = pygame.Surface(size, pygame.SRCALPHA)
    for r in range(int(h * 0.45), 0, -8):
        pygame.draw.circle(g, (*glow, 5), (w // 2, int(h * 0.38)), r)
    surf.blit(g, (0, 0))
    _vignette(surf)
    return surf


def ending_victory(size, fonts: FontGetter) -> pygame.Surface:
    return _ending(size, fonts, (0x2A, 0x22, 0x10), theme.GOLD)


def ending_bankrupt(size, fonts: FontGetter) -> pygame.Surface:
    return _ending(size, fonts, (0x18, 0x1A, 0x1C), theme.TEXT_MUTED)


# ---------------------------------------------------------------------- cards

def _card_shape(size) -> tuple[pygame.Surface, pygame.Rect, int]:
    surf = pygame.Surface(size, pygame.SRCALPHA)
    rect = surf.get_rect()
    radius = max(4, size[0] // 12)
    return surf, rect, radius


def card_front_blank(size, fonts: FontGetter) -> pygame.Surface:
    surf, rect, radius = _card_shape(size)
    pygame.draw.rect(surf, theme.IVORY, rect, border_radius=radius)
    inner = rect.inflate(-size[0] // 10, -size[0] // 10)
    pygame.draw.rect(surf, (0xD8, 0xCC, 0xB4), inner, max(1, size[0] // 128), border_radius=radius // 2)
    pygame.draw.rect(surf, (0x9E, 0x93, 0x7E), rect, max(1, size[0] // 96), border_radius=radius)
    return surf


def lattice_back(base: Color, lattice: Color, trim: Color, edge: Color) -> Callable[..., pygame.Surface]:
    """A lattice card back in any colours (the default back and card back cosmetics)."""

    def draw(size, fonts: FontGetter) -> pygame.Surface:
        surf, rect, radius = _card_shape(size)
        w, h = size
        pygame.draw.rect(surf, base, rect, border_radius=radius)
        inner = rect.inflate(-w // 8, -w // 8)
        step = max(6, w // 8)
        clip = surf.subsurface(inner)
        for x in range(-h, w + h, step):
            pygame.draw.line(clip, lattice, (x, 0), (x + h, h), max(1, w // 128))
            pygame.draw.line(clip, lattice, (x + h, 0), (x, h), max(1, w // 128))
        pygame.draw.rect(surf, trim, inner, max(1, w // 64), border_radius=radius // 2)
        c = rect.center
        d = w // 6
        pygame.draw.polygon(surf, trim, [(c[0], c[1] - d), (c[0] + d, c[1]), (c[0], c[1] + d), (c[0] - d, c[1])])
        pygame.draw.rect(surf, edge, rect, max(1, w // 96), border_radius=radius)
        return surf

    return draw


card_back = lattice_back((0x2A, 0x12, 0x3A), theme.CHAOS_PURPLE, theme.GOLD, theme.GOLD_DIM)


# ---------------------------------------------------------------------- chips

def chip(color: Color, spots: Color | None = None) -> Callable[..., pygame.Surface]:
    """A chip in `color`; edge spots are ivory (red on the white chip) unless given."""
    if spots is None:
        spots = theme.IVORY if color != theme.CHIP_COLORS[1] else theme.SUIT_RED

    def draw(size, fonts: FontGetter) -> pygame.Surface:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w = min(size)
        c = (size[0] // 2, size[1] // 2)
        r = int(w * 0.46)
        pygame.draw.circle(surf, _lerp(color, (0, 0, 0), 0.35), (c[0], c[1] + w // 40), r)
        pygame.draw.circle(surf, color, c, r)
        for i in range(8):
            a = i * math.pi / 4
            p = (c[0] + math.cos(a) * r * 0.85, c[1] + math.sin(a) * r * 0.85)
            pygame.draw.circle(surf, spots, p, max(2, w // 18))
        pygame.draw.circle(surf, _lerp(color, theme.IVORY, 0.35), c, int(r * 0.62))
        pygame.draw.circle(surf, _lerp(color, (0, 0, 0), 0.25), c, int(r * 0.62), max(1, w // 64))
        return surf

    return draw


# -------------------------------------------------------------------- avatars

def avatar(emblem: str, background: Color, ring: Color, ink: Color = theme.IVORY) -> Callable[..., pygame.Surface]:
    """A round player portrait with an emblem: "bust", "spade" or "flag" (shapes, so
    no font needs the glyph)."""

    def draw(size, fonts: FontGetter) -> pygame.Surface:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w = min(size)
        cx, cy = size[0] // 2, size[1] // 2
        r = int(w * 0.47)
        pygame.draw.circle(surf, background, (cx, cy), r)
        if emblem == "spade":
            d = r * 0.42
            pygame.draw.circle(surf, ink, (int(cx - d * 0.5), int(cy + d * 0.05)), int(d * 0.55))
            pygame.draw.circle(surf, ink, (int(cx + d * 0.5), int(cy + d * 0.05)), int(d * 0.55))
            pygame.draw.polygon(surf, ink, [(cx, cy - d * 1.25), (cx + d * 1.02, cy - d * 0.05),
                                            (cx - d * 1.02, cy - d * 0.05)])
            pygame.draw.polygon(surf, ink, [(cx, cy + d * 0.2), (cx + d * 0.42, cy + d * 1.15),
                                            (cx - d * 0.42, cy + d * 1.15)])
        elif emblem == "flag":
            pole = max(2, w // 40)
            pygame.draw.line(surf, ink, (cx - r * 0.3, cy - r * 0.55), (cx - r * 0.3, cy + r * 0.6), pole)
            pygame.draw.polygon(surf, ink, [(cx - r * 0.3, cy - r * 0.55), (cx + r * 0.42, cy - r * 0.38),
                                            (cx + r * 0.3, cy - r * 0.12), (cx + r * 0.45, cy + r * 0.08),
                                            (cx - r * 0.3, cy + r * 0.02)])
        else:
            pygame.draw.circle(surf, ink, (cx, cy - int(r * 0.22)), int(r * 0.3))
            body = pygame.Rect(0, 0, int(r * 1.2), int(r * 0.9))
            body.midtop = (cx, cy + int(r * 0.15))
            pygame.draw.ellipse(surf, ink, body)
            mask = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (cx, cy), r)
            surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        pygame.draw.circle(surf, ring, (cx, cy), r, max(2, w // 24))
        return surf

    return draw


# --------------------------------------------------------------- chaos dealer

_EXPRESSIONS = {
    # (brow tilt, mouth: "flat" | "smile" | "open" | "frown")
    "calm": (0.0, "flat"),
    "smug": (0.15, "smile"),
    "laugh": (0.05, "open"),
    "angry": (-0.35, "frown"),
}


def chaos_character(expression: str) -> Callable[..., pygame.Surface]:
    tilt, mouth = _EXPRESSIONS[expression]

    def draw(size, fonts: FontGetter) -> pygame.Surface:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w, h = size
        cx, cy = w // 2, int(h * 0.56)
        r = int(min(w, h) * 0.34)
        # horns
        for side in (-1, 1):
            base = (cx + side * r * 0.55, cy - r * 0.7)
            pygame.draw.polygon(
                surf, theme.CHAOS_MAGENTA,
                [base, (base[0] + side * r * 0.35, base[1] - r * 0.75), (base[0] + side * r * 0.45, base[1] + r * 0.2)],
            )
        pygame.draw.circle(surf, (0x3A, 0x1A, 0x50), (cx, cy), r)
        pygame.draw.circle(surf, theme.CHAOS_PURPLE, (cx, cy), r, max(2, w // 80))
        # eyes + brows
        for side in (-1, 1):
            ex, ey = cx + side * r * 0.38, cy - r * 0.12
            pygame.draw.circle(surf, theme.GOLD, (ex, ey), r * 0.12)
            dy = tilt * r * side
            pygame.draw.line(
                surf, theme.IVORY,
                (ex - r * 0.2, ey - r * 0.3 - dy), (ex + r * 0.2, ey - r * 0.3 + dy),
                max(2, w // 60),
            )
        mw = r * 0.7
        my = cy + r * 0.42
        mrect = pygame.Rect(0, 0, mw, r * 0.45)
        mrect.center = (cx, int(my))
        lw = max(2, w // 60)
        if mouth == "flat":
            pygame.draw.line(surf, theme.IVORY, (cx - mw / 2, my), (cx + mw / 2, my), lw)
        elif mouth == "smile":
            pygame.draw.arc(surf, theme.IVORY, mrect.move(mw * 0.1, -r * 0.2), math.pi * 1.1, math.pi * 1.9, lw)
        elif mouth == "open":
            pygame.draw.ellipse(surf, theme.DARK, mrect)
            pygame.draw.ellipse(surf, theme.IVORY, mrect, lw)
        else:
            pygame.draw.arc(surf, theme.IVORY, mrect.move(0, r * 0.15), math.pi * 0.15, math.pi * 0.85, lw)
        return surf

    return draw


# ---------------------------------------------------------------------- icons

def icon(glyph: str, color: Color) -> Callable[..., pygame.Surface]:
    """Rounded badge with a short glyph — placeholder for item / rule icons."""

    def draw(size, fonts: FontGetter) -> pygame.Surface:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w = min(size)
        rect = pygame.Rect(0, 0, int(w * 0.76), int(w * 0.76))
        rect.center = (size[0] // 2, size[1] // 2)
        pygame.draw.rect(surf, _lerp(color, theme.DARK, 0.7), rect, border_radius=w // 6)
        pygame.draw.rect(surf, color, rect, max(2, w // 40), border_radius=w // 6)
        _label(surf, glyph, fonts(max(10, int(w * 0.3))), color, rect.center)
        return surf

    return draw


def missing(size, fonts: FontGetter) -> pygame.Surface:
    """Magenta/black checker for ids that are neither on disk nor in the manifest."""
    surf = pygame.Surface(size)
    cell = max(4, min(size) // 8)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            on = (x // cell + y // cell) % 2 == 0
            surf.fill(theme.CHAOS_MAGENTA if on else (0, 0, 0), (x, y, cell, cell))
    return surf
