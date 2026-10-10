"""Table animations: dealing, flips, chips, bankroll roll-up, banner, glitch.

TableFx watches view changes and notices and keeps tweens; the table scene
asks it where and how to draw things. Only card movement is *blocking*
(the dealer and the Chaos AI wait for cards to land); everything else runs
alongside play. Player input is never blocked.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import CardView, GameView, RoundResult, TablePhase
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.anim import Animator, Tween, in_out_cubic, lerp, lerp_point, linear, out_back, out_cubic

DEAL_TIME = 0.42   # one card: fly + flip
DEAL_GAP = 0.14    # stagger between cards dealt together
FLY_SHARE = 0.7    # part of DEAL_TIME spent flying; the rest flips face up
FLIP_TIME = 0.3    # revealing the hole card
CHIP_DROP = 0.35
SETTLE_TIME = 0.55
BANNER_TIME = 0.35
MONEY_TIME = 0.8
GLITCH_TIME = 0.55

HANDS = ("player", "dealer")  # deal order within each round of dealing


@dataclass
class CardFx:
    kind: str  # "deal" | "flip"
    tween: Tween
    flip_at: float | None = None
    flip_played: bool = False


@dataclass
class SettleFx:
    tween: Tween
    result: RoundResult


class TableFx:
    def __init__(self, view: GameView, *, bankroll_anchor: tuple[int, int], dealer_anchor: tuple[int, int],
                 audio=None) -> None:
        self.audio = audio
        self._sound_epoch = 0
        self.anim = Animator()
        self.cards: dict[tuple[str, int], CardFx] = {}
        self.chip_drop: Tween | None = None
        self.settle: SettleFx | None = None
        self.banner: Tween | None = None
        self.glitch: Tween | None = None
        self.bankroll_anchor = bankroll_anchor
        self.dealer_anchor = dealer_anchor
        self._money_from = self._money_to = float(view.money)
        self._money: Tween | None = None

    # ------------------------------------------------------------ driving

    @property
    def busy(self) -> bool:
        return self.anim.busy

    def update(self, dt: float) -> None:
        self.anim.update(dt)
        for fx in self.cards.values():
            if fx.flip_at is not None and fx.tween.raw >= fx.flip_at and not fx.flip_played:
                fx.flip_played = True
                self._sound("card_flip")
        for key in [k for k, fx in self.cards.items() if fx.tween.done]:
            del self.cards[key]

    def _sound(self, sound_id: str) -> None:
        if self.audio is not None:
            self.audio.play(sound_id)

    def _sound_callback(self, sound_id: str):
        """Discard old-round sound callbacks without changing any Tween timing."""
        epoch = self._sound_epoch
        def play() -> None:
            if epoch == self._sound_epoch:
                self._sound(sound_id)
        return play

    def view_changed(self, prev: GameView, new: GameView) -> None:
        if new.phase == TablePhase.BETTING and prev.phase != TablePhase.BETTING:
            self._sound_epoch += 1
            self.cards.clear()
            self.settle = self.banner = None
        self._diff_cards(prev, new)
        if new.money != self._money_to:
            self._money_from = float(self.money_shown())
            self._money_to = float(new.money)
            delay = self.settle.tween.delay + SETTLE_TIME * 0.6 if self.settle and not self.settle.tween.done else 0.0
            self._money = self.anim.add(Tween(MONEY_TIME, ease=out_cubic, delay=delay, blocking=False))

    def react(self, n: Notice) -> None:
        if n.kind == NoticeKind.ROUND_STARTED:
            self.chip_drop = self.anim.add(Tween(CHIP_DROP, ease=out_back, blocking=False,
                                                  on_done=self._sound_callback("chip_stack")))
        elif n.kind == NoticeKind.ROUND_SETTLED and isinstance(n.data.get("result"), RoundResult):
            # Let the last card land before the chips move and the banner appears.
            wait = max((fx.tween.delay + fx.tween.duration - fx.tween.elapsed for fx in self.cards.values()),
                       default=0.0) + 0.1
            result = n.data["result"]
            chips = "chips_win" if result.delta > 0 else "chips_lose" if result.delta < 0 else None
            tween = self.anim.add(Tween(SETTLE_TIME, ease=in_out_cubic, delay=wait, blocking=False,
                                        on_start=self._sound_callback(chips) if chips else None))
            self.settle = SettleFx(tween, result)
            cue = ("push" if result.outcome == "push" else "blackjack" if result.outcome == "blackjack"
                   else "bust" if result.player_bust else "round_win" if result.delta > 0 else "round_lose")
            # The banner covers the betting circle, so it waits until the chips have mostly left.
            self.banner = self.anim.add(Tween(BANNER_TIME, ease=out_back, delay=wait + SETTLE_TIME * 0.8,
                                              blocking=False, on_start=self._sound_callback(cue)))
        elif n.kind == NoticeKind.RULE_MODIFIER_APPLIED:
            self.glitch = self.anim.add(Tween(GLITCH_TIME, ease=linear, blocking=False,
                                              on_start=self._sound_callback("chaos_glitch")))
        elif n.kind == NoticeKind.ITEM_USED:
            self._sound("item_use")

    def _diff_cards(self, prev: GameView, new: GameView) -> None:
        hands = {"player": (prev.player_cards, new.player_cards), "dealer": (prev.dealer_cards, new.dealer_cards)}
        new_round = new.round != prev.round
        dealt: list[tuple[str, int]] = []
        for name, (old, cur) in hands.items():
            if new_round or len(cur) < len(old):
                for key in [k for k in self.cards if k[0] == name]:
                    del self.cards[key]
                old = ()
            for i, card in enumerate(cur):
                if i >= len(old):
                    dealt.append((name, i))
                elif not old[i].face_up and card.face_up:
                    self.cards[(name, i)] = CardFx("flip", self.anim.add(Tween(FLIP_TIME, ease=linear)), flip_at=0.5)
        # Deal in table order: player, dealer, player, dealer ...
        dealt.sort(key=lambda k: (k[1], HANDS.index(k[0])))
        for n, key in enumerate(dealt):
            card = hands[key[0]][1][key[1]]
            self.cards[key] = CardFx(
                "deal", self.anim.add(Tween(DEAL_TIME, ease=linear, delay=n * DEAL_GAP,
                                            on_start=self._sound_callback("card_deal"))),
                flip_at=FLY_SHARE + (1 - FLY_SHARE) * 0.5 if card.face_up else None,
            )

    # ------------------------------------------------------------ queries

    def hand_moving(self, hand: str) -> bool:
        """True while a card of `hand` ("player" / "dealer") is still flying or flipping."""
        return any(k[0] == hand and not fx.tween.done for k, fx in self.cards.items())

    def money_shown(self) -> int:
        if self._money is None or self._money.done:
            return int(self._money_to)
        return round(lerp(self._money_from, self._money_to, self._money.value))

    def chip_drop_offset(self) -> int:
        """Vertical offset of the wager stack while it lands in the circle."""
        if self.chip_drop is None or self.chip_drop.done:
            return 0
        return round(-36 * (1 - self.chip_drop.value))

    def banner_progress(self) -> float:
        if self.banner is None:
            return 1.0
        if not self.banner.started:
            return 0.0
        return self.banner.value

    def settle_position(self, start: tuple[int, int]) -> tuple[tuple[int, int], int, float] | None:
        """(centre, amount, alpha 0..1) for the wager after the round, or None when gone."""
        if self.settle is None:
            return start, 0, 1.0
        r = self.settle.result
        if r.outcome == "push":
            return start, r.bet, 1.0
        winner = r.delta > 0
        amount = r.bet + max(r.delta, 0)
        target = self.bankroll_anchor if winner else self.dealer_anchor
        t = self.settle.tween
        if t.done:
            return None
        p = t.value
        x, y = lerp_point(start, target, p)
        return (round(x), round(y)), amount, 1.0 - 0.7 * p

    # ------------------------------------------------------------ drawing

    def draw_card(self, surface: pygame.Surface, renderer, card: CardView, key: tuple[str, int],
                  rect: pygame.Rect, deck: pygame.Rect) -> None:
        fx = self.cards.get(key)
        if fx is None or fx.tween.done:
            _draw_card_at(surface, renderer.render(card, rect.size), rect, shadow=True)
            return
        t = fx.tween
        if fx.kind == "flip":
            self._draw_flip(surface, renderer, card, rect, t.raw)
            return
        if not t.started:
            return  # still in the shoe
        p = t.raw
        fly = out_cubic(min(1.0, p / FLY_SHARE))
        x, y = lerp_point(deck.topleft, rect.topleft, fly)
        at = pygame.Rect(round(x), round(y), rect.w, rect.h)
        if p < FLY_SHARE or not card.face_up:
            _draw_card_at(surface, renderer.back(rect.size), at, shadow=p >= FLY_SHARE)
        else:
            self._draw_flip(surface, renderer, card, at, (p - FLY_SHARE) / (1 - FLY_SHARE))

    @staticmethod
    def _draw_flip(surface: pygame.Surface, renderer, card: CardView, rect: pygame.Rect, f: float) -> None:
        """Squash horizontally to the edge showing the back, then open on the face."""
        img = renderer.back(rect.size) if f < 0.5 else renderer.render(card, rect.size)
        w = max(1, round(rect.w * abs(1 - 2 * f)))
        squashed = pygame.transform.smoothscale(img, (w, rect.h))
        _draw_card_at(surface, squashed, squashed.get_rect(midtop=rect.midtop), shadow=True)

    def apply_glitch(self, surface: pygame.Surface) -> None:
        """Brief horizontal tearing and tinted bars when a chaos rule lands."""
        t = self.glitch
        if t is None or t.done:
            return
        strength = 1.0 - t.raw
        w, h = surface.get_size()
        rng = random.Random(int(t.elapsed * 24))  # new tear pattern ~24 times a second
        for _ in range(7):
            band_h = rng.randint(3, 26)
            y = rng.randrange(0, h - band_h)
            dx = round(rng.choice((-1, 1)) * rng.randint(4, 22) * strength)
            strip = surface.subsurface((0, y, w, band_h)).copy()
            surface.blit(strip, (dx, y))
        for color in (theme.CHAOS_MAGENTA, theme.CHAOS_PURPLE):
            bar = pygame.Surface((w, rng.randint(2, 8)), pygame.SRCALPHA)
            bar.fill((*color, round(90 * strength)))
            surface.blit(bar, (0, rng.randrange(0, h - 8)))


def _draw_card_at(surface: pygame.Surface, img: pygame.Surface, rect: pygame.Rect, *, shadow: bool) -> None:
    if shadow:
        sh = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 90), sh.get_rect(), border_radius=8)
        surface.blit(sh, rect.move(3, 4))
    surface.blit(img, rect)


__all__ = ["TableFx"]
