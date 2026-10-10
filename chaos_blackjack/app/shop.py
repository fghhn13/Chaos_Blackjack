"""Item shop — stock, prices and restocking (pure helpers).

The shop is open while betting. Its stock is a few single-purchase offers
rolled from `RunConfig.shop_prices`; it restocks every
`RunConfig.shop_refresh_rounds` rounds. Rolls are seeded per round, so the
same run seed always shows the same shelves.
"""

from __future__ import annotations

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

    def offer(self, item_id: str) -> ShopOffer | None:
        return next((o for o in self.offers if o.item == item_id and not o.sold), None)

    def with_sold(self, item_id: str) -> "ShopState":
        offers = tuple(replace(o, sold=True) if o.item == item_id else o for o in self.offers)
        return replace(self, offers=offers)

    def to_dict(self) -> dict[str, Any]:
        return {"stock_round": self.stock_round, "offers": [o.to_dict() for o in self.offers]}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ShopState":
        return ShopState(
            stock_round=int(d.get("stock_round", 1)),
            offers=tuple(ShopOffer.from_dict(o) for o in d.get("offers", [])),
        )


def roll_stock(shop_seed: int, round_no: int, prices: Mapping[str, int], slots: int) -> ShopState:
    """Pick `slots` different items (sorted by price) for this round's shelves."""
    rng = random.Random(f"{shop_seed}:shop:{round_no}")
    pool = sorted(prices)
    picked = rng.sample(pool, min(slots, len(pool)))
    offers = sorted((ShopOffer(i, int(prices[i])) for i in picked), key=lambda o: (o.price, o.item))
    return ShopState(stock_round=round_no, offers=tuple(offers))


def rounds_until_restock(shop: ShopState, round_no: int, every: int) -> int:
    return max(1, every - (round_no - shop.stock_round))


def needs_restock(shop: ShopState, round_no: int, every: int) -> bool:
    return round_no - shop.stock_round >= every
