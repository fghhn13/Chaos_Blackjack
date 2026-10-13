"""Draws widget data (app/widgets.py): one renderer per widget kind.

`WidgetView` stacks a part's widgets in a column of a given width. It knows
nothing about tables: clickable elements carry an `Act` that is handed to
`on_act`, hovering shows the element's tooltip. `measure()` and `draw()` run
the same code, so the height always matches what is drawn.

Adding a widget kind: a function `_<kind>(r, widget, x, y, w) -> height`
registered in RENDERERS (and the dataclass in app/widgets.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pygame

from chaos_blackjack.app.widgets import Act, Widget
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.texts import BAD, GOOD
from chaos_blackjack.gui.widgets import draw_tooltip, fit_text, wrap_text

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

WARN = (0xE0, 0xB0, 0x60)
TONES: dict[str, tuple[int, int, int]] = {
    "": theme.IVORY, "good": GOOD, "bad": BAD, "warn": WARN, "chaos": theme.CHAOS_MAGENTA,
    "muted": theme.TEXT_MUTED, "gold": theme.GOLD,
}
LOG_COLORS = {"hand": theme.IVORY, "chaos": theme.CHAOS_MAGENTA, "deck": (0xD8, 0x8A, 0x7A),
              "money": theme.GOLD, "shop": (0x9C, 0xB8, 0xD8), "items": GOOD}
GAP = 10


def tone(name: str) -> tuple[int, int, int]:
    return TONES.get(name, theme.IVORY)


def _dim(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """A disabled element's edge: the colour at about 60%."""
    return tuple(round(c * 0.6) for c in color)  # type: ignore[return-value]


@dataclass
class Hit:
    rect: pygame.Rect
    act: Act | None = None
    tooltip: str = ""


@dataclass
class _Render:
    assets: "AssetManager"
    surface: pygame.Surface | None          # None while measuring
    full: bool
    hits: list[Hit]
    state: dict[str, Any] = field(default_factory=dict)
    hover: tuple[int, int] = (-1, -1)

    def blit(self, img: pygame.Surface, pos) -> None:
        if self.surface is not None:
            self.surface.blit(img, pos)

    def rect(self, color, rect, width: int = 0, radius: int = 0) -> None:
        if self.surface is not None:
            pygame.draw.rect(self.surface, color, rect, width, border_radius=radius)

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        return self.assets.font(size, bold=bold)

    def heading(self, text: str, x: int, y: int, w: int) -> int:
        if not text:
            return y
        img = self.font(theme.FONT_TINY, bold=True).render(text.upper(), True, theme.GOLD_DIM)
        self.blit(img, (x, y))
        y += img.get_height() + 3
        if self.surface is not None:
            pygame.draw.line(self.surface, theme.GOLD_DIM, (x, y), (x + w, y), 1)
        return y + 6

    def icon(self, asset_id: str, rect: pygame.Rect, alpha: int = 255) -> None:
        if self.surface is None or not asset_id:
            return
        img = self.assets.image(asset_id, rect.size)
        if alpha < 255:
            img = img.copy()
            img.set_alpha(alpha)
        self.surface.blit(img, rect)

    def hovered(self, rect: pygame.Rect) -> bool:
        return rect.collidepoint(self.hover)


# --------------------------------------------------------------- renderers


def _stat(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    size = 24
    if w.icon:
        r.icon(w.icon, pygame.Rect(x, y + 2, size, size))
    tx = x + (size + 8 if w.icon else 0)
    r.blit(r.font(theme.FONT_TINY).render(w.label, True, theme.TEXT_MUTED), (tx, y))
    r.blit(r.font(theme.FONT_BODY, bold=True).render(w.value, True, tone(w.tone)), (tx, y + 14))
    r.hits.append(Hit(pygame.Rect(x, y, width, 40), None, w.tooltip))
    return 40


def _badges(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    y = r.heading(w.title, x, y, width) if r.full else y
    font = r.font(theme.FONT_SMALL, bold=True)
    cx, cy, h = x, y, 30
    for b in w.items:
        text = font.render(b.text, True, tone(b.tone))
        chip = pygame.Rect(cx, cy, 8 + 20 + 6 + text.get_width() + 10, h)
        if chip.right > x + width and cx > x:
            cx, cy = x, cy + h + 6
            chip.topleft = (cx, cy)
        hot = r.hovered(chip) and b.act is not None
        r.rect(theme.FELT if hot else theme.DARK, chip, 0, 15)
        r.rect(tone(b.tone) if b.tone else theme.GOLD_DIM, chip, 1, 15)
        r.icon(b.icon, pygame.Rect(chip.x + 8, chip.y + 5, 20, 20))
        r.blit(text, (chip.x + 34, chip.centery - text.get_height() // 2))
        r.hits.append(Hit(chip, b.act, b.tooltip))
        cx = chip.right + 6
    return (cy + h) - top if w.items else 0


def _bars(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    small = r.font(theme.FONT_TINY)
    if w.compact:
        if w.title or w.note:
            if w.title:
                r.blit(r.font(theme.FONT_TINY, bold=True).render(w.title.upper(), True, theme.GOLD_DIM), (x, y))
            if w.note:
                note = small.render(w.note, True, theme.IVORY)
                r.blit(note, (x + width - note.get_width(), y))
            y += 18
        n = max(1, len(w.bars))
        step = width / n
        most = max((b.value for b in w.bars), default=1) or 1
        for i, b in enumerate(w.bars):
            h = max(2, round(30 * b.value / most)) if b.value else 1
            rect = pygame.Rect(round(x + i * step + 1), y + 30 - h, max(2, round(step) - 3), h)
            r.rect(BAD if b.tone == "bad" else theme.GOLD_DIM if b.value else theme.TEXT_MUTED, rect, 0, 2)
            r.hits.append(Hit(pygame.Rect(round(x + i * step), y, max(2, round(step)), 34), w.act,
                              f"{b.label}: {b.value}"))
        y += 34
        area = pygame.Rect(x, top, width, y - top)
        r.hits.insert(0, Hit(area, w.act, ""))  # fallback for the gaps between bars
        return y - top
    y = r.heading(w.title, x, y, width)
    legend = None
    if w.baseline:
        legend = small.render(f"{w.baseline_label}: {w.baseline}".strip(": "), True, theme.TEXT_MUTED)
    if w.note or legend is not None:
        if w.note:
            room = width - (legend.get_width() + 40 if legend is not None else 0)
            r.blit(small.render(fit_text(small, w.note, room), True, theme.TEXT_MUTED), (x, y))
        if legend is not None:  # a dashed sample, then the reference's name
            lx = x + width - legend.get_width()
            r.blit(legend, (lx, y))
            if r.surface is not None:
                for dx in (0, 10, 20):
                    pygame.draw.line(r.surface, theme.TEXT_MUTED, (lx - 34 + dx, y + 9), (lx - 29 + dx, y + 9), 1)
        y += 20
    y += 18  # room for the counts above the tallest bar
    n = max(1, len(w.bars))
    step = width / n
    top_value = max([b.value for b in w.bars] + [w.baseline or 0]) or 1
    chart = 120
    bar_w = min(44, max(6, round(step * 0.55)))
    if w.baseline and r.surface is not None:  # behind the bars and their counts
        by = y + chart - round(chart * w.baseline / top_value)
        for dx in range(0, width, 10):
            pygame.draw.line(r.surface, theme.TEXT_MUTED, (x + dx, by), (x + min(dx + 5, width), by), 1)
    for i, b in enumerate(w.bars):
        cx = round(x + i * step + step / 2)
        h = round(chart * b.value / top_value) if b.value else 0
        count = small.render(str(b.value), True, theme.IVORY if b.value else theme.TEXT_MUTED)
        spot = count.get_rect(midbottom=(cx, y + chart - h - 2))
        r.rect(theme.PANEL, spot.inflate(6, 0))
        r.blit(count, spot)
        if h:
            r.rect(tone(b.tone) if b.tone else theme.GOLD_DIM, pygame.Rect(cx - bar_w // 2, y + chart - h, bar_w, h), 0, 3)
        label = r.font(theme.FONT_SMALL, bold=True).render(b.label, True, tone(b.tone) if b.tone else theme.IVORY)
        r.blit(label, (cx - label.get_width() // 2, y + chart + 6))
        r.hits.append(Hit(pygame.Rect(cx - step / 2, y, step, chart + 26), None, f"{b.label}: {b.value}"))
    return y + chart + 30 - top


def _progress(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    y = r.heading(w.title, x, y, width)
    font = r.font(theme.FONT_SMALL)
    r.blit(font.render(w.label, True, theme.TEXT_MUTED), (x, y))
    value = font.render(f"{w.value} / {w.maximum}", True, tone(w.tone))
    r.blit(value, (x + width - value.get_width(), y))
    y += 22
    bar = pygame.Rect(x, y, width, 12)
    r.rect(theme.DARK, bar, 0, 6)
    k = max(0.0, min(1.0, w.value / max(1, w.maximum)))
    if k:
        r.rect(tone(w.tone) if w.tone else theme.GOLD_DIM, pygame.Rect(x, y, max(8, round(width * k)), 12), 0, 6)
    r.rect(theme.GOLD_DIM, bar, 1, 6)
    return y + 18 - top


def _list(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    y = r.heading(w.title, x, y, width)
    tiny = r.font(theme.FONT_TINY)
    if not w.entries:
        if w.empty:
            r.blit(tiny.render(fit_text(tiny, w.empty, width), True, theme.TEXT_MUTED), (x, y + 2))
            y += 22
        return y - top
    if w.compact:  # icons (or short chips) in a row, details on hover
        cx, size = x, 34
        for e in w.entries:
            if e.icon:
                rect = pygame.Rect(cx, y, size, size)
                if rect.right > x + width:
                    cx, y = x, y + size + 6
                    rect.topleft = (cx, y)
                r.rect(theme.FELT if r.hovered(rect) else theme.DARK, rect, 0, 8)
                r.icon(e.icon, rect.inflate(-6, -6))
            else:
                text = r.font(theme.FONT_SMALL, bold=True).render(f"{e.title} {e.badge}".strip(), True, tone(e.tone))
                rect = pygame.Rect(cx, y, text.get_width() + 16, size)
                if rect.right > x + width and cx > x:
                    cx, y = x, y + size + 6
                    rect.topleft = (cx, y)
                r.rect(theme.DARK, rect, 0, 8)
                r.blit(text, (rect.x + 8, rect.centery - text.get_height() // 2))
            r.hits.append(Hit(rect, e.act, e.tooltip or (f"{e.title}: {e.text}" if e.text else e.title)))
            cx = rect.right + 6
        return y + size + 4 - top
    body, small = r.font(theme.FONT_SMALL, bold=True), r.font(theme.FONT_SMALL)
    icon = 36 if r.full else 30
    for e in w.entries:
        lines = wrap_text(small if r.full else tiny, e.text, width - icon - 26, max_lines=3 if r.full else 1) if e.text else []
        lh = (small if r.full else tiny).get_linesize()
        h = max(icon + 8, 24 + lh * len(lines) + 6)
        row = pygame.Rect(x, y, width, h)
        usable = e.act is not None and e.act.enabled
        if r.hovered(row) and usable:
            r.rect(theme.FELT, row, 0, 8)
            r.rect(theme.GOLD, row, 1, 8)
        tx = x + 8
        if e.icon:
            box = pygame.Rect(x + 6, y + 4, icon, icon)
            if e.frame in theme.GROUP_COLORS:
                r.rect(theme.GROUP_COLORS[e.frame], box.inflate(4, 4), 1, 6)
            r.icon(e.icon, box, 255 if usable or e.act is None else 120)
            tx = x + icon + 16
        badge_w = 0
        if e.badge:
            badge = body.render(e.badge, True, theme.GOLD)
            badge_w = badge.get_width() + 10
            r.blit(badge, (row.right - badge.get_width() - 8, y + 6))
        r.blit(body.render(fit_text(body, e.title, row.right - tx - badge_w - 8), True, tone(e.tone)), (tx, y + 4))
        for i, line in enumerate(lines):
            r.blit((small if r.full else tiny).render(line, True, theme.TEXT_MUTED), (tx, y + 24 + i * lh))
        r.hits.append(Hit(row, e.act, e.tooltip))
        y += h + 4
    return y - top


def _rows(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    y = r.heading(w.title, x, y, width)
    font = r.font(theme.FONT_SMALL)
    lh = font.get_linesize() + 4
    for row in w.rows:
        r.blit(font.render(fit_text(font, row.label, width // 2), True, theme.TEXT_MUTED), (x, y))
        value = font.render(fit_text(font, row.value, width // 2), True, tone(row.tone))
        r.blit(value, (x + width - value.get_width(), y))
        y += lh
    return y - top + 2


def _slots(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    tiny = r.font(theme.FONT_TINY, bold=True)
    if w.title:
        r.blit(tiny.render(w.title.upper(), True, theme.GOLD_DIM), (x, y))
        y += 18
    if not w.slots:
        r.blit(r.font(theme.FONT_TINY).render(w.empty, True, theme.TEXT_MUTED), (x, y))
        return y + 20 - top
    cols = max(1, w.columns)
    size = min(52, (width - (cols - 1) * 6) // cols)
    for i, s in enumerate(w.slots):
        row, col = divmod(i, cols)
        rect = pygame.Rect(x + col * (size + 6), y + row * (size + 6), size, size)
        usable = s.act is not None and s.act.enabled
        r.rect(theme.FELT if r.hovered(rect) and usable else theme.DARK, rect, 0, 8)
        edge = theme.GROUP_COLORS.get(s.frame, theme.GOLD)
        r.rect(edge if usable else _dim(edge), rect, 2 if s.frame else 1, 8)
        r.icon(s.icon, rect.inflate(-10, -10), 255 if usable else 110)
        if s.count > 1:
            count = tiny.render(f"×{s.count}", True, theme.GOLD)
            r.blit(count, (rect.right - count.get_width() - 3, rect.bottom - count.get_height() - 1))
        if s.hotkey:
            r.blit(r.font(theme.FONT_TINY).render(s.hotkey, True, theme.TEXT_MUTED), (rect.x + 4, rect.y + 2))
        r.hits.append(Hit(rect, s.act, s.tooltip))
    rows = (len(w.slots) + cols - 1) // cols
    return y + rows * (size + 6) - top


def _log(r: _Render, w: Any, x: int, y: int, width: int) -> int:
    top = y
    font = r.font(theme.FONT_SMALL)
    if not r.full:  # tail: the last lines, one line each
        for line in w.lines:
            color = LOG_COLORS.get(line.category, theme.IVORY)
            r.blit(font.render(fit_text(font, line.text, width), True, color), (x, y))
            y += font.get_linesize() + 2
        return y - top
    y = r.heading(w.title, x, y, width)
    chosen = r.state.get("log_filter", "")
    cx = x
    chip_font = r.font(theme.FONT_TINY, bold=True)
    for cat in ("", *w.categories):
        text = chip_font.render((cat or "all").upper(), True, theme.DARK if cat == chosen else LOG_COLORS.get(cat, theme.IVORY))
        chip = pygame.Rect(cx, y, text.get_width() + 18, 24)
        r.rect(LOG_COLORS.get(cat, theme.GOLD) if cat == chosen else theme.DARK, chip, 0, 12)
        r.rect(theme.GOLD_DIM, chip, 1, 12)
        r.blit(text, (chip.x + 9, chip.centery - text.get_height() // 2))
        r.hits.append(Hit(chip, Act("gui:log_filter", cat)))
        cx = chip.right + 6
    y += 34
    lines = [line for line in w.lines if not chosen or line.category == chosen]
    if not lines:
        r.blit(font.render("Nothing recorded yet.", True, theme.TEXT_MUTED), (x, y))
        return y + 24 - top
    rounds: dict[int, list] = {}
    for line in lines:
        rounds.setdefault(line.round, []).append(line)
    for number in sorted(rounds, reverse=True):  # newest round first, its lines in order
        y += 4
        r.blit(r.font(theme.FONT_TINY, bold=True).render(f"ROUND {number}", True, theme.GOLD_DIM), (x, y))
        y += 18
        for line in rounds[number]:
            for part in wrap_text(font, line.text, width - 16, max_lines=3):
                r.blit(font.render(part, True, LOG_COLORS.get(line.category, theme.IVORY)), (x + 12, y))
                y += font.get_linesize()
            y += 2
    return y - top


RENDERERS: dict[str, Callable[[_Render, Any, int, int, int], int]] = {
    "stat": _stat, "badges": _badges, "bars": _bars, "progress": _progress,
    "list": _list, "rows": _rows, "slots": _slots, "log": _log,
}


class WidgetView:
    """A column of widgets; `full` is the run panel's larger style."""

    def __init__(self, assets: "AssetManager", widgets: tuple[Widget, ...], width: int, *, full: bool = False,
                 on_act: Callable[[Act], None] | None = None, state: dict | None = None) -> None:
        self.assets = assets
        self.widgets = widgets
        self.width = width
        self.full = full
        self.on_act = on_act
        self.state = state if state is not None else {}
        self.hits: list[Hit] = []
        self.hover: tuple[int, int] = (-1, -1)
        self.origin = (0, 0)

    def _run(self, surface: pygame.Surface | None, x: int, y: int, offset: tuple[int, int] = (0, 0)) -> int:
        hover = (self.hover[0] - offset[0], self.hover[1] - offset[1])
        r = _Render(self.assets, surface, self.full, [], self.state, hover)
        top = y
        for i, widget in enumerate(self.widgets):
            renderer = RENDERERS.get(widget.kind)
            if renderer is None:
                continue
            height = renderer(r, widget, x, y, self.width)
            if height:
                y += height + (GAP + 6 if self.full else GAP)
        if surface is not None:
            self.hits = r.hits
        return max(0, y - top - (GAP if self.widgets else 0))

    def measure(self) -> int:
        return self._run(None, 0, 0)

    def draw(self, surface: pygame.Surface, pos: tuple[int, int], *, offset: tuple[int, int] = (0, 0),
             clip: pygame.Rect | None = None) -> int:
        """Draw at `pos` on `surface`. When `surface` is an off-screen canvas placed at
        `offset` on screen (clipped to `clip`), hit areas are moved to screen coordinates."""
        self.origin = pos
        height = self._run(surface, *pos, offset=offset)
        if offset != (0, 0) or clip is not None:
            for h in self.hits:
                h.rect.move_ip(offset)
                if clip is not None:
                    h.rect = h.rect.clip(clip)
        return height

    def hit(self, pos: tuple[int, int]) -> Hit | None:
        # Later (more specific) hits win over earlier fallback areas.
        return next((h for h in reversed(self.hits) if h.rect.collidepoint(pos)), None)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hover = event.pos
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            h = self.hit(event.pos)
            if h is not None and h.act is not None and h.act.enabled:
                if h.act.id == "gui:log_filter":
                    self.state["log_filter"] = h.act.arg
                elif self.on_act is not None:
                    self.on_act(h.act)
                return True
        return False

    def draw_overlay(self, surface: pygame.Surface) -> None:
        h = self.hit(self.hover)
        if h is not None and h.tooltip:
            draw_tooltip(surface, self.assets, h.tooltip, (self.hover[0] + 16, self.hover[1] + 12))
