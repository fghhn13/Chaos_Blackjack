"""Item shop — stock, prices and restocking (pure helpers).

The shop is open while betting. Its stock is a few single-purchase offers
rolled from `RunConfig.shop_prices`; it restocks every
`RunConfig.shop_refresh_rounds` rounds and can be rerolled once per stock.
Rolls are seeded per round, so the same run seed always shows the same shelves.

Prices are fixed chips, or (`RunConfig.shop_bankroll_pct`) a percentage of
the bankroll when the stock is rolled, rounded half up and at least one chip.
Custom configurations and saved runs may retain an optional price floor.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class ShopOffer:
    item: str
    price: int
    sold: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"item": self.item, "price": self.price, "sold": self.sold}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ShopOffer":
        return ShopOffer(item=str(d["item"]), price=int(d["price"]), sold=bool(d.get("sold", False)))


@dataclass(frozen=True)
class ShopState:
    stock_round: int  # round the current stock was rolled in
    offers: tuple[ShopOffer, ...]
    rerolled: bool = False         # this stock was already rerolled
    free_rerolls_used: int = 0     # per run; carried across restocks

    def offer(self, item_id: str) -> ShopOffer | None:
        return next((o for o in self.offers if o.item == item_id and not o.sold), None)

    def with_sold(self, item_id: str) -> "ShopState":
        offers = tuple(replace(o, sold=True) if o.item == item_id else o for o in self.offers)
        return replace(self, offers=offers)

    def to_dict(self) -> dict[str, Any]:
        return {"stock_round": self.stock_round, "offers": [o.to_dict() for o in self.offers],
                "rerolled": self.rerolled, "free_rerolls_used": self.free_rerolls_used}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ShopState":
        return ShopState(
            stock_round=int(d.get("stock_round", 1)),
            offers=tuple(ShopOffer.from_dict(o) for o in d.get("offers", [])),
            rerolled=bool(d.get("rerolled", False)),
            free_rerolls_used=int(d.get("free_rerolls_used", 0)),
        )


def shop_prices(prices: Mapping[str, int], bankroll_pct: tuple[str, ...] | frozenset[str], money: int,
                floor_money: int) -> dict[str, int]:
    """Chip prices for a roll: fixed prices as they are, percentage prices
    against max(bankroll, floor_money), rounded half up and at least 1."""
    base = max(money, floor_money)
    return {item: max(1, math.floor(price * base / 100 + 0.5)) if item in bankroll_pct else int(price)
            for item, price in prices.items()}


def roll_stock(shop_seed: int, round_no: int, prices: Mapping[str, int], slots: int, *,
               reroll: bool = False) -> ShopState:
    """Pick `slots` different items (sorted by price) for this round's shelves."""
    rng = random.Random(f"{shop_seed}:shop:{round_no}" + (":reroll" if reroll else ""))
    pool = sorted(prices)
    picked = rng.sample(pool, min(slots, len(pool)))
    offers = sorted((ShopOffer(i, int(prices[i])) for i in picked), key=lambda o: (o.price, o.item))
    return ShopState(stock_round=round_no, offers=tuple(offers))


def rounds_until_restock(shop: ShopState, round_no: int, every: int) -> int:
    return max(1, every - (round_no - shop.stock_round))


def needs_restock(shop: ShopState, round_no: int, every: int) -> bool:
    return round_no - shop.stock_round >= every
