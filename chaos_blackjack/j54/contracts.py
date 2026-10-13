"""J-54's run contracts — what its shop sells instead of items.

A contract has a price (shop_item row, fixed chips), a trigger and either a
deck operation (j54/deck_ops.py: `select`, `op`, `count`) or one of the
table's special effects (`effect`: `freeze`, `release_jokers`). The numbers
are the row's `params` in the balance profile; the defaults below are used
when a profile has none. Contracts are not items: buying one never puts
anything in the inventory.

Triggers: `now` (applied when bought), `win` (next won hand, natural
included), `loss` (next lost hand), `natural` (next natural blackjack).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chaos_blackjack.j54.deck_ops import DeckOp

TRIGGERS = ("now", "win", "loss", "natural")
EFFECTS = ("freeze", "release_jokers")


@dataclass(frozen=True)
class Contract:
    id: str
    name: str
    default: dict[str, Any] = field(default_factory=dict)


CONTRACTS: dict[str, Contract] = {c.id: c for c in (
    Contract("j54_streamline", "Streamline Contract", {"trigger": "win", "select": "any", "op": "remove", "count": 5}),
    Contract("j54_low_purge", "Low Purge Contract", {"trigger": "now", "select": "low", "op": "remove", "count": 6}),
    Contract("j54_high_injection", "High Injection Contract",
             {"trigger": "now", "select": "high", "op": "add", "count": 3}),
    Contract("j54_freeze", "Freeze Contract", {"trigger": "now", "effect": "freeze", "rounds": 3}),
    Contract("j54_start_experiment", "Start Experiment", {"trigger": "now", "effect": "release_jokers"}),
)}

_WHEN = {
    "now": "At once",
    "win": "When you next win a hand",
    "loss": "When you next lose a hand",
    "natural": "When you next get a natural blackjack",
}


@dataclass(frozen=True)
class ContractSpec:
    trigger: str
    op: DeckOp | None = None      # a deck operation, or
    effect: str | None = None     # a special effect
    rounds: int = 1               # freeze length


def contract_spec(contract_id: str, item_params: dict[str, dict[str, Any]]) -> ContractSpec:
    """The contract's trigger and effect (profile params over the defaults)."""
    params = {**CONTRACTS[contract_id].default, **item_params.get(contract_id, {})}
    trigger = str(params.get("trigger", "now"))
    if trigger not in TRIGGERS:
        raise ValueError(f"Contract {contract_id}: unknown trigger {trigger!r}")
    effect = params.get("effect")
    if effect is not None:
        if effect not in EFFECTS:
            raise ValueError(f"Contract {contract_id}: unknown effect {effect!r}")
        return ContractSpec(trigger, effect=str(effect), rounds=int(params.get("rounds", 1)))
    return ContractSpec(trigger, op=DeckOp.from_params(params))


def describe(contract_id: str, item_params: dict[str, dict[str, Any]]) -> str:
    spec = contract_spec(contract_id, item_params)
    if spec.effect == "freeze":
        text = f"stop J-54 adding cards for {spec.rounds} round{'s' if spec.rounds != 1 else ''}"
    elif spec.effect == "release_jokers":
        text = "release the sealed Joker into the deck (J-54 then adds more cards each round)"
    else:
        assert spec.op is not None
        text = spec.op.describe()
    return f"{_WHEN[spec.trigger]}: {text}."
