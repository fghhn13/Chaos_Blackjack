"""Playback of precomputed DemoFrames. No live controller is kept by the GUI."""

from dataclasses import replace

import pygame

from chaos_blackjack.gui import theme
from chaos_blackjack.gui.components.cards import CardRenderer, layout_hand
from chaos_blackjack.gui.components.codex_text import draw_text
from chaos_blackjack.gui.components.table_fx import TableFx
from chaos_blackjack.gui.texts import notice_line, outcome_banner

FRAME_SECONDS = 1.8
DEMO_CARD_SIZE = (70, 105)


class CodexDemo:
    def __init__(self, assets, frames):
        self.assets = assets
        self.frames = tuple(frames)
        self.cards = CardRenderer(assets)
        self.index = 0
        self.elapsed = 0.0
        self.playing = bool(self.frames)
        self.fx = None
        self.message = ""
        if self.frames:
            self._show(0)

    @property
    def frame(self):
        return self.frames[self.index] if self.frames else None

    def _show(self, index, *, animate=True):
        previous = self.frame.view
        self.index = index
        current = self.frame.view
        if self.fx is None or not animate:
            previous = replace(current, player_cards=(), dealer_cards=()) if animate else current
            self.fx = TableFx(previous, bankroll_anchor=(80, 20), dealer_anchor=(380, 110))
        self.fx.view_changed(previous, current)
        if animate:
            for notice in self.frame.notices:
                self.fx.react(notice)
        self.message = "\n".join(line[0] for n in self.frame.notices if (line := notice_line(n)))
        self.elapsed = 0.0

    def replay(self):
        if self.frames:
            self.fx = None
            self._show(0)
            self.playing = True

    def toggle(self):
        if self.frames:
            if self.index == len(self.frames) - 1 and not self.playing:
                self.replay()
            else:
                self.playing = not self.playing

    def step(self, delta):
        if self.frames:
            self.playing = False
            self._show(max(0, min(len(self.frames) - 1, self.index + delta)), animate=False)

    def update(self, dt):
        if not self.frames or not self.playing:
            return
        self.fx.update(dt)
        self.elapsed += max(0, dt)
        if self.elapsed >= FRAME_SECONDS and not self.fx.busy:
            if self.index < len(self.frames) - 1:
                self._show(self.index + 1)
            else:
                self.playing = False

    def draw(self, surface, rect):
        if not self.frame:
            return
        rect = pygame.Rect(rect)
        board = pygame.Surface(rect.size)
        board.fill(theme.FELT)
        width, height = rect.size
        view = self.frame.view
        font = self.assets.font(theme.FONT_SMALL)
        text = f"Bankroll {self.fx.money_shown()}    Bet {view.current_bet}    Deck {view.deck_count}"
        draw_text(board, text, font, (20, 16, width - 40, 28), theme.GOLD)
        deck = pygame.Rect(width - 82, 76, 54, 81)
        board.blit(self.cards.back(deck.size), deck)
        for who, cards, total, y in (
            ("dealer", view.dealer_cards, view.dealer_total, 140),
            ("player", view.player_cards, view.player_total, 330),
        ):
            label = "Dealer" if who == "dealer" else "You"
            draw_text(board, f"{label}  {total if total is not None else '?'}", font,
                      (20, y - 82, width - 110, 24), theme.TEXT)
            for index, (card, at) in enumerate(zip(cards, layout_hand(
                len(cards), (width // 2 - 16, y), DEMO_CARD_SIZE, max_width=width - 180,
            ))):
                self.fx.draw_card(board, self.cards, card, (who, index), at, deck)
        rule_names = ", ".join(r.id.replace("_", " ").title() for r in view.active_rules)
        draw_text(board, f"Active rules: {rule_names or 'none'}", font,
                  (20, 216, width - 40, 44), theme.CHAOS_MAGENTA)
        draw_text(board, self.frame.caption, font, (20, 398, width - 40, 60))
        message = self.message
        color = theme.GOLD
        if view.last_result:
            head, detail, color = outcome_banner(view.last_result)
            message = f"{head}: {detail}"
        draw_text(board, message, font, (20, height - 48, width - 40, 44), color)
        self.fx.apply_glitch(board)
        surface.blit(board, rect)
