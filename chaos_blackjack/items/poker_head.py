"""Register Poker Head consumables; execution belongs to its table."""

from chaos_blackjack.contracts.items import ItemResult
from chaos_blackjack.poker_head.catalog import PRODUCTS
from chaos_blackjack.registry import register_item


def _use(self, ctx):
    return ItemResult(ok=False, message="This item requires Poker Head's build table.")


for _p in PRODUCTS.values():
    if _p.kind == "item":
        register_item(_p.id, type(_p.id, (), {"name": _p.id, "codex_name": _p.name,
            "description": _p.description, "mode": "chaos", "codex_kind": "build", "use": _use}))
