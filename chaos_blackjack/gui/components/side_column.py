"""Side columns of the table, built from a layout (app/layout.py).

Each entry of a layout column becomes a block, stacked top to bottom:

* native blocks — parts that need the GUI itself: `core.host` (portrait and
  speech), `core.deck_pile` (the shoe cards are dealt from), `core.buttons`
  (Shop, Panel; kept at the bottom) and `core.feed` (the live event feed; it
  takes the space that is left);
* data blocks — any other part, drawn from its widgets (gui/components/widget_view.py).

A block that does not fit is left out and the column says "More in the panel".
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from chaos_blackjack.app.layout import split_entry
from chaos_blackjack.app.parts import PartContext, build_part
from chaos_blackjack.app.view import Action, GameView
from chaos_blackjack.app.widgets import Act
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.cards import CARD_SIZE
from chaos_blackjack.gui.components.chaos_panel import HEIGHT as HOST_HEIGHT, ChaosPanel
from chaos_blackjack.gui.components.hud import EventFeed
from chaos_blackjack.gui.components.widget_view import WidgetView
from chaos_blackjack.gui.widgets import Button, draw_panel

if TYPE_CHECKING:
    from chaos_blackjack.gui.assets import AssetManager

PAD = 14
GAP = 12
FEED_LINE = 22


class Block:
    """A slot of a side column. `height()` None = take the space that is left."""

    bottom = False

    def height(self, width: int) -> int | None:
        return 0

    def place(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def sync(self, view: GameView) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> bool:
        return False

    def draw(self, surface: pygame.Surface) -> None:
        pass

    def draw_overlay(self, surface: pygame.Surface) -> None:
        pass


class HostBlock(Block):
    def __init__(self, panel: ChaosPanel) -> None:
        self.panel = panel

    def height(self, width: int) -> int:
        return HOST_HEIGHT

    def place(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.panel.rect = pygame.Rect(rect.x - PAD, rect.y - 6, rect.w + 2 * PAD, rect.h)

    def sync(self, view: GameView) -> None:
        self.panel.sync(view)

    def update(self, dt: float) -> None:
        self.panel.update(dt)

    def handle_event(self, event: pygame.event.Event) -> bool:
        return self.panel.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        self.panel.draw(surface)


class DeckPileBlock(Block):
    """The shoe; cards fly from `pile_rect`. Clicking it opens the panel's deck tab."""

    def __init__(self, assets: "AssetManager", cards, on_act: Callable[[Act], None], *, clickable: bool) -> None:
        self.assets, self.cards, self.on_act, self.clickable = assets, cards, on_act, clickable
        self.count = 0
        self.rect = pygame.Rect(0, 0, 0, 0)

    @property
    def pile_rect(self) -> pygame.Rect:
        rect = pygame.Rect((0, 0), CARD_SIZE)
        rect.midtop = (self.rect.centerx, self.rect.y + 10)
        return rect

    def height(self, width: int) -> int:
        return CARD_SIZE[1] + 40

    def sync(self, view: GameView) -> None:
        self.count = view.deck_count

    def handle_event(self, event: pygame.event.Event) -> bool:
        if (self.clickable and event.type == pygame.MOUSEBUTTONUP and event.button == 1
                and self.pile_rect.collidepoint(event.pos)):
            self.on_act(Act("gui:panel", "deck"))
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        rect = self.pile_rect
        back = self.cards.back(CARD_SIZE)
        for i in range(3):
            surface.blit(back, rect.move(-i * 2, -i * 2))
        if self.count:
            n = self.assets.font(theme.FONT_SMALL).render(f"{self.count} cards left", True, theme.TEXT_MUTED)
            surface.blit(n, n.get_rect(midtop=(rect.centerx, rect.bottom + 8)))


class ButtonsBlock(Block):
    bottom = True

    def __init__(self, assets: "AssetManager", on_shop: Callable[[], None], on_panel: Callable[[], None]) -> None:
        self.shop = Button(assets, (0, 0, 10, 48), "Shop", on_shop, hotkey=pygame.K_b, font_size=theme.FONT_BODY)
        self.panel = Button(assets, (0, 0, 10, 48), "Panel", on_panel, hotkey=pygame.K_TAB, font_size=theme.FONT_BODY)
        self.restock_in = 0
        self.stocked = True
        self.assets = assets

    def height(self, width: int) -> int:
        return 48 + 22

    def place(self, rect: pygame.Rect) -> None:
        self.rect = rect
        half = (rect.w - 8) // 2
        self.shop.rect = pygame.Rect(rect.x, rect.bottom - 48, half, 48)
        self.panel.rect = pygame.Rect(rect.x + half + 8, rect.bottom - 48, rect.w - half - 8, 48)

    def sync(self, view: GameView) -> None:
        self.shop.enabled = view.can(Action.BUY)
        self.restock_in = view.shop_restock_in
        self.stocked = bool(view.shop_offers)  # a table that sells nothing has no stock to announce

    def handle_event(self, event: pygame.event.Event) -> bool:
        return self.shop.handle_event(event) or self.panel.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        n = self.restock_in
        if self.stocked:
            note = self.assets.font(theme.FONT_TINY).render(f"New stock in {n} round{'s' if n != 1 else ''}", True,
                                                            theme.TEXT_MUTED)
            surface.blit(note, note.get_rect(midbottom=(self.rect.centerx, self.shop.rect.y - 4)))
        self.shop.draw(surface)
        self.panel.draw(surface)


class FeedBlock(Block):
    """The live event feed (recent lines fade); its heading opens the full log."""

    def __init__(self, assets: "AssetManager", on_act: Callable[[Act], None]) -> None:
        self.assets, self.on_act = assets, on_act
        self.feed = EventFeed(assets, (0, 0), max_lines=4, align_top=True)
        self.rect = pygame.Rect(0, 0, 0, 0)

    def height(self, width: int) -> None:
        return None

    @property
    def expand_rect(self) -> pygame.Rect:
        return pygame.Rect(self.rect.right - 90, self.rect.y - 2, 90, 20)

    def place(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.feed.anchor = (rect.x, rect.y + 26)
        self.feed.max_width = rect.w
        self.feed.max_lines = max(2, (rect.h - 26) // FEED_LINE)

    def update(self, dt: float) -> None:
        self.feed.update(dt)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.expand_rect.collidepoint(event.pos):
            self.on_act(Act("gui:panel", "log"))
            return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        tiny = self.assets.font(theme.FONT_TINY, bold=True)
        surface.blit(tiny.render("TABLE LOG", True, theme.GOLD_DIM), (self.rect.x, self.rect.y))
        more = self.assets.font(theme.FONT_TINY).render("L  expand ›", True, theme.GOLD)
        surface.blit(more, more.get_rect(topright=(self.rect.right, self.rect.y)))
        pygame.draw.line(surface, theme.GOLD_DIM, (self.rect.x, self.rect.y + 18), (self.rect.right, self.rect.y + 18), 1)
        self.feed.draw(surface)


class DataBlock(Block):
    def __init__(self, assets: "AssetManager", part: str, variant: str, on_act: Callable[[Act], None]) -> None:
        self.assets, self.part, self.variant = assets, part, variant
        self.view = WidgetView(assets, (), 0, on_act=on_act)
        self.rect = pygame.Rect(0, 0, 0, 0)

    def rebuild(self, ctx: PartContext, width: int) -> None:
        self.view.widgets = build_part(self.part, ctx, self.variant)
        self.view.width = width

    def height(self, width: int) -> int:
        return self.view.measure() if self.view.widgets else 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        return self.view.handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        self.view.draw(surface, self.rect.topleft)

    def draw_overlay(self, surface: pygame.Surface) -> None:
        self.view.draw_overlay(surface)


class SideColumn:
    def __init__(self, assets: "AssetManager", rect: pygame.Rect, entries: tuple[str, ...],
                 natives: dict[str, Block], on_act: Callable[[Act], None]) -> None:
        self.assets = assets
        self.rect = pygame.Rect(rect)
        self.blocks: list[Block] = []
        self.visible: list[Block] = []
        self.hidden = 0
        for entry in entries:
            part, variant = split_entry(entry, "compact")
            self.blocks.append(natives[part] if part in natives else DataBlock(assets, part, variant, on_act))

    def block(self, kind: type) -> Block | None:
        return next((b for b in self.blocks if isinstance(b, kind)), None)

    def sync(self, view: GameView, ctx: PartContext | None) -> None:
        inner = self.rect.inflate(-2 * PAD, -2 * PAD)
        for b in self.blocks:
            b.sync(view)
            if isinstance(b, DataBlock) and ctx is not None:
                b.rebuild(ctx, inner.w)
        self._layout(inner)

    def _layout(self, inner: pygame.Rect) -> None:
        bottom = inner.bottom
        self.visible, self.hidden = [], 0
        for b in [b for b in self.blocks if b.bottom]:
            h = b.height(inner.w) or 0
            b.place(pygame.Rect(inner.x, bottom - h, inner.w, h))
            bottom -= h + GAP
            self.visible.append(b)
        y, flex = inner.y, None
        for b in [b for b in self.blocks if not b.bottom]:
            h = b.height(inner.w)
            if h is None:
                flex = b
                continue
            if h == 0:
                continue
            if y + h > bottom - (60 if flex is not None or any(x.height(inner.w) is None for x in self.blocks) else 0):
                self.hidden += 1
                continue
            b.place(pygame.Rect(inner.x, y, inner.w, h))
            self.visible.append(b)
            y += h + GAP
        if flex is not None:
            flex.place(pygame.Rect(inner.x, y, inner.w, max(40, bottom - y - (18 if self.hidden else 0))))
            self.visible.append(flex)
        self._more_y = bottom - 16

    def update(self, dt: float) -> None:
        for b in self.blocks:
            b.update(dt)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            for b in self.visible:
                b.handle_event(event)
            return False
        return any(b.handle_event(event) for b in self.visible)

    def draw(self, surface: pygame.Surface) -> None:
        draw_panel(surface, self.rect)
        for b in self.visible:
            b.draw(surface)
        if self.hidden:
            note = self.assets.font(theme.FONT_TINY).render("More in the panel (Tab)", True, theme.TEXT_MUTED)
            surface.blit(note, note.get_rect(midtop=(self.rect.centerx, self._more_y)))

    def draw_overlay(self, surface: pygame.Surface) -> None:
        for b in self.visible:
            b.draw_overlay(surface)
