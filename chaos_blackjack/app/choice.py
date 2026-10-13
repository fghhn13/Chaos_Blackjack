"""Choices and moves — the questions a command may ask, and what a player can do now.

A command that needs a decision (a core, which permanent to replace, which
rule to remove) asks a `Choice` through `GameController.ask` and changes
nothing else. The controller then only accepts `choose <option>`, `cancel`
(when allowed) and `save`; `choose` hands the choice back to the table, which
completes the original command. See docs/design/ITEM_ARCHITECTURE.md §6–7.

`Move` is one thing a player could do right now, enabled or not, with an
English reason when it is not. The GUI and the agent both read moves, so
they always agree on what is legal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ChoiceOption:
    id: str
    label: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "description": self.description}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ChoiceOption":
        return ChoiceOption(str(d["id"]), str(d["label"]), str(d.get("description", "")))


@dataclass(frozen=True)
class Choice:
    kind: str
    prompt: str
    options: tuple[ChoiceOption, ...]
    cancellable: bool = True
    # What the table needs to finish the command (JSON-safe; saved with the run).
    payload: Mapping[str, Any] = field(default_factory=dict)

    def option(self, option_id: str) -> ChoiceOption | None:
        return next((o for o in self.options if o.id == option_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "prompt": self.prompt, "options": [o.to_dict() for o in self.options],
                "cancellable": self.cancellable, "payload": dict(self.payload)}

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "Choice":
        return Choice(str(d["kind"]), str(d["prompt"]), tuple(ChoiceOption.from_dict(o) for o in d["options"]),
                      bool(d.get("cancellable", True)), dict(d.get("payload", {})))


@dataclass(frozen=True)
class Usability:
    ok: bool
    reason: str = ""  # why not, in English (empty when ok)

    def __bool__(self) -> bool:
        return self.ok


USABLE = Usability(True)


def unusable(reason: str) -> Usability:
    return Usability(False, reason)


@dataclass(frozen=True)
class Move:
    action: str        # a controller action id (bet, buy, use_item, choose, ...) or a table action
    arg: str = ""      # its argument (an item id, an option id); "" when it has none
    label: str = ""
    enabled: bool = True
    reason: str = ""   # why it is disabled
    table: bool = False  # a table's own action, run through GameController.perform
    listed: bool = True  # shown in the generic table-actions list (False: a part shows it next to its object)
