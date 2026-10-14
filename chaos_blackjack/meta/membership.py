"""Membership levels: how much a player has spent on goods (docs/design/CARRIED_CHIPS.zh-CN.md §8).

`player.lifetime_spend` (chips spent in run shops and the meta shop; bets do
not count) sets the level. The thresholds and the two money perks come from
the balance profile (`meta.membership_spend`, `meta.membership_relief_bonus`,
`meta.membership_shop_discount_pct`); names, badges and perk text are here.
Badge art: assets/membership/member_<level>.png (scripts/draw_membership_badges.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from chaos_blackjack.data.balance import Balance

NAMES = ("Newcomer", "Regular", "Patron", "High Roller", "Guest of Honor")
RELIEF_LEVEL = 3      # from this level Poker Head's relief cap is higher
DISCOUNT_LEVEL = 4    # from this level the meta shop is cheaper


@dataclass(frozen=True)
class Membership:
    level: int                    # 1..5
    name: str
    spend: int                    # lifetime spend
    floor: int                    # spend this level starts at
    next_at: int | None           # spend the next level starts at; None at the top
    perks: tuple[str, ...]        # what this level gives, in plain English

    @property
    def badge(self) -> str:
        return f"member_{self.level}"

    @property
    def progress(self) -> float:
        """Share of the way to the next level (1.0 at the top)."""
        if self.next_at is None:
            return 1.0
        return max(0.0, min(1.0, (self.spend - self.floor) / max(1, self.next_at - self.floor)))


def thresholds(balance: Balance) -> tuple[int, ...]:
    return tuple(int(x) for x in str(balance.meta_membership_spend).split(","))


def perks(balance: Balance, level: int) -> tuple[str, ...]:
    out = []
    if level >= 2:
        out.append(f"The {NAMES[min(level, len(NAMES)) - 1]} title and badge")
    if level >= RELIEF_LEVEL:
        out.append(f"Poker Head's relief goes up to {balance.meta_relief_cap + balance.meta_membership_relief_bonus}")
    if level >= DISCOUNT_LEVEL:
        out.append(f"{balance.meta_membership_shop_discount_pct}% off in the Shop")
    return tuple(out)


def membership(balance: Balance, spend: int) -> Membership:
    steps = thresholds(balance)
    level = max(i + 1 for i, floor in enumerate(steps) if spend >= floor)
    next_at = steps[level] if level < len(steps) else None
    return Membership(level, NAMES[level - 1], spend, steps[level - 1], next_at, perks(balance, level))


def relief_cap(balance: Balance, spend: int) -> int:
    bonus = balance.meta_membership_relief_bonus if membership(balance, spend).level >= RELIEF_LEVEL else 0
    return balance.meta_relief_cap + bonus


def shop_price(balance: Balance, spend: int, price: int) -> int:
    """A meta shop price after the membership discount (rounded up)."""
    if membership(balance, spend).level < DISCOUNT_LEVEL:
        return price
    return math.ceil(price * (100 - balance.meta_membership_shop_discount_pct) / 100)
