"""What the player owns at Poker Head's table: consumables, the build and money positions.

* `Holdings`: every consumable as an instance with the price actually paid,
  so Original Price Receipt refunds a specific purchase.
* `Loadout`: the core (or none) and the permanents in their slots.
* `Ledger`: open investments, loans and a loss larger than the cash. Net
  assets = cash + open principal − every repayment still owed; unrealised
  profit never counts.

All three are plain data with `to_dict` / `from_dict`; behaviour lives in the
table, effects and item handlers (docs/design/ITEM_ARCHITECTURE.md §4).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Holding:
    uid: str
    id: str                          # product id (or a starter alias, e.g. fate_oracle)
    paid: int = 0                    # chips actually paid (0 for gifts and starters)
    choices: tuple[str, ...] = ()    # cores an invitation or amendment offers, fixed when acquired


@dataclass
class Holdings:
    items: list[Holding] = field(default_factory=list)
    sequence: int = 0

    def add(self, item_id: str, paid: int = 0, choices: tuple[str, ...] = ()) -> Holding:
        self.sequence += 1
        holding = Holding(f"ph:{self.sequence}", item_id, paid, tuple(choices))
        self.items.append(holding)
        return holding

    def get(self, uid: str) -> Holding | None:
        return next((h for h in self.items if h.uid == uid), None)

    def first(self, item_id: str) -> Holding | None:
        """The oldest holding of an id (items are used oldest first)."""
        return next((h for h in self.items if h.id == item_id), None)

    def remove(self, uid: str) -> Holding:
        holding = self.get(uid)
        if holding is None:
            raise KeyError(uid)
        self.items.remove(holding)
        return holding

    def ids(self) -> tuple[str, ...]:
        return tuple(h.id for h in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence,
                "items": [{**asdict(h), "choices": list(h.choices)} for h in self.items]}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Holdings":
        items = [Holding(str(x["uid"]), str(x["id"]), int(x.get("paid", 0)), tuple(x.get("choices", ())))
                 for x in d.get("items", [])]
        return Holdings(items, int(d.get("sequence", len(items))))


@dataclass
class Loadout:
    core: str | None = None
    no_core: bool = False          # the opening cash was taken: no core for the whole run
    equipped: list[str] = field(default_factory=list)

    def has(self, item_id: str) -> bool:
        return item_id in self.equipped

    def active(self) -> tuple[str, ...]:
        """Core first, then permanents in slot order (the order effects apply in)."""
        return ((self.core,) if self.core else ()) + tuple(self.equipped)

    def to_dict(self) -> dict[str, Any]:
        return {"core": self.core, "no_core": self.no_core, "equipped": list(self.equipped)}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Loadout":
        return Loadout(d.get("core"), bool(d.get("no_core", False)), [str(x) for x in d.get("equipped", [])])


@dataclass(frozen=True)
class Position:
    uid: str
    id: str               # ph_deposit | ph_bond | ph_stock | ph_loan
    principal: int        # invested chips at cost (0 for a loan)
    debt: int             # repayment still owed (0 for investments)
    remaining: int        # rounds until maturity
    wins: int = 0         # won rounds since opening (Performance Bond)


@dataclass
class Ledger:
    positions: list[Position] = field(default_factory=list)
    sequence: int = 0
    settled: list[str] = field(default_factory=list)  # uids already paid out (never twice)
    shortfall: int = 0    # a loss larger than the cash (Fourfold Ticket), owed until the run ends

    def open(self, item_id: str, principal: int, debt: int, rounds: int) -> Position:
        self.sequence += 1
        position = Position(f"finance:{self.sequence}", item_id, principal, debt, rounds)
        self.positions.append(position)
        return position

    @property
    def invested(self) -> int:
        return sum(p.principal for p in self.positions)

    @property
    def debt(self) -> int:
        return sum(p.debt for p in self.positions) + self.shortfall

    def net_assets(self, cash: int) -> int:
        return cash + self.invested - self.debt

    def has(self, item_id: str) -> bool:
        return any(p.id == item_id for p in self.positions)

    def advance(self, won: bool) -> list[Position]:
        """One round passed: count it and return the positions that matured (removed)."""
        matured, kept = [], []
        for p in self.positions:
            p = replace(p, remaining=p.remaining - 1, wins=p.wins + int(won))
            (matured if p.remaining <= 0 else kept).append(p)
        for p in matured:
            if p.uid in self.settled:
                raise ValueError(f"Position {p.uid} was already settled")
            self.settled.append(p.uid)
        self.positions = kept
        return matured

    def close_all(self) -> None:
        """Victory: principal returns at cost and debts are paid (cash is set by the caller)."""
        self.settled.extend(p.uid for p in self.positions)
        self.positions = []
        self.shortfall = 0

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "positions": [asdict(p) for p in self.positions],
                "settled": list(self.settled), "shortfall": self.shortfall}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Ledger":
        positions = [Position(str(p["uid"]), str(p["id"]), int(p["principal"]), int(p.get("debt", 0)),
                              int(p["remaining"]), int(p.get("wins", 0))) for p in d.get("positions", [])]
        return Ledger(positions, int(d.get("sequence", len(positions))), [str(x) for x in d.get("settled", [])],
                      int(d.get("shortfall", 0)))
