"""Table mechanics — a mode's own rules around the hand (deck, fees, contracts, goal).

Most tables play plain blackjack and have none. A mode that needs more (e.g.
J-54's persistent deck, docs/design/J54_TABLE.md) registers a factory for its
mode id; `GameController` then calls the hooks below at fixed points of the
round. Every hook has a neutral default, so a table overrides only what it
changes.

    register_table("j54", J54Table)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from chaos_blackjack.core.game_state import Card, GameState

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.economy import RunState
    from chaos_blackjack.rules.modifiers import ActiveModifiers

Notify = Callable[[str, str, dict], None]  # (notice kind, text, data)


class TableMechanics:
    """Neutral hooks; subclasses override what their table changes."""

    id = ""

    @classmethod
    def goal(cls, config: "RunConfig") -> str | None:
        """The goal in a few words for New run (None = the profile's chip target)."""
        return None

    def __init__(self, config: "RunConfig", seed: int | str, notify: Notify) -> None:
        self.config = config
        self.seed = seed
        self.notify = notify

    # --- run --------------------------------------------------------------

    def start(self, run: "RunState") -> None:
        """A new run begins (not called when a save is restored)."""

    def summary(self) -> list[str]:
        """The host's description of the goal (replaces the generic rules line)."""
        return []

    def info(self, run: "RunState") -> tuple[tuple[str, str], ...]:
        """(label, value) rows the table shows next to the cards."""
        return ()

    def victory(self, run: "RunState") -> str | None:
        """A message when the run is won, else None."""
        return None

    # --- economy ----------------------------------------------------------

    def fee(self, round_no: int) -> int:
        """Chips charged before the bet of this round."""
        return 0

    def min_bet(self, round_no: int) -> int:
        """Lowest bet this round (the profile's min bet still applies)."""
        return 0

    # --- shop -------------------------------------------------------------

    def sells(self, item_id: str) -> bool:
        """Whether `item_id` is one of this table's own offers (not an item)."""
        return False

    def stockable(self, item_id: str) -> bool:
        """Whether an own offer may be rolled into the shop right now."""
        return self.sells(item_id)

    def pinned(self) -> tuple[str, ...]:
        """Own offers always on the shelf (not rolled)."""
        return ()

    def describe(self, item_id: str) -> str:
        return ""

    def buy(self, item_id: str, run: "RunState") -> str:
        """Apply a bought own offer; returns the text of the purchase notice."""
        raise NotImplementedError

    # --- round ------------------------------------------------------------

    def round_cards(self) -> tuple[Card, ...] | None:
        """The cards shuffled for a new round (None = a standard deck)."""
        return None

    def after_cards(self, state: GameState) -> GameState:
        """Cards were dealt or drawn (deal, hit, double, dealer draw, item)."""
        return state

    def after_chaos(self, state: GameState, modifiers: "ActiveModifiers") -> tuple[GameState, "ActiveModifiers"]:
        """The Chaos AI acted; the table may apply rules that change the deck."""
        return state, modifiers

    def after_settle(self, state: GameState, outcome: str, modifiers: "ActiveModifiers", run: "RunState") -> None:
        """The round was settled (outcome as in RoundResult)."""

    @property
    def ends_hand(self) -> bool:
        """True once the table ended the hand by itself (e.g. a captured Joker)."""
        return False

    # --- save -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {}

    def restore(self, data: dict[str, Any]) -> None:
        pass


_TABLES: dict[str, Callable[..., TableMechanics]] = {}


def register_table(mode_id: str, factory: Callable[..., TableMechanics]) -> None:
    _TABLES[mode_id] = factory


def make_table(config: "RunConfig", seed: int | str, notify: Notify) -> TableMechanics | None:
    """The mechanics of the run's mode, or None for a plain table."""
    _load_builtin_tables()
    factory = _TABLES.get(config.mode)
    return factory(config, seed, notify) if factory is not None else None


def table_goal(config: "RunConfig") -> str | None:
    """The goal a mode's table sets for New run, or None for a plain chip target."""
    _load_builtin_tables()
    factory = _TABLES.get(config.mode)
    goal = getattr(factory, "goal", None)
    return goal(config) if goal is not None else None


def _load_builtin_tables() -> None:
    import chaos_blackjack.j54  # noqa: F401  (registers "j54")
