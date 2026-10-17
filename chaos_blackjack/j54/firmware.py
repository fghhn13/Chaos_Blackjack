"""J-54's firmware: the player's one build pick (docs/design/J54_V2_SPEC.md section 7).

A firmware is one rule on the **player's** cards or bust line for the whole
run, bought from the starting chips when the run opens. Value firmwares use
the value operations of J-54's conditions (rules/plugins/j54_conditions.py),
so the evaluator takes them as `player_rules`; `fw_margin` moves the bust line
(`player_bust`). The prices are `mode.j54.firmware.<id>.price`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.rules.plugins.j54_conditions import apply_value

NO_FIRMWARE = "none"


@dataclass(frozen=True)
class Firmware:
    id: str
    name: str
    text: str                                  # what it does, for the choice and the Run panel
    rules: tuple[Mapping[str, Any], ...] = ()  # value operations on the player's cards
    bust: int | None = None                    # the player busts only above this (None = 21)

    def card_value(self, card: Card, value: int) -> int:
        for rule in self.rules:
            value = apply_value(rule, card, value)
        return value

    def bust_limit(self, limit: int) -> int:
        return self.bust if self.bust is not None else limit


CATALOG: dict[str, Firmware] = {f.id: f for f in (
    Firmware("fw_mid", "Midrange Firmware", "Your 4, 5 and 6 count 10.",
             ({"op": "set", "filter": "ranks:4-6", "value": 10},)),
    Firmware("fw_fives", "Fives Firmware", "Your 5s and 6s count 10.",
             ({"op": "set", "filter": "ranks:5-6", "value": 10},)),
    Firmware("fw_low", "Low Firmware", "Your 2, 3 and 4 count 10.",
             ({"op": "set", "filter": "ranks:2-4", "value": 10},)),
    Firmware("fw_margin", "Margin Firmware", "You bust only above 22.", bust=22),
)}


def firmware(firmware_id: str | None) -> Firmware | None:
    return CATALOG.get(firmware_id or "")
