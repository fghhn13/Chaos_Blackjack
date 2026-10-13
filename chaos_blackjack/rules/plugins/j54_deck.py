"""Chaos rules of J-54's table: deck operations, not value changes
(docs/design/J54_TABLE.md, chaos_blackjack/j54/deck_ops.py).

Each rule is a name plus one deck operation. The operation comes from the
rule's fixed params in the balance profile (`chaos_rule.params`, e.g.
`{"when": "now", "select": "high", "op": "move_bottom", "count": "all"}`);
the defaults below are used when a profile has none. Adding a rule: one
entry here (id, name, default) and one `chaos_rule` row. The table applies
the operation once (j54/table.py); card values never change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from chaos_blackjack.core.game_state import Card
from chaos_blackjack.j54.deck_ops import DeckOp
from chaos_blackjack.registry import register_rule

# id -> (name, summary for the collection, default operation)
DECK_RULES: dict[str, tuple[str, str, dict[str, Any]]] = {
    "j54_burn": ("Burn Protocol", "Every card drawn this round leaves the deck.",
                 {"when": "round_end", "select": "drawn", "op": "remove", "count": "all"}),
    "j54_sample_injection": ("Sample Injection", "Copies of one rank join the deck.",
                             {"select": "random_rank", "op": "add", "count": 3}),
    "j54_redundancy_purge": ("Redundancy Purge", "Some cards of one rank leave the deck.",
                             {"select": "random_rank", "op": "remove", "count": 3}),
    "j54_ace_injection": ("Ace Injection", "An ace joins the deck.",
                          {"select": "rank:A", "op": "add", "count": 1}),
    "j54_layered_sort": ("Layered Sort", "High cards sink to the bottom of this round's deck.",
                         {"select": "high", "op": "move_bottom", "count": "all"}),
    "j54_data_backflow": ("Data Backflow", "Deleted cards are shuffled back into the deck.",
                          {"select": "removed", "op": "return", "count": 4}),
}


@dataclass(frozen=True)
class DeckRuleModifier:
    id: str
    name: str
    op: DeckOp
    rank: str | None = None    # the rank a random_rank operation drew (set by the table)
    chaos_flags: frozenset[str] = field(default_factory=frozenset)
    deck_rule: bool = True     # applied by the table, not the rule engine

    def adjust_rank_value(self, card: Card, base_value: int) -> int:
        return base_value

    def describe(self) -> str:
        text = self.op.describe(self.rank)
        return f"{self.name}: {text[0].upper()}{text[1:]}."

    def with_rank(self, rank: str | None) -> "DeckRuleModifier":
        return replace(self, rank=rank)


def _plugin(rule_id: str) -> type:
    name, summary, default = DECK_RULES[rule_id]

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> DeckRuleModifier:
        spec = {**default, **{k: v for k, v in params.items() if k in ("when", "select", "op", "count")}}
        rank = params.get("rank")
        return DeckRuleModifier(rule_id, name, DeckOp.from_params(spec), str(rank) if rank else None)

    return type(f"DeckRule_{rule_id}", (), {"id": rule_id, "codex_name": name, "codex_summary": summary,
                                            "from_params": from_params})


for _rule_id in DECK_RULES:
    register_rule(_rule_id, _plugin(_rule_id))
