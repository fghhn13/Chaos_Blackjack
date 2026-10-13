"""GameView -> JSON observation for agent players.

Fair-play rule: only information a human at the table could see is included
(no dealer hole card, no deck order). Bump OBS_SCHEMA when the shape changes.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from chaos_blackjack.app.help_text import ITEM_HELP
from chaos_blackjack.app.notices import Notice, NoticeKind
from chaos_blackjack.app.view import Action, CardView, GameView, RoundResult, TablePhase

OBS_SCHEMA = 2

# Plain-English help so an LLM does not have to guess what ids mean.
ACTION_HELP: dict[str, str] = {
    Action.BET: "start the round: bet <amount>",
    Action.BUY: "buy a shop offer (an item, or a contract at J-54's table) before betting: buy <item_id>",
    Action.REROLL: "roll the shop's stock again (once per stock; obs.shop.reroll_price chips)",
    Action.HIT: "take one more card",
    Action.STAND: "end your turn; the dealer plays",
    Action.DOUBLE: "double the bet, take exactly one card, then stand (first decision only)",
    Action.SURRENDER: "give up the hand and get half the bet back (first decision only)",
    Action.USE_ITEM: "use an item: act use_item <item_id>",
}

_SKIP_EVENTS = {NoticeKind.PHASE_CHANGED, NoticeKind.ROUND_SETTLED, NoticeKind.ITEM_USED}


def card_str(c: CardView) -> str:
    return f"{c.rank}{c.suit}" if c.face_up else "??"


def round_result_dict(r: RoundResult) -> dict[str, Any]:
    return asdict(r)


def event_texts(notices: list[Notice]) -> list[str]:
    out: list[str] = []
    for n in notices:
        if n.kind in _SKIP_EVENTS:
            continue
        if n.kind == NoticeKind.ROUND_STARTED:
            out.append(f"Round {n.data.get('round')} started, bet {n.data.get('bet')}")
        elif n.kind == NoticeKind.CHAOS_NARRATION:
            out.append(f"Chaos AI says: {n.data.get('text')}")
        elif n.text:
            out.append(n.text)
    return out


def legal_actions(v: GameView) -> list[str]:
    if v.phase == TablePhase.BETTING:
        acts = [Action.BET]
        if any(o.affordable for o in v.shop_offers):
            acts.append(Action.BUY)
        if v.can(Action.REROLL):
            acts.append(Action.REROLL)
        return acts
    if v.phase != TablePhase.PLAYER_TURN:
        return []
    acts = [a for a in (Action.HIT, Action.STAND, Action.DOUBLE, Action.SURRENDER) if v.can(a)]
    if v.can(Action.USE_ITEM) and v.items:
        acts.append(Action.USE_ITEM)
    return acts


def next_step_hint(v: GameView, acts: list[str]) -> str:
    if v.phase == TablePhase.RUN_OVER:
        return "The run is over. Start a new one with `new`."
    if v.phase == TablePhase.BETTING:
        bet = f"Place a bet: bet <amount> with {v.bet_min} <= amount <= {v.bet_max}."
        extra = []
        if Action.BUY in acts:
            extra.append("buy <item_id>")
        if Action.REROLL in acts:
            extra.append("reroll")
        if extra:
            return bet + f" Or first: {' / '.join(extra)} (see obs.shop)."
        return bet
    parts = [a if a != Action.USE_ITEM else "use_item <item_id>" for a in acts]
    return "Your move: act " + " | ".join(parts)


def summary(v: GameView) -> str:
    """One readable paragraph describing the table."""
    bankroll = f"{v.money}/{v.target_money}" if v.target_money > 0 else str(v.money)
    lines = [f"Round {v.round}. Bankroll {bankroll}."]
    if v.table_info:
        lines.append(" ".join(f"{label}: {value}." for label, value in v.table_info))
    if v.player_cards:
        lines.append(f"Bet {v.current_bet}. You: {' '.join(card_str(c) for c in v.player_cards)} = {v.player_total}.")
        dealer = " ".join(card_str(c) for c in v.dealer_cards)
        total = "?" if v.dealer_total is None else str(v.dealer_total)
        lines.append(f"Dealer: {dealer} = {total}.")
    if v.active_rules:
        lines.append("Active chaos rules: " + "; ".join(r.description for r in v.active_rules))
    if v.items:
        lines.append("Items: " + ", ".join(f"{i.id} x{i.count}" for i in v.items) + ".")
    if v.phase == TablePhase.BETTING:
        on_sale = [f"{o.item} {o.price}" for o in v.shop_offers if not o.sold]
        stock = ", ".join(on_sale) if on_sale else "sold out"
        reroll = ""
        if v.shop_reroll_price is not None:
            reroll = "; reroll free" if v.shop_reroll_price == 0 else f"; reroll {v.shop_reroll_price}"
        lines.append(f"Shop: {stock} (restocks in {v.shop_restock_in} round{'s' if v.shop_restock_in != 1 else ''}{reroll}).")
    return " ".join(lines)


def build_observation(v: GameView, *, last_round: dict[str, Any] | None = None) -> dict[str, Any]:
    acts = legal_actions(v)
    in_hand = v.phase == TablePhase.PLAYER_TURN or (v.player_cards and v.phase != TablePhase.BETTING)
    obs: dict[str, Any] = {
        "schema": OBS_SCHEMA,
        "phase": v.phase.value,
        "legal_actions": acts,
        "hint": next_step_hint(v, acts),
        "summary": summary(v),
        "round": v.round,
        "bankroll": v.money,
        "target": v.target_money,
        "bet_range": [v.bet_min, v.bet_max] if v.phase == TablePhase.BETTING else None,
        "bet": v.current_bet if in_hand else None,
        "win_streak": v.win_streak,
        "you": {"cards": [card_str(c) for c in v.player_cards], "total": v.player_total} if in_hand else None,
        "dealer": {"cards": [card_str(c) for c in v.dealer_cards], "total": v.dealer_total} if in_hand else None,
        "items": [{"id": i.id, "count": i.count, "help": i.description or ITEM_HELP.get(i.id, "")} for i in v.items],
        "shop": {
            "offers": [
                {"item": o.item, "price": o.price, "sold": o.sold, "affordable": o.affordable,
                 "help": o.description or ITEM_HELP.get(o.item, "")}
                for o in v.shop_offers
            ],
            "restock_in": v.shop_restock_in,
            "reroll_price": v.shop_reroll_price,
            "reroll_affordable": v.can(Action.REROLL),
        } if v.phase == TablePhase.BETTING else None,
        "chaos": {
            "enabled": v.chaos_enabled,
            "budget": v.chaos_budget,
            "active_rules": [{"id": r.id, "help": r.description} for r in v.active_rules],
        },
        # A mode's own mechanics (J-54: protocol, Joker, deck size, fee, contracts); None elsewhere.
        "table": {"info": dict(v.table_info), "fee": v.fee, "deck": dict(v.deck_counts)} if v.table_info else None,
        "action_help": {a: ACTION_HELP[a] for a in acts if a in ACTION_HELP},
        "last_round": last_round,
        "run_end": {"kind": v.run_end.kind, "message": v.run_end.message} if v.run_end else None,
    }
    return obs


__all__ = [
    "ACTION_HELP",
    "ITEM_HELP",
    "OBS_SCHEMA",
    "build_observation",
    "event_texts",
    "legal_actions",
    "round_result_dict",
]
