"""Explicit installation of a trusted pack's shop rows into an editable profile."""

from pathlib import Path
import sqlite3

from chaos_blackjack.content.loader import PACK_ROOT, load_content_packs
from chaos_blackjack.data.balance import BalanceError, load_balance
from chaos_blackjack.data.db import _statements


def install_shop(conn: sqlite3.Connection, packs: tuple[str, ...], profile: str,
                 *, root: Path = PACK_ROOT) -> None:
    catalog = load_content_packs(packs, root=root)
    row = conn.execute("SELECT id, locked FROM balance_profile WHERE name=?", (profile,)).fetchone()
    if row is None or row["locked"]:
        raise BalanceError("Choose an existing editable balance profile; clone default first.")
    with conn:
        for pack in packs:
            for statement in _statements((root / pack / "shop.sql").read_text(encoding="utf-8")):
                conn.execute(statement, {"profile": row["id"]})
        balance = load_balance(profile, conn)
        missing = set(catalog.shop_items) - balance.shop_prices.keys()
        if missing:
            raise BalanceError(f"Missing enabled shop prices: {', '.join(sorted(missing))}")
