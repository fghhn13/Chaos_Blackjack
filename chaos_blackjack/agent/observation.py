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

OBS_SCHEMA = 3

# Plain-English help so an LLM does not have to guess what ids mean.
ACTION_HELP: dict[str, str] = {
    Action.BET: "start the round: bet <amount>",
    Action.BUY: "buy a shop offer before betting: buy <item_id> (see obs.shop; some ask obs.choice next)",
    Action.REROLL: "roll the shop's stock again (obs.shop.reroll_price chips)",
    Action.HIT: "take one more card",
    Action.STAND: "end your turn; the dealer plays",
    Action.DOUBLE: "double the bet, take exactly one card, then stand",
    Action.SURRENDER: "give up the hand and get part of the bet back",
    Action.USE_ITEM: "use an item whose usable is true: act use_item <item_id> [--target <id>]",
    Action.CHOOSE: "answer the pending question: choose <option id> (see obs.choice)",
    Action.CANCEL: "drop the pending question; nothing is charged or spent",
    "perform": "run one of obs.table_actions: perform <action> [arg]",
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
    """Command names of the enabled moves (GameController.moves), in a stable order."""
    if v.phase == TablePhase.RUN_OVER:
        return []
    enabled = [m for m in v.moves if m.enabled]
    names = {m.action for m in enabled if not m.table}
    order = (Action.CHOOSE, Action.CANCEL, Action.BET, Action.BUY, Action.REROLL, Action.HIT, Action.STAND,
             Action.DOUBLE, Action.SURRENDER, Action.USE_ITEM)
    acts = [a for a in order if a in names]
    if any(m.table for m in enabled):
        acts.append("perform")
    return acts


def next_step_hint(v: GameView, acts: list[str]) -> str:
    if v.phase == TablePhase.RUN_OVER:
        return "The run is over. Start a new one with `new`."
    if v.choice is not None:
        cancel = " or cancel" if Action.CANCEL in acts else ""
        return f"Answer the question: choose <option>{cancel} (see obs.choice)."
    if v.phase == TablePhase.BETTING:
        bet = f"Place a bet: bet <amount> with {v.bet_min} <= amount <= {v.bet_max}."
        extra = []
        if Action.BUY in acts:
            extra.append("buy <item_id>")
        if Action.REROLL in acts:
            extra.append("reroll")
        if Action.USE_ITEM in acts:
            extra.append("act use_item <item_id>")
        if "perform" in acts:
            extra.append("perform <action>")
        if extra:
            return bet + f" Or first: {' / '.join(extra)} (see obs.shop, obs.items)."
        return bet
    parts = [a if a != Action.USE_ITEM else "use_item <item_id>" for a in acts if a != "perform"]
    hint = "Your move: act " + " | ".join(parts)
    return hint + (" (or perform <action>, see obs.table_actions)" if "perform" in acts else "")


def summary(v: GameView) -> str:
    """One readable paragraph describing the table."""
    bankroll = f"{v.money}/{v.target_money}" if v.target_money > 0 else str(v.money)
    lines = [f"Round {v.round}. Bankroll {bankroll}."]
    if v.table_info:
        lines.append(" ".join(f"{label}: {value}." for label, value in v.table_info))
    if v.player_cards:
        total = "?" if v.player_total is None else v.player_total
        lines.append(f"Bet {v.current_bet}. You: {' '.join(card_str(c) for c in v.player_cards)} = {total}.")
        dealer = " ".join(card_str(c) for c in v.dealer_cards)
        total = "?" if v.dealer_total is None else str(v.dealer_total)
        lines.append(f"Dealer: {dealer} = {total}.")
    if v.active_rules:
        # A table's own rules (they say what they do) are in force for a while; Chaos AI modifiers for this round.
        label = "Rules in force" if any(r.effect for r in v.active_rules) else "Active chaos rules"
        lines.append(f"{label}: " + "; ".join(r.description for r in v.active_rules))
    if v.items:
        lines.append("Items: " + ", ".join(f"{i.id} x{i.count}" for i in v.items) + ".")
    if v.phase == TablePhase.BETTING and v.shop_offers:  # a table that sells nothing has no shop line
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
        "items": [{"id": i.id, "name": i.name or i.id, "count": i.count,
                   "help": i.description or ITEM_HELP.get(i.id, ""), "when": i.when,
                   "usable": i.usable, **({"reason": i.reason} if not i.usable and i.reason else {}),
                   **({"note": i.note} if i.note else {})}
                  for i in v.items],
        "choice": {
            "kind": v.choice.kind,
            "prompt": v.choice.prompt,
            "options": [{"id": o.id, "label": o.label, "help": o.description} for o in v.choice.options],
            "cancellable": v.choice.cancellable,
        } if v.choice is not None else None,
        "table_actions": [{"action": m.action, "arg": m.arg, "label": m.label, "enabled": m.enabled,
                           **({"reason": m.reason} if m.reason else {})} for m in v.moves if m.table],
        "shop": {
            "offers": [
                {"item": o.item, "price": o.price, "sold": o.sold, "affordable": o.affordable,
                 "help": o.description or ITEM_HELP.get(o.item, ""),
                 **({"name": o.name, "kind": o.kind, "when": o.when} if o.kind else {}),
                 **({"reason": o.reason} if not o.affordable and o.reason else {}),
                 **({"base_price": o.base_price, "price_note": o.price_note} if o.base_price is not None else {})}
                for o in v.shop_offers
            ],
            "restock_in": v.shop_restock_in,
            "reroll_price": v.shop_reroll_price,
            "reroll_affordable": v.can(Action.REROLL),
        } if v.phase == TablePhase.BETTING else None,
        "chaos": {
            "enabled": v.chaos_enabled,
            "budget": v.chaos_budget if v.chaos_budget_shown else None,
            "active_rules": [{"id": r.id, "help": r.description,
                              **({"name": r.name, "scope": r.scope, "effect": r.effect, "remaining": r.remaining,
                                  "removal": r.removal, "silenced": r.silenced, "tier": r.tier} if r.effect else {})}
                             for r in v.active_rules],
        },
        # A mode's own mechanics (J-54: compute, meter, Joker, deck; Poker Head: build and money); None elsewhere.
        "table": {"info": dict(v.table_info), "fee": v.fee, "deck": dict(v.deck_counts),
                  **({"public": v.table_public.to_dict()} if v.table_public is not None else {})}
                 if v.table_info else None,
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
