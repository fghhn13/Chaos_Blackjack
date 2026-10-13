"""Notices — the controller's outward stream of "something happened".

Front-ends drain them each frame: the CLI prints `text`, the GUI maps `kind`
to animations / sounds and reads details from `data`. Kinds are plain strings
so new ones can be added without touching any front-end that ignores them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from chaos_blackjack.events.event import Event, EventType
from chaos_blackjack.ui.feedback import FeedbackLog


class NoticeKind:
    # Translated from core EventType (kind = event type name, lower-case)
    DRAW_CARD = "draw_card"
    RULE_MODIFIER_APPLIED = "rule_modifier_applied"
    CHAOS_ACTION_REJECTED = "chaos_action_rejected"
    ITEM_USED = "item_used"
    # Emitted by the controller itself
    PHASE_CHANGED = "phase_changed"
    ROUND_STARTED = "round_started"
    CHAOS_NARRATION = "chaos_narration"
    CHAOS_POKE_REPLY = "chaos_poke_reply"
    ITEM_RESULT = "item_result"
    PLAYER_BUST = "player_bust"
    PLAYER_BLACKJACK = "player_blackjack"
    DEALER_BLACKJACK = "dealer_blackjack"
    DOUBLED = "doubled"
    SURRENDERED = "surrendered"
    DEALER_STANDS = "dealer_stands"
    DEALER_BUSTS = "dealer_busts"
    ROUND_SETTLED = "round_settled"
    ITEM_BOUGHT = "item_bought"
    SHOP_RESTOCKED = "shop_restocked"
    SHOP_REROLLED = "shop_rerolled"
    CHAOS_DISPELLED = "chaos_dispelled"
    RUN_ENDED = "run_ended"
    FEE_PAID = "fee_paid"          # a table's per-round charge (J-54's compute fee)
    TABLE_EVENT = "table_event"    # a table's own mechanics (J-54: deck changes, contracts)
    CHOICE_OPENED = "choice_opened"   # a command asked a question (app/choice.py)
    CHOICE_CLOSED = "choice_closed"   # it was answered or cancelled
    GAME_SAVED = "game_saved"
    ERROR = "error"


@dataclass(frozen=True)
class Notice:
    kind: str
    text: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


class EventTranslator:
    """Core Event -> Notice, reusing FeedbackLog's wording for the text."""

    def __init__(self) -> None:
        self._log = FeedbackLog()
        self._text_handlers: dict[EventType, Any] = {}
        self._log.wire_dispatcher(self._text_handlers.__setitem__)

    def translate(self, event: Event) -> Notice:
        handler = self._text_handlers.get(event.type)
        text = ""
        if handler is not None:
            handler(event)
            text = "\n".join(self._log.drain())
        return Notice(kind=event.type.name.lower(), text=text, data=dict(event.payload))
