"""Table mechanics — a mode's own rules around the hand (deck, fees, goods, goal).

Most tables play plain blackjack and have none. A mode that needs more (e.g.
J-54's persistent deck, docs/design/J54_TABLE.md, or Poker Head's builds,
docs/design/ITEM_ARCHITECTURE.md) registers a factory for its mode id;
`GameController` then calls the hooks below at fixed points of the round.
Every hook is declared here with a neutral default, so a table overrides only
what it changes and the controller never probes for optional methods.

    register_table("j54", J54Table)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from chaos_blackjack.core.game_state import Card, GameState

if TYPE_CHECKING:
    from chaos_blackjack.app.choice import Choice, Move, Usability
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.economy import RunState
    from chaos_blackjack.app.products import ProductDef
    from chaos_blackjack.app.shop import ShopOffer, ShopState
    from chaos_blackjack.app.view import RuleView, TablePublic
    from chaos_blackjack.contracts.items import ItemResult
    from chaos_blackjack.rules.modifiers import ActiveModifiers

Notify = Callable[[str, str, dict], None]  # (notice kind, text, data)


class TableMechanics:
    """Neutral hooks; subclasses override what their table changes."""

    id = ""
    # Chaos rules outlive the round (they are shown between rounds too).
    persistent_rules = False
    # The Chaos AI's per-round action budget means something here (False: the table changes rules itself).
    uses_chaos_budget = True
    # The table changes the rules itself (Poker Head's environment), instead of the Chaos AI's registry rules.
    environment_rules = False

    @classmethod
    def enabled(cls, config: "RunConfig") -> bool:
        """Whether this run uses the table (e.g. not for an older save of the mode)."""
        return True

    @classmethod
    def goal(cls, config: "RunConfig") -> str | None:
        """The goal in a few words for New run (None = the profile's chip target)."""
        return None

    def __init__(self, config: "RunConfig", seed: int | str, notify: Notify) -> None:
        self.config = config
        self.seed = seed
        self.notify = notify

    def bind(self, controller: "GameController") -> None:
        """The controller is built; called before `start` or `restore`."""

    # --- run --------------------------------------------------------------

    def start(self, run: "RunState") -> None:
        """A new run begins (not called when a save is restored)."""

    def summary(self) -> list[str]:
        """The host's description of the goal (replaces the generic rules line)."""
        return []

    def info(self, run: "RunState") -> tuple[tuple[str, str], ...]:
        """(label, value) rows the table shows next to the cards."""
        return ()

    def deck_counts(self) -> tuple[tuple[str, int], ...]:
        """(rank, cards) of the table's whole deck when its make-up is public (J-54), else ()."""
        return ()

    def victory(self, run: "RunState") -> str | None:
        """A message when the run is won, else None."""
        return None

    def goal_progress(self, run: "RunState") -> tuple[str, int, int] | None:
        """(label, value, target) when the goal is not the bankroll itself (e.g. net assets), else None."""
        return None

    def active_rules(self) -> "tuple[RuleView, ...] | None":
        """The table's own rules to show (None = the Chaos AI's modifiers in force this round)."""
        return None

    def public(self) -> "TablePublic | None":
        """A frozen snapshot of what any player may see (never undealt cards)."""
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

    def product(self, item_id: str) -> "ProductDef | None":
        """The catalog row an id stands for at this table (app/products.py)."""
        from chaos_blackjack.app.products import product

        return product(item_id)

    def roll_shop(self, reroll: bool = False) -> "ShopState | None":
        """The table's own stock, or None to let the controller roll the profile's items."""
        return None

    def offer_price(self, item_id: str, price: int) -> int:
        """What an offer costs right now (e.g. after a discount)."""
        return price

    def offer_note(self, item_id: str) -> str:
        """Why an offer's price differs from its base price (e.g. "+20% Price Hike"), or ""."""
        return ""

    def offer_usability(self, offer: "ShopOffer") -> "Usability | None":
        """Whether an offer can be bought now (None = the controller's bankroll check)."""
        return None

    def purchase(self, item_id: str, option: str = "") -> bool:
        """Handle a whole purchase (charging included); False = not this table's.
        `option` answers a question the purchase would ask (e.g. what to replace)."""
        return False

    def buy(self, item_id: str, run: "RunState") -> str:
        """Apply an own offer the controller already charged; returns the notice text."""
        raise NotImplementedError

    def reroll_price(self, price: int | None) -> int | None:
        """Chips the next reroll costs (`price` is the controller's), None = not allowed."""
        return price

    def rerolled(self, price: int) -> bool:
        """A paid reroll happened; True when the table keeps its own reroll count."""
        return False

    # --- items, choices and own actions -------------------------------------

    def item_usability(self, item_id: str) -> "Usability | None":
        """Whether a held item can be used now (None = only on your turn)."""
        return None

    def item_note(self, item_id: str) -> str:
        """A remark on a held item right now (e.g. an item ban), or ""."""
        return ""

    def hidden_player_cards(self) -> frozenset[int]:
        """Indexes of the player's cards dealt face down until the player's turn ends."""
        return frozenset()

    def use_item(self, item_id: str, target: str = "") -> "ItemResult | None":
        """Use an item of this table (None = a plain registry item)."""
        return None

    def resolve_choice(self, choice: "Choice", option: str) -> None:
        """Finish the command that asked `choice`, with the chosen option."""
        raise NotImplementedError

    def table_moves(self) -> tuple["Move", ...]:
        """The table's own actions now (e.g. a once-per-round permanent)."""
        return ()

    def perform(self, action: str, arg: str) -> object:
        """Run one of `table_moves`."""
        from chaos_blackjack.app.controller import ActionError

        raise ActionError(f"Unknown action {action!r}")

    def augment_actions(self, actions: frozenset[str]) -> frozenset[str]:
        """Adjust the phase's actions (e.g. allow surrender after hitting)."""
        return actions

    # --- round ------------------------------------------------------------

    def entered_betting(self) -> None:
        """The table returned to betting for a new round."""

    def before_bet(self) -> tuple[Card, ...] | None:
        """An already ordered deal (e.g. promised by a forecast), or None to shuffle."""
        return None

    def round_cards(self) -> tuple[Card, ...] | None:
        """The cards shuffled for a new round (None = a standard deck)."""
        return None

    def before_naturals(self, state: GameState) -> GameState:
        """The opening cards were dealt; naturals are checked next."""
        return state

    def natural_outcome(self, player: bool, dealer: bool) -> str | None:
        """Overrule the natural check (an outcome as in RoundResult, or None)."""
        return None

    def after_cards(self, state: GameState) -> GameState:
        """Cards were dealt or drawn (deal, hit, double, dealer draw, item)."""
        return state

    def should_chaos(self) -> bool:
        """Whether the Chaos AI acts this round."""
        return True

    def after_chaos(self, state: GameState, modifiers: "ActiveModifiers") -> tuple[GameState, "ActiveModifiers"]:
        """The Chaos AI acted; the table may apply rules that change the deck."""
        return state, modifiers

    def entered_player(self) -> None:
        """The player's turn began."""

    def double_multiplier(self) -> int:
        """How many times the bet a double stakes."""
        return 2

    def plays_out_bust(self) -> bool:
        """A player bust waits for the dealer to play (the outcome then decides) instead of settling at once."""
        return False

    def double_cover(self) -> int:
        """How many times the bet the bankroll must cover for a double to be offered."""
        return self.double_multiplier()

    def surrender_refund(self, bet: int) -> int:
        """Chips returned on surrender."""
        return bet // 2

    def settlement(self, state: GameState, outcome: str, bet: int, doubled: bool, delta: int) -> int:
        """Final hand cash delta, before it is published or applied."""
        return delta

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
    enabled = getattr(factory, "enabled", lambda config: True)
    return factory(config, seed, notify) if factory is not None and enabled(config) else None


def table_factory(config: "RunConfig") -> Callable[..., TableMechanics] | None:
    """The table class a config would play at (None: a plain table, or a mode whose table is off)."""
    _load_builtin_tables()
    factory = _TABLES.get(config.mode)
    enabled = getattr(factory, "enabled", lambda config: True)
    return factory if factory is not None and enabled(config) else None


def table_goal(config: "RunConfig") -> str | None:
    """The goal a mode's table sets for New run, or None for a plain chip target."""
    _load_builtin_tables()
    factory = _TABLES.get(config.mode)
    goal = getattr(factory, "goal", None)
    enabled = getattr(factory, "enabled", lambda config: True)
    return goal(config) if goal is not None and enabled(config) else None


def _load_builtin_tables() -> None:
    import chaos_blackjack.j54.table  # noqa: F401  (registers "j54")
    import chaos_blackjack.poker_head.table  # noqa: F401  (registers "chaos")
