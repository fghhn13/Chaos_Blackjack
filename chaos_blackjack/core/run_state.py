"""Run-level state model used for JSON saves.

This module intentionally contains only JSON-ready data structures.
It does not import UI modules and does not depend on live game objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


SaveVersion = Literal[1]


@dataclass(frozen=True)
class CardSnapshot:
    rank: str
    suit: str

    def to_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "suit": self.suit}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "CardSnapshot":
        return CardSnapshot(rank=str(d["rank"]), suit=str(d.get("suit", "")))


@dataclass(frozen=True)
class GameStateSnapshot:
    player_hand: list[CardSnapshot]
    dealer_hand: list[CardSnapshot]
    deck: list[CardSnapshot]
    phase: str
    chaos_budget_remaining: int
    inventory: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_hand": [c.to_dict() for c in self.player_hand],
            "dealer_hand": [c.to_dict() for c in self.dealer_hand],
            "deck": [c.to_dict() for c in self.deck],
            "phase": self.phase,
            "chaos_budget_remaining": self.chaos_budget_remaining,
            "inventory": list(self.inventory),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "GameStateSnapshot":
        return GameStateSnapshot(
            player_hand=[CardSnapshot.from_dict(x) for x in d.get("player_hand", [])],
            dealer_hand=[CardSnapshot.from_dict(x) for x in d.get("dealer_hand", [])],
            deck=[CardSnapshot.from_dict(x) for x in d.get("deck", [])],
            phase=str(d["phase"]),
            chaos_budget_remaining=int(d.get("chaos_budget_remaining", 0)),
            inventory=[str(x) for x in d.get("inventory", [])],
        )


@dataclass(frozen=True)
class ModifierSnapshot:
    id: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "params": dict(self.params)}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ModifierSnapshot":
        return ModifierSnapshot(
            id=str(d["id"]),
            params=dict(d.get("params") or {}),
        )


@dataclass(frozen=True)
class RunSaveData:
    """Entire save payload (JSON-ready)."""

    version: SaveVersion
    money: int
    start_money: int
    round: int
    items: list[str]
    objective: str
    win_streak: int

    target_money: int
    current_bet: int

    enable_chaos: bool
    # Optional snapshot for resuming mid-round.
    game_state: GameStateSnapshot | None
    active_modifiers: list[ModifierSnapshot]
    chaos_actions_this_turn: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": int(self.version),
            "money": self.money,
            "start_money": self.start_money,
            "round": self.round,
            "items": list(self.items),
            "objective": self.objective,
            "win_streak": self.win_streak,
            "target_money": self.target_money,
            "current_bet": self.current_bet,
            "enable_chaos": self.enable_chaos,
            "game_state": None if self.game_state is None else self.game_state.to_dict(),
            "active_modifiers": [m.to_dict() for m in self.active_modifiers],
            "chaos_actions_this_turn": self.chaos_actions_this_turn,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "RunSaveData":
        version_val = int(d.get("version", 1))
        version: SaveVersion = 1 if version_val == 1 else 1
        gs = d.get("game_state")
        return RunSaveData(
            version=version,
            money=int(d["money"]),
            start_money=int(d.get("start_money", d["money"])),
            round=int(d.get("round", 1)),
            items=[str(x) for x in d.get("items", [])],
            objective=str(d.get("objective", "double_money")),
            win_streak=int(d.get("win_streak", 0)),
            target_money=int(d.get("target_money", 400)),
            current_bet=int(d.get("current_bet", 0)),
            enable_chaos=bool(d.get("enable_chaos", False)),
            game_state=None if gs is None else GameStateSnapshot.from_dict(gs),
            active_modifiers=[ModifierSnapshot.from_dict(x) for x in d.get("active_modifiers", [])],
            chaos_actions_this_turn=int(d.get("chaos_actions_this_turn", 0)),
        )


class HasSaveData(Protocol):
    def to_dict(self) -> dict[str, Any]:
        ...

