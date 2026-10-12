"""An in-memory meta service with demo players, for GUI work and tests.

    from chaos_blackjack.meta.fake import install_fake
    install_fake()            # every chaos_blackjack.meta call now uses a throwaway database

It is the real MetaService on an in-memory SQLite database, so behaviour is
identical to data/game.db; nothing is written to disk.
"""

from __future__ import annotations

import json

from chaos_blackjack import meta
from chaos_blackjack.data.db import MEMORY, connect
from chaos_blackjack.meta.service import MetaService


def install_fake(*, demo: bool = True) -> MetaService:
    svc = MetaService(connect(MEMORY))
    if demo:
        seed_demo(svc)
    meta.use_service(svc)
    return svc


def seed_demo(svc: MetaService) -> None:
    """Slot 1: a veteran with tokens, upgrades, history, cosmetics and achievements.
    Slot 2: a new player. Slot 3: empty."""
    ace = svc.create_player(1, "Ace")
    svc.grant_tokens(ace.id, 200)
    for upgrade in ("start_money", "start_money", "bag_space", "start_peek", "start_peek", "start_shield"):
        svc.buy_upgrade(ace.id, upgrade)
    svc.grant_tokens(ace.id, 60 - svc.get_player(ace.id).tokens)
    svc.create_player(2, "Rookie")
    with svc._db() as db, db:  # noqa: SLF001 - demo history without playing runs
        for mode, result, rounds, final, peak, tokens in (
            ("normal", "defeat", 18, 1, 160, 3),
            ("chaos", "victory", 31, 412, 412, 10),
            ("chaos", "defeat", 9, 1, 120, 2),
        ):
            summary = {"rules_seen": {"great_crash": 2} if mode == "chaos" else {}, "items_used": {"peek": 1},
                       "items_bought": {"swap": 1}, "rounds": rounds, "peak_money": peak, "blackjacks": 1,
                       "doubles": 2, "surrenders": 0, "chaos_ai": "default" if mode == "chaos" else None}
            db.execute(
                "INSERT INTO run_history (player_id, ended_at, mode, balance_profile, result, rounds, final_money, "
                "peak_money, tokens_earned, upgrades, summary) VALUES (?, datetime('now'), ?, 'default', ?, ?, ?, ?, ?, "
                "?, ?)",
                (ace.id, mode, result, rounds, final, peak, tokens, json.dumps({"start_money": 2}),
                 json.dumps(summary)),
            )
    svc.achievements(ace.id)  # stats and achievements from the history above
    svc.grant_cosmetic(ace.id, "card_back_crimson")
    for cosmetic in ("card_back_crimson", "table_poker_head"):
        svc.equip(ace.id, cosmetic)
