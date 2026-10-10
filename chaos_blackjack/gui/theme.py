"""Palette and type scale — matches black-jack-assets/docs/generation-plan.md."""

from __future__ import annotations

Color = tuple[int, int, int]

# Muted, flat palette from the art direction: ink green felt, matte old gold,
# grey violet / grey rose for chaos, warm ivory for cards and text.
DARK: Color = (0x17, 0x1C, 0x1B)
FELT: Color = (0x26, 0x3B, 0x34)
FELT_LIGHT: Color = (0x31, 0x49, 0x3F)
GOLD: Color = (0xC2, 0xAE, 0x7E)
GOLD_DIM: Color = (0x7E, 0x71, 0x52)
CHAOS_PURPLE: Color = (0x88, 0x75, 0x8F)
CHAOS_MAGENTA: Color = (0xB9, 0x8A, 0xA2)
IVORY: Color = (0xE6, 0xE0, 0xD2)
INK: Color = (0x22, 0x24, 0x23)
SUIT_RED: Color = (0xA8, 0x35, 0x2F)
TEXT: Color = IVORY
TEXT_MUTED: Color = (0x8E, 0x96, 0x90)
PANEL: Color = (0x1E, 0x25, 0x23)
PANEL_ALPHA = 236  # side panels and bars drawn over the table art

CHIP_COLORS: dict[int, Color] = {
    1: (0xE6, 0xE0, 0xD2),
    5: (0x9A, 0x5B, 0x50),
    10: (0x5F, 0x74, 0x84),
    25: (0xB7, 0xA4, 0x77),
}

# Font sizes in logical pixels (canvas is 1280x720).
FONT_TINY = 14
FONT_SMALL = 16
FONT_BODY = 20
FONT_BUTTON = 24
FONT_HEADING = 36
FONT_TITLE = 64
