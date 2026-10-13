"""J-54's run contracts — what its shop sells instead of items.

A contract has a price (shop_item row, fixed chips), a trigger and an effect;
the numbers are the row's `params` (balance profile). Contracts are not items:
buying one never puts anything in the inventory.

Triggers: `now` (applied when bought), `win` (next won hand, natural
included), `loss` (next lost hand), `natural` (next natural blackjack).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TRIGGERS = ("now", "win", "loss", "natural")


@dataclass(frozen=True)
class Contract:
    id: str
    name: str
    effect: str          # default effect when the profile gives none
    trigger: str = "now"


CONTRACTS: dict[str, Contract] = {c.id: c for c in (
    Contract("j54_streamline", "Streamline Contract", "delete_random", "win"),
    Contract("j54_low_purge", "Low Purge Contract", "delete_low", "win"),
    Contract("j54_high_injection", "High Injection Contract", "add_high"),
    Contract("j54_freeze", "Freeze Contract", "freeze"),
    Contract("j54_start_experiment", "Start Experiment", "release_jokers"),
)}

_WHEN = {
    "now": "At once",
    "win": "When you next win a hand",
    "loss": "When you next lose a hand",
    "natural": "When you next get a natural blackjack",
}


def contract_params(contract_id: str, item_params: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Trigger, effect and numbers of a contract (profile params over defaults)."""
    c = CONTRACTS[contract_id]
    params = {"trigger": c.trigger, "effect": c.effect, **item_params.get(contract_id, {})}
    if params["trigger"] not in TRIGGERS:
        raise ValueError(f"Contract {contract_id}: unknown trigger {params['trigger']!r}")
    return params


def effect_text(params: dict[str, Any]) -> str:
    """What a contract does, without its trigger (e.g. "delete 4 random cards")."""
    effect, count = params["effect"], int(params.get("count", 1))
    plural = "s" if count != 1 else ""
    if effect == "delete_random":
        return f"delete {count} random card{plural} from the deck"
    if effect == "delete_low":
        return f"delete {count} low card{plural} (2-6) from the deck"
    if effect == "add_high":
        return f"add {count} high card{plural} (10, J, Q, K or A) to the deck"
    if effect == "freeze":
        rounds = int(params.get("rounds", 1))
        return f"stop J-54 adding cards for {rounds} round{'s' if rounds != 1 else ''}"
    if effect == "release_jokers":
        return "release the sealed Joker into the deck (J-54 then adds more cards each round)"
    raise ValueError(f"Unknown contract effect {effect!r}")


def describe(contract_id: str, item_params: dict[str, dict[str, Any]]) -> str:
    params = contract_params(contract_id, item_params)
    text = effect_text(params)
    return f"{_WHEN[params['trigger']]}: {text}."
