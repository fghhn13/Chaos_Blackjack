"""GameController — one run of Chaos Blackjack, independent of any UI.

Front-ends (CLI, GUI, tests, bots) drive it with a small command set and read
back two things:

* `view()`           -> GameView, an immutable snapshot to render
* `drain_notices()`  -> list[Notice], what happened since the last drain

Flow:  BETTING [-buy*] -place_bet-> [CHAOS -resolve_chaos->] PLAYER_TURN
       -hit/stand/double_down/use_item-> DEALER_TURN -dealer_step*-> ROUND_OVER
       -next_round-> BETTING ... until RUN_OVER.

Naturals are checked against the original two cards before chaos:
a player natural pays `blackjack_pays` (3:2), a dealer natural
wins at once, both is a push. Double and surrender are first-decision only.

The shop is open while betting: `buy(item_id)` spends bankroll on one of a
few offers, `reroll_shop()` rolls the current stock again once, and the stock
rolls again every `shop_refresh_rounds` rounds.

Every step is explicit (e.g. the dealer draws one card per `dealer_step()`),
so a GUI can animate between steps and a CLI can just loop.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import replace

from chaos_blackjack.ai.memory import ChaosMemory
from chaos_blackjack.app.chaos_context import build_chaos_context
from chaos_blackjack.ai.pipeline import OfflineChaosStub
from chaos_blackjack.app.choice import USABLE, Choice, Move, Usability, unusable
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.economy import (
    RunState,
    bet_limits,
    settlement_delta,
    update_streak,
)
from chaos_blackjack.app.item_use import inventory_counts, use_item
from chaos_blackjack.app.notices import EventTranslator, Notice, NoticeKind
from chaos_blackjack.app.persistence import (
    build_save_data,
    deserialize_active_modifiers,
    snapshot_to_game_state,
)
from chaos_blackjack.app.help_text import ITEM_HELP
from chaos_blackjack.app.products import ProductDef, product as catalog_product
from chaos_blackjack.app.shop import (
    ShopOffer, ShopState, needs_restock, roll_stock, rounds_until_restock, shop_prices,
)
from chaos_blackjack.app.run_log import RunLog
from chaos_blackjack.app.table_mechanics import TableMechanics, make_table
from chaos_blackjack.app.view import (
    Action,
    CardView,
    GameView,
    ItemView,
    RoundResult,
    RuleView,
    ShopOfferView,
    TablePhase,
)
from chaos_blackjack.contracts.items import ItemResult
from chaos_blackjack.contracts.chaos_interaction import PokeReply, PokeRequest
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import GamePhase, GameState
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.data.saves import save_run
from chaos_blackjack.events.dispatcher import EventDispatcher
from chaos_blackjack.events.event import Event
from chaos_blackjack.logic.run_end_policy import (
    CompositeRunEndPolicy,
    MoneyBankruptDefeatPolicy,
    MoneyTargetVictoryPolicy,
    RunEndPolicy,
    RunEndResult,
)
from chaos_blackjack.ui.descriptions import describe_modifier


NO_VALID_BET_MESSAGE = "You no longer have enough bankroll to place a valid bet. Game Over."

_ACTIONS_BY_PHASE: dict[TablePhase, frozenset[str]] = {
    TablePhase.BETTING: frozenset({Action.BET, Action.BUY, Action.SAVE}),
    TablePhase.CHAOS: frozenset({Action.RESOLVE_CHAOS}),
    TablePhase.PLAYER_TURN: frozenset({Action.HIT, Action.STAND, Action.USE_ITEM, Action.SAVE}),
    TablePhase.DEALER_TURN: frozenset({Action.DEALER_STEP}),
    TablePhase.ROUND_OVER: frozenset({Action.NEXT_ROUND, Action.SAVE}),
    TablePhase.RUN_OVER: frozenset(),
}


class ActionError(ValueError):
    """Command not allowed in the current phase, or invalid argument."""


def default_run_end_policy() -> RunEndPolicy:
    return CompositeRunEndPolicy(
        policies=(MoneyBankruptDefeatPolicy(), MoneyTargetVictoryPolicy()),
    )


class GameController:
    def __init__(
        self,
        config: RunConfig | None = None,
        *,
        loop_factory: Callable[[EventDispatcher], GameLoop] | None = None,
        run_end_policy: RunEndPolicy | None = None,
        save_fn: Callable[[RunSaveData, str], object] = save_run,
    ) -> None:
        from chaos_blackjack import auto_load_plugins

        auto_load_plugins()
        self.config = (config or RunConfig()).resolved()
        from chaos_blackjack.content.loader import load_content_packs
        from chaos_blackjack.content.ai_profile import build_pipeline

        content = load_content_packs(self.config.content_packs)
        self.registry = content.registry
        if self.config.ai_id not in self.registry.ai_ids():
            raise ValueError(f"Unknown AI id: {self.config.ai_id}")
        for item_id in (*self.config.starting_items, *content.starting_items):
            if self.registry.resolve_item(item_id) is None:
                raise ValueError(f"Unknown configured item id: {item_id}")
        self._translator = EventTranslator()
        self._notices: list[Notice] = []
        self._listeners: list[Callable[[Notice], None]] = []
        self._dispatcher = EventDispatcher()
        self._dispatcher.set_default(self._on_core_event)

        factory = loop_factory or (lambda d: GameLoop(
            dispatcher=d,
            pipeline=build_pipeline(self.config.ai_id, self.registry, use_llm=self.config.use_llm),
        ))
        self.loop = factory(self._dispatcher)
        self.loop.pipeline.registry = self.registry
        self.loop.initial_inventory = ()
        self._configure_chaos()
        self.rng = random.Random(self.config.seed)
        self._poke_rng = random.Random(None if self.config.seed is None else f"{self.config.seed}:poke")
        self.chaos_memory = ChaosMemory(enabled=self.config.chaos_memory_enabled,
                                        limit=self.config.chaos_memory_limit)
        self.run_end_policy = run_end_policy or default_run_end_policy()
        self._save_fn = save_fn

        self.run = RunState(
            money=self.config.start_money,
            start_money=self.config.start_money,
            round=1,
            target_money=self.config.target_money,
            objective=self.config.objective,
            win_streak=0,
            current_bet=0,
            items=(*self.config.starting_items, *content.starting_items),
        )
        # The whole run's record (saved with the run; the GUI's run panel shows it).
        self.run_log = RunLog()
        self.run_log.stats["peak"] = self.run.money
        self.state: GameState | None = None
        self.phase = TablePhase.BETTING
        self.last_result: RoundResult | None = None
        self.run_end: RunEndResult | None = None
        self._doubled = False
        self._dealer_blackjack = False
        self.hole_revealed = False
        # A question a command asked (app/choice.py); only choose / cancel / save until answered.
        self.choice: Choice | None = None
        # Shop rolls (and the offline Chaos AI) are seeded apart from the deal,
        # so buying never changes the cards.
        self.shop_seed = self.config.seed if self.config.seed is not None else random.randrange(2**31)
        # The mode's own mechanics (docs/design/J54_TABLE.md), None for a plain table.
        self.table: TableMechanics | None = make_table(self.config, self.shop_seed, self._notify)
        if self.table is not None:
            self.table.bind(self)
            self.table.start(self.run)
        self.shop = self._roll_shop()
        self._check_can_bet()

    # ------------------------------------------------------------------ load

    @classmethod
    def from_save(
        cls,
        data: RunSaveData,
        config: RunConfig | None = None,
        **kwargs,
    ) -> "GameController":
        # A save that carries its config restores those numbers; `config` can
        # still switch chaos on. Older saves take the numbers from `config`.
        if data.config:
            base = RunConfig.from_dict(data.config)
            if config is not None and config.enable_chaos:
                base = replace(base, enable_chaos=True)
        else:
            base = config or RunConfig()
        cfg = replace(
            base,
            start_money=data.start_money,
            target_money=data.target_money,
            objective=data.objective,
            enable_chaos=bool(base.enable_chaos or data.enable_chaos),
        )
        if cfg.mode == "chaos" and data.table is None:
            settings = dict(cfg.mode_settings)
            settings["chaos.build_version"] = 0
            cfg = replace(cfg, mode_settings=settings)
        c = cls(cfg, **kwargs)
        c.run.money = data.money
        c.run.round = data.round
        c.run.win_streak = data.win_streak
        c.run.current_bet = data.current_bet
        c.run.items = tuple(data.items)
        c.loop._chaos_actions_this_turn = int(data.chaos_actions_this_turn)
        if data.shop_seed is not None:
            c.shop_seed = data.shop_seed
        if c.table is not None and data.table is not None:
            c.table.restore(data.table)
            c.run.objective, c.run.target_money = data.objective, data.target_money
        c.shop = ShopState.from_dict(data.shop) if data.shop else c._roll_shop()
        c.choice = Choice.from_dict(data.choice) if data.choice else None
        c.hole_revealed = data.hole_revealed
        c.chaos_memory.restore(data.chaos_memory)
        c.run_log.restore(data.log)
        c.run_end = None
        c.phase = TablePhase.BETTING

        if data.game_state is None:
            c._check_can_bet()
            return c

        c.state = snapshot_to_game_state(data.game_state)
        if data.active_modifiers:
            c.loop.modifiers = deserialize_active_modifiers(
                data.active_modifiers, registry=c.registry, rule_params=cfg.chaos_rule_params,
            )
        if c.state.phase == GamePhase.PLAYER_TURN:
            c._set_phase(TablePhase.PLAYER_TURN)
        elif c.state.phase == GamePhase.DEALER_TURN:
            c._set_phase(TablePhase.DEALER_TURN)
        else:
            c._settle()
        return c

    # -------------------------------------------------------------- commands

    def place_bet(self, amount: int) -> None:
        self._require(Action.BET)
        lo, hi = self.bet_limits(self.run.money)
        if not lo <= amount <= hi:
            raise ActionError(f"Invalid bet. Allowed range: {lo}~{hi}")
        ordered = self.table.before_bet() if self.table is not None else None
        fee = self._fee()
        if fee:
            self.run.money -= fee
            self._notify(NoticeKind.FEE_PAID, f"Compute fee: {fee} chips.", {"fee": fee})
        self.run.current_bet = amount
        self.last_result = None
        cards = self.table.round_cards() if self.table is not None else None
        self.state = self.loop.new_round(
            seed=self.rng.randint(0, 2**30),
            inventory_override=self.run.items,
            **({"cards": cards} if cards is not None else {}),
            **({"ordered_cards": ordered} if ordered is not None else {}),
        )
        if self.table is not None:
            self.state = self.table.before_naturals(self.state)
        self._doubled = False
        self._dealer_blackjack = False
        self.hole_revealed = False
        self._notify(NoticeKind.ROUND_STARTED, data={"round": self.run.round, "bet": amount})
        if self._table_cards():
            return
        if self._settle_naturals():
            return
        if self.config.enable_chaos and (self.table is None or self.table.should_chaos()):
            self._set_phase(TablePhase.CHAOS)
        else:
            self._enter_player_turn()

    def buy(self, item_id: str, option: str = "") -> None:
        """Buy one shop offer. You must keep enough bankroll to place a bet.
        `option` answers a question the purchase would ask (e.g. which
        permanent to replace); without it the purchase may ask a Choice."""
        self._require(Action.BUY)
        if self.table is not None and self.table.purchase(item_id, option):
            return
        offer = self.shop.offer(item_id)
        if offer is None:
            raise ActionError(f"The shop has no {item_id!r} for sale")
        if not self.can_bet(self.run.money - offer.price):
            raise ActionError(f"Not enough chips: {item_id} costs {offer.price} and you must keep enough to bet")
        self.run.money -= offer.price
        self.shop = self.shop.with_sold(item_id)
        if self.table is not None and self.table.sells(item_id):
            # A table's own offer (e.g. a J-54 contract) takes effect; it is not carried.
            text = self.table.buy(item_id, self.run)
            self._notify(NoticeKind.ITEM_BOUGHT, f"{text} ({offer.price} chips)",
                         {"item": item_id, "price": offer.price, "table": True})
            return
        self.run.items = self.run.items + (item_id,)
        self._notify(
            NoticeKind.ITEM_BOUGHT,
            f"Bought {item_id} for {offer.price}.",
            {"item": item_id, "price": offer.price},
        )

    def resolve_chaos(self) -> None:
        """Let the Chaos AI act once. May block on an LLM call — GUIs should
        run this off the render thread. The caller must not read or mutate
        this controller (including draining notices) until the call finishes;
        render a cached GameView while waiting."""
        self._require(Action.RESOLVE_CHAOS)
        if self.table is not None and not self.table.should_chaos():
            self._enter_player_turn()
            return
        llm = getattr(getattr(self.loop, "pipeline", None), "llm", None)
        if isinstance(llm, OfflineChaosStub):
            llm.reseed(f"{self.shop_seed}:chaos:{self.run.round}")
        self.state = self.loop.maybe_apply_chaos_phase(self._st, context_json=build_chaos_context(self))
        if self.table is not None:
            self.state, self.loop.modifiers = self.table.after_chaos(self._st, self.loop.modifiers)
        narration = self.loop.last_chaos_narration
        if narration:
            self._notify(NoticeKind.CHAOS_NARRATION, narration, {"text": narration})
        self._enter_player_turn()

    def prepare_poke(self) -> PokeRequest:
        """Capture a private immutable context before starting the reply worker."""
        if not self.config.enable_chaos or self.phase not in (
            TablePhase.BETTING, TablePhase.PLAYER_TURN, TablePhase.ROUND_OVER,
        ):
            raise ActionError("Chaos cannot be poked during this phase")
        intent = "guide" if self._poke_rng.random() < self.config.chaos_guidance_probability else "mislead"
        return PokeRequest(build_chaos_context(self), intent)

    def accept_poke_reply(self, request: PokeRequest, reply: PokeReply) -> bool:
        """Publish on the UI thread; ignore a reply for a changed game state."""
        if not reply.ok or request.context_json != build_chaos_context(self):
            return False
        self._notify(NoticeKind.CHAOS_POKE_REPLY, reply.text, {"text": reply.text})
        return True

    def hit(self) -> None:
        self._require(Action.HIT)
        self.state = self.loop.draw_for_player(self._st)
        if not self._table_cards():
            self._settle_if_player_bust()

    def stand(self) -> None:
        self._require(Action.STAND)
        self._to_dealer()

    def double_down(self) -> None:
        """Double the bet, take exactly one card, then stand."""
        self._require(Action.DOUBLE)
        self.run.current_bet *= self._double_multiplier()
        self._doubled = True
        self._notify(
            NoticeKind.DOUBLED,
            f"Double down! Bet is now {self.run.current_bet}.",
            {"bet": self.run.current_bet},
        )
        self.state = self.loop.draw_for_player(self._st)
        if self._table_cards():
            return
        if not self._settle_if_player_bust():
            self._to_dealer()

    def surrender(self) -> None:
        """Give up the hand and get half the bet back."""
        self._require(Action.SURRENDER)
        bet = self.run.current_bet
        refund = self.table.surrender_refund(bet) if self.table is not None else bet // 2
        self._notify(NoticeKind.SURRENDERED, f"You surrender. {refund} returned.", {"refund": refund})
        self.state = self._st.with_phase(GamePhase.RESOLVED)
        self._settle("surrender")

    def use_item(self, item_id: str, target: str = "") -> ItemResult:
        """Use a held item. `target` answers the question a targeted item would
        ask (a rule, another item); without it the item may ask a Choice."""
        self._require(Action.USE_ITEM)
        if self.table is not None:
            result = self.table.use_item(item_id, target)
            if result is not None:
                if result.message:
                    self._notify(NoticeKind.ITEM_RESULT, result.message, {"item": item_id, "ok": result.ok})
                if result.ok:
                    self._after_table_change()
                return result
        self.state, result = use_item(self.loop, self._st, item_id, self.config.item_params.get(item_id))
        self.run.items = self._st.inventory
        extra = result.extra or {}
        if result.ok and extra.get("reveal_hole_card"):
            self.hole_revealed = True
        self._notify(
            NoticeKind.ITEM_RESULT,
            result.message,
            {"item": item_id, "ok": result.ok},
        )
        if result.ok and extra.get("dispel_chaos_rules"):
            self._notify(NoticeKind.CHAOS_DISPELLED, "Chaos rules dispelled for this round.")
        if result.ok and not self._table_cards():
            # Swapping a card or dropping a rule can push the hand over.
            self._settle_if_player_bust()
        return result

    def perform(self, action: str, arg: str = "") -> object:
        """Run an action a widget sent (app/widgets.py `Act`): a controller
        command by id, or one of the table's own moves. Raises ActionError when
        the action is unknown or not allowed now."""
        if action == Action.USE_ITEM:
            return self.use_item(arg)
        if action == Action.BUY:
            return self.buy(arg)
        if action == Action.CHOOSE:
            return self.choose(arg)
        if action == Action.CANCEL:
            return self.cancel_choice()
        move = next((m for m in self._table_moves() if m.action == action and m.arg == arg), None)
        if move is None:
            raise ActionError(f"Unknown action {action!r}")
        if not move.enabled or self.choice is not None:
            raise ActionError(move.reason or f"'{action}' is not allowed now")
        result = self.table.perform(action, arg)
        self._after_table_change()
        return result

    # ------------------------------------------------------------- choices

    def ask(self, choice: Choice) -> None:
        """A command needs a decision: hold it until `choose` or `cancel`."""
        if not choice.options:
            raise ActionError("There is nothing to choose.")
        self.choice = choice
        self._notify(NoticeKind.CHOICE_OPENED, choice.prompt, {"kind": choice.kind})

    def choose(self, option: str) -> None:
        """Answer the pending choice; the table finishes the command that asked it."""
        self._require(Action.CHOOSE)
        choice = self.choice
        assert choice is not None
        if choice.option(option) is None:
            raise ActionError("Choose one of the offered options.")
        self.choice = None
        try:
            assert self.table is not None
            self.table.resolve_choice(choice, option)
        except Exception:
            self.choice = choice  # nothing was applied; ask again
            raise
        self._notify(NoticeKind.CHOICE_CLOSED, data={"kind": choice.kind, "option": option})
        self._after_table_change()

    def cancel_choice(self) -> None:
        """Drop the pending choice; the command that asked it changes nothing."""
        self._require(Action.CANCEL)
        assert self.choice is not None
        kind, self.choice = self.choice.kind, None
        self._notify(NoticeKind.CHOICE_CLOSED, "Cancelled.", {"kind": kind, "option": None})

    def dealer_step(self) -> bool:
        """Advance the dealer by one decision. Returns True while the dealer
        still has more to do."""
        self._require(Action.DEALER_STEP)
        ctx = self.loop.context("dealer")
        dv = self._value(self._st.dealer_hand, "dealer")
        if self.loop.rules.is_bust(dv, ctx):
            self._notify(NoticeKind.DEALER_BUSTS, "Dealer busts.", {"total": dv})
        elif dv >= self.config.dealer_stand_on:
            self._notify(NoticeKind.DEALER_STANDS, f"Dealer stands at {dv}.", {"total": dv})
        elif self._st.deck:
            self.state = self.loop.draw_for_dealer(self._st)
            self._table_cards()
            return True
        self.state = self._st.with_phase(GamePhase.RESOLVED)
        self._settle()
        return False

    def finish_dealer(self) -> None:
        while self.phase == TablePhase.DEALER_TURN and self.dealer_step():
            pass

    def reroll_price(self) -> int | None:
        """Chips the next shop reroll costs (0 when a free reroll is left), or
        None when this stock was already rerolled."""
        if self.shop.rerolled:
            price = None
        else:
            price = 0 if self.shop.free_rerolls_used < self.config.free_rerolls else self.config.shop_reroll_price
        return self.table.reroll_price(price) if self.table is not None else price

    def reroll_shop(self) -> None:
        """Roll the current stock again (once per stock); keep enough bankroll to bet."""
        if self.phase != TablePhase.BETTING or self.choice is not None:
            self._require(Action.REROLL)
        price = self.reroll_price()
        if price is None:
            raise ActionError("This stock was already rerolled; wait for the next restock")
        if not self.can_bet(self.run.money - price):
            import math
            required = price + math.ceil(self.config.min_bet / self.config.max_bet_fraction)
            raise ActionError(f"Not enough chips: a reroll costs {price}; you need at least {required} chips to keep betting")
        self.run.money -= price
        if self.table is not None and self.table.rerolled(price):
            self.shop = self._roll_shop(reroll=True)
        else:
            free_used = self.shop.free_rerolls_used + (1 if price == 0 else 0)
            stock = self._roll_shop(reroll=True)
            self.shop = ShopState(self.shop.stock_round, stock.offers, rerolled=True, free_rerolls_used=free_used)
        self._notify(
            NoticeKind.SHOP_REROLLED,
            "The shop rerolled its stock." + (f" Cost {price}." if price else " Free reroll used."),
            {"price": price},
        )

    def next_round(self) -> None:
        self._require(Action.NEXT_ROUND)
        self.state = None
        self._set_phase(TablePhase.BETTING)
        if self.table is not None:
            self.table.entered_betting()
        self._check_can_bet()
        if self.phase == TablePhase.RUN_OVER:
            return
        if needs_restock(self.shop, self.run.round, self.config.shop_refresh_rounds):
            used = self.shop.free_rerolls_used
            self.shop = self._roll_shop()
            self.shop = ShopState(self.shop.stock_round, self.shop.offers, free_rerolls_used=used)
            self._notify(NoticeKind.SHOP_RESTOCKED, "The shop has new stock.")
        self._check_can_bet()

    def save(self, name: str) -> RunSaveData:
        self._require(Action.SAVE)
        data = build_save_data(
            run=self.run,
            state=self.state if self.phase == TablePhase.PLAYER_TURN else None,
            loop=self.loop,
            enable_chaos=self.config.enable_chaos,
            shop=self.shop,
            shop_seed=self.shop_seed,
            hole_revealed=self.hole_revealed,
            chaos_memory=self.chaos_memory.export(),
            config=self.config.to_dict(),
            table=self.table.to_dict() if self.table is not None else None,
            log=self.run_log.to_dict(),
            choice=self.choice.to_dict() if self.choice is not None else None,
        )
        path = self._save_fn(data, name)
        self._notify(NoticeKind.GAME_SAVED, "Game saved successfully.", {"path": str(path)})
        return data

    # ------------------------------------------------------------ read side

    def bet_limits(self, money: int | None = None) -> tuple[int, int]:
        """Allowed bet range for `money` (default: the current bankroll) under this run's config."""
        m = (self.run.money if money is None else money) - self._fee()
        lo, hi = bet_limits(m, min_bet=self.config.min_bet, max_fraction=self.config.max_bet_fraction)
        if self.table is not None:
            lo = max(lo, self.table.min_bet(self.run.round))
        return lo, hi

    def can_bet(self, money: int | None = None) -> bool:
        """Whether `money` (default: the bankroll) still allows a minimum bet; shop
        purchases must leave this true."""
        lo, hi = self.bet_limits(money)
        return hi >= lo

    def add_listener(self, fn: Callable[[Notice], None]) -> None:
        """Call `fn` with every notice as it happens, without consuming it
        (front-ends keep draining notices). Listeners run on whatever thread
        drives the controller, e.g. the chaos worker; keep them small."""
        self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[Notice], None]) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    def drain_notices(self) -> list[Notice]:
        out = self._notices
        self._notices = []
        return out

    def view(self) -> GameView:
        st = self.state
        hide_hole = self.phase in (TablePhase.CHAOS, TablePhase.PLAYER_TURN) and not self.hole_revealed
        lo, hi = self.bet_limits(self.run.money)
        player_cards: tuple[CardView, ...] = ()
        dealer_cards: tuple[CardView, ...] = ()
        player_total = dealer_total = None
        if st is not None:
            # A table may deal player cards face down until the player's turn ends (Poker Head's Face-Down Card).
            hidden = (self.table.hidden_player_cards() if self.table is not None and self.phase in (
                TablePhase.CHAOS, TablePhase.PLAYER_TURN) else frozenset())
            player_cards = tuple(CardView(str(c.rank), c.suit, face_up=i not in hidden)
                                 for i, c in enumerate(st.player_hand))
            dealer_cards = tuple(
                CardView(str(c.rank), c.suit, face_up=not (hide_hole and i == 1))
                for i, c in enumerate(st.dealer_hand)
            )
            player_total = None if hidden else self._value(st.player_hand)
            if not hide_hole:
                dealer_total = self._value(st.dealer_hand, "dealer")
        inventory = st.inventory if st is not None else self.run.items
        moves = self.moves()
        enabled = {(m.action, m.arg): m for m in moves}

        def item_view(item_id: str, count: int) -> ItemView:
            m = enabled.get((Action.USE_ITEM, item_id))
            row = self.product(item_id)
            return ItemView(item_id, count, self._describe_offer(item_id), bool(m and m.enabled),
                            row.name if row else "", row.when if row else "On your turn", m.reason if m else "",
                            row.group if row else "", self.table.item_note(item_id) if self.table is not None else "")

        def offer_view(o: ShopOffer) -> ShopOfferView:
            m = enabled.get((Action.BUY, o.item))
            row = self.product(o.item)
            price = self._offer_price(o)
            return ShopOfferView(o.item, price, o.sold, bool(m and m.enabled), self._describe_offer(o.item),
                                 row.name if row else "", row.kind if row else "", row.when if row else "",
                                 m.reason if m else "", row.group if row else "",
                                 o.price if price != o.price else None,
                                 self.table.offer_note(o.item) if self.table is not None and price != o.price else "")

        return GameView(
            phase=self.phase,
            round=self.last_result.round if self.phase == TablePhase.ROUND_OVER and self.last_result else self.run.round,
            money=self.run.money,
            start_money=self.run.start_money,
            target_money=self.run.target_money,
            objective=self.run.objective,
            current_bet=self.run.current_bet,
            bet_min=lo,
            bet_max=hi,
            win_streak=self.run.win_streak,
            player_cards=player_cards,
            dealer_cards=dealer_cards,
            player_total=player_total,
            dealer_total=dealer_total,
            deck_count=len(st.deck) if st is not None else 0,
            items=tuple(item_view(i, n) for i, n in inventory_counts(inventory)),
            shop_offers=tuple(offer_view(o) for o in self.shop.offers),
            shop_restock_in=rounds_until_restock(self.shop, self.run.round, self.config.shop_refresh_rounds),
            hole_revealed=self.hole_revealed,
            chaos_enabled=self.config.enable_chaos,
            chaos_budget=st.chaos_budget_remaining if st is not None else self.loop.chaos_budget_initial,
            # Modifiers are only cleared on the next deal; between rounds none apply.
            active_rules=self._active_rules(st),
            narration=self.loop.last_chaos_narration,
            available_actions=self._available_actions(),
            last_result=self.last_result,
            run_end=self.run_end,
            shop_reroll_price=self.reroll_price() if self.phase == TablePhase.BETTING else None,
            table_info=self.table.info(self.run) if self.table is not None else (),
            fee=self._fee(),
            deck_counts=self.table.deck_counts() if self.table is not None else (),
            moves=moves,
            choice=self.choice,
            table_public=self.table.public() if self.table is not None else None,
            goal=self.table.goal_progress(self.run) if self.table is not None else None,
            chaos_budget_shown=self.table is None or self.table.uses_chaos_budget,
        )

    def moves(self) -> tuple[Move, ...]:
        """Everything the player could do now, each enabled or with a reason
        (docs/design/ITEM_ARCHITECTURE.md §7). Automatic steps (Chaos,
        dealer draws) and saving are not moves."""
        if self.choice is not None:
            out = [Move(Action.CHOOSE, o.id, o.label) for o in self.choice.options]
            if self.choice.cancellable:
                out.append(Move(Action.CANCEL, "", "Cancel"))
            return tuple(out)
        actions = self._available_actions()
        out: list[Move] = []
        if self.phase == TablePhase.BETTING:
            lo, hi = self.bet_limits()
            out.append(Move(Action.BET, "", "Bet", Action.BET in actions and hi >= lo,
                            "" if hi >= lo else "Not enough chips for the minimum bet."))
            for o in self.shop.offers:
                u = self.offer_usability(o)
                row = self.product(o.item)
                out.append(Move(Action.BUY, o.item, row.name if row else o.item, u.ok, u.reason))
            if self.shop.offers:
                price = self.reroll_price()
                reason = (("This stock was already rerolled." if self.shop.rerolled else "No reroll here.") if price is None
                          else "" if Action.REROLL in actions else "Keep enough chips to bet.")
                out.append(Move(Action.REROLL, "", "Reroll", Action.REROLL in actions, reason))
        elif self.phase == TablePhase.PLAYER_TURN:
            for action, label in ((Action.HIT, "Hit"), (Action.STAND, "Stand"), (Action.DOUBLE, "Double"),
                                  (Action.SURRENDER, "Surrender")):
                out.append(Move(action, "", label, action in actions, "" if action in actions else "Not allowed now."))
        elif self.phase == TablePhase.ROUND_OVER:
            out.append(Move(Action.NEXT_ROUND, "", "Next round"))
        if self.phase in (TablePhase.BETTING, TablePhase.PLAYER_TURN):
            items = self.state.inventory if self.state is not None else self.run.items
            for item_id, _ in inventory_counts(items):
                u = self.item_usability(item_id)
                row = self.product(item_id)
                out.append(Move(Action.USE_ITEM, item_id, row.name if row else item_id, u.ok, u.reason))
        out.extend(self._table_moves())
        return tuple(out)

    def item_usability(self, item_id: str) -> Usability:
        """Whether a held item can be used now, and why not."""
        items = self.state.inventory if self.state is not None else self.run.items
        if item_id not in items:
            return unusable("You don't have that item.")
        if self.choice is not None:
            return unusable("Finish the current choice first.")
        if self.phase not in (TablePhase.BETTING, TablePhase.PLAYER_TURN):
            return unusable("Not now.")
        result = self.table.item_usability(item_id) if self.table is not None else None
        if result is not None:
            return result
        return USABLE if self.phase == TablePhase.PLAYER_TURN else unusable("Use it on your turn.")

    def can_use_item(self, item_id: str) -> bool:
        return self.item_usability(item_id).ok

    def offer_usability(self, offer: ShopOffer) -> Usability:
        """Whether a shop offer can be bought now, and why not."""
        if offer.sold:
            return unusable("Sold.")
        if self.choice is not None:
            return unusable("Finish the current choice first.")
        if self.phase != TablePhase.BETTING:
            return unusable("The shop is open while betting.")
        result = self.table.offer_usability(offer) if self.table is not None else None
        if result is not None:
            return result
        return USABLE if self.can_bet(self.run.money - self._offer_price(offer)) else unusable("Keep enough chips to bet.")

    def hand_value(self, hand, actor: str = "player") -> int:
        """A hand's total under the rules in force, for `actor` ("player" or "dealer")."""
        return self._value(hand, actor)

    def base_actions(self) -> frozenset[str]:
        """The phase's actions before any item check (tables use this to test
        whether e.g. a double or surrender is allowed)."""
        actions = _ACTIONS_BY_PHASE[self.phase]
        if self.phase == TablePhase.BETTING and self.shop.offers:
            price = self.reroll_price()
            if price is not None and self.can_bet(self.run.money - price):
                actions = actions | {Action.REROLL}
        if self.phase == TablePhase.PLAYER_TURN and len(self._st.player_hand) == 2:
            extra = set()
            if self.config.allow_double and self.run.money >= self.run.current_bet * self._double_cover():
                extra.add(Action.DOUBLE)
            if self.config.allow_surrender:
                extra.add(Action.SURRENDER)
            actions = actions | extra
        return self.table.augment_actions(actions) if self.table is not None else actions

    # -------------------------------------------------------------- internal

    @property
    def _st(self) -> GameState:
        assert self.state is not None
        return self.state

    def _value(self, hand, actor="player") -> int:
        return self.loop.rules.hand_value(hand, self.loop.context(actor))

    def product(self, item_id: str) -> ProductDef | None:
        """The catalog row an item or offer id stands for here (None for classic item plugins)."""
        return self.table.product(item_id) if self.table is not None else catalog_product(item_id)

    def _active_rules(self, st) -> tuple[RuleView, ...]:
        own = self.table.active_rules() if self.table is not None else None
        if own is not None:
            return own
        # Modifiers are only cleared on the next deal; between rounds none apply.
        if st is None and not (self.table is not None and self.table.persistent_rules):
            return ()
        return tuple(RuleView(str(getattr(m, "id", "?")), describe_modifier(m)) for m in self.loop.modifiers.items)

    def _double_multiplier(self) -> int:
        return self.table.double_multiplier() if self.table is not None else 2

    def _double_cover(self) -> int:
        return self.table.double_cover() if self.table is not None else 2

    def _offer_price(self, offer: ShopOffer) -> int:
        return self.table.offer_price(offer.item, offer.price) if self.table is not None else offer.price

    def _table_moves(self) -> tuple[Move, ...]:
        if self.table is None or self.phase == TablePhase.RUN_OVER:
            return ()
        return tuple(replace(m, table=True) for m in self.table.table_moves())

    def check_terminal(self) -> None:
        """Check the table's goal after an out-of-hand transaction (e.g. a refund while betting)."""
        if self.phase == TablePhase.RUN_OVER:
            return
        if self.table is not None and self.choice is None:
            won = self.table.victory(self.run)
            if won:
                self.run_end = RunEndResult(kind="victory", message=won)
                self._end_run()
                return
        self._check_can_bet()

    def _after_table_change(self) -> None:
        """A table action or item changed the round: settle a bust, or check the goal between hands."""
        if self.phase == TablePhase.PLAYER_TURN and self.state is not None:
            if not self._table_cards():
                self._settle_if_player_bust()
        elif self.phase == TablePhase.BETTING:
            self.check_terminal()

    def _available_actions(self) -> frozenset[str]:
        if self.choice is not None:
            return frozenset({Action.CHOOSE, Action.SAVE} | ({Action.CANCEL} if self.choice.cancellable else set()))
        actions = self.base_actions()
        if self.phase == TablePhase.BETTING and Action.USE_ITEM not in actions:
            if any(self.item_usability(i).ok for i, _ in inventory_counts(self.run.items)):
                actions = actions | {Action.USE_ITEM}
        return actions

    def _require(self, action: str) -> None:
        if action not in self._available_actions():
            raise ActionError(f"'{action}' is not allowed during {self.phase.value}")

    def _set_phase(self, phase: TablePhase) -> None:
        prev = self.phase
        self.phase = phase
        self._notify(NoticeKind.PHASE_CHANGED, data={"from": prev.value, "to": phase.value})

    def _notify(self, kind: str, text: str = "", data: dict | None = None) -> None:
        self._publish(Notice(kind=kind, text=text, data=data or {}))
        if kind in {
            NoticeKind.ROUND_STARTED, NoticeKind.ITEM_BOUGHT, NoticeKind.ITEM_RESULT,
            NoticeKind.CHAOS_NARRATION, NoticeKind.CHAOS_POKE_REPLY, NoticeKind.ROUND_SETTLED,
        }:
            self.chaos_memory.record(self.run.round, kind, data or {"text": text})

    def _on_core_event(self, event: Event) -> None:
        notice = self._translator.translate(event)
        self._publish(notice)
        if notice.kind == NoticeKind.DRAW_CARD:
            self.chaos_memory.record(self.run.round, notice.kind, dict(notice.data))

    def _publish(self, notice: Notice) -> None:
        self.run_log.record(self.run.round, notice)
        self._notices.append(notice)
        for fn in list(self._listeners):
            fn(notice)

    def _is_natural(self, hand) -> bool:
        if len(hand) != 2:
            return False
        ranks = {str(card.rank).upper() for card in hand}
        return 'A' in ranks and bool(ranks & {'10', 'J', 'Q', 'K'})

    def _enter_player_turn(self) -> None:
        self._set_phase(TablePhase.PLAYER_TURN)
        if self.table is not None:
            self.table.entered_player()
        self._settle_if_player_bust()

    def _settle_naturals(self) -> bool:
        st = self._st
        player_nat = self._is_natural(st.player_hand)
        dealer_nat = self._is_natural(st.dealer_hand)
        override = self.table.natural_outcome(player_nat, dealer_nat) if self.table is not None else None
        if override is not None:
            self._notify(NoticeKind.PLAYER_BLACKJACK, "Borrowed blackjack!")
            self.state = st.with_phase(GamePhase.RESOLVED)
            self._settle(override)
            return True
        if not (player_nat or dealer_nat):
            return False
        if player_nat:
            self._notify(NoticeKind.PLAYER_BLACKJACK, "♠ BLACKJACK!")
        if dealer_nat:
            self._dealer_blackjack = True
            self._notify(NoticeKind.DEALER_BLACKJACK, "Dealer has blackjack.")
        self.state = st.with_phase(GamePhase.RESOLVED)
        self._settle("push" if player_nat and dealer_nat else "blackjack" if player_nat else "dealer")
        return True

    def _settle_if_player_bust(self) -> bool:
        pv = self._value(self._st.player_hand)
        if not self.loop.rules.is_bust(pv, self.loop.context()):
            return False
        self._notify(NoticeKind.PLAYER_BUST, "💀 BUST!", {"total": pv})
        if self.table is not None and self.table.plays_out_bust():
            self._to_dealer()  # e.g. Bust Insurance: the outcome waits for the dealer
            return True
        self.state = self._st.with_phase(GamePhase.RESOLVED)
        self._settle()
        return True

    def _to_dealer(self) -> None:
        self.state = self._st.with_phase(GamePhase.DEALER_TURN)
        self._set_phase(TablePhase.DEALER_TURN)

    def _settle(self, outcome: str | None = None) -> None:
        st = self._st
        ctx = self.loop.context()
        pv = self._value(st.player_hand)
        dv = self._value(st.dealer_hand, "dealer")
        out = outcome or self.loop.outcome_label(st)
        bet = self.run.current_bet
        delta = settlement_delta(bet, out, blackjack_pays=self.config.blackjack_pays)
        if self.table is not None:
            delta = self.table.settlement(st, out, bet, self._doubled, delta)

        self.run.money += delta
        self.run.items = st.inventory
        update_streak(self.run, out)
        if self.table is not None:
            self.table.after_settle(st, out, self.loop.modifiers, self.run)
            won = self.table.victory(self.run)
            self.run_end = RunEndResult(kind="victory", message=won) if won else None
        else:
            delta -= self._cap_at_target()
            self.run_end = self.run_end_policy.check(self.run)
        self.last_result = RoundResult(
            round=self.run.round,
            outcome=out,
            player_total=pv,
            dealer_total=dv,
            player_bust=self.loop.rules.is_bust(pv, ctx),
            bet=bet,
            delta=delta,
            money_after=self.run.money,
            doubled=self._doubled,
            dealer_blackjack=self._dealer_blackjack,
        )
        self._notify(NoticeKind.ROUND_SETTLED, data={"result": self.last_result})

        if self.run_end is None and not self.can_bet(self.run.money):
            self.run_end = RunEndResult(kind='defeat', message=NO_VALID_BET_MESSAGE)
        if self.run_end is not None:
            self._end_run()
            return
        self.run.round += 1
        self._set_phase(TablePhase.ROUND_OVER)


    def _configure_chaos(self) -> None:
        """Hand the balance profile's chaos settings to the pipeline."""
        pipeline = getattr(self.loop, "pipeline", None)
        if pipeline is None:
            return
        pipeline.rule_params = {k: dict(v) for k, v in self.config.chaos_rule_params.items()}
        disabled = set(self.config.disabled_rules)
        if self.config.rule_pool is not None:  # the mode's pool: every other rule is off
            disabled |= set(self.registry.rule_ids()) - set(self.config.rule_pool)
        pipeline.disabled_rules = frozenset(disabled)
        pipeline.item_params = {k: dict(v) for k, v in self.config.item_params.items()}
        if isinstance(pipeline.llm, OfflineChaosStub):
            pipeline.llm.choices = tuple(self.config.chaos_stub)

    def _roll_shop(self, *, reroll: bool = False) -> ShopState:
        table = self.table
        if table is not None:
            stock = table.roll_shop(reroll)
            if stock is not None:
                return stock
        pinned = table.pinned() if table is not None else ()

        def stocked(item: str) -> bool:
            if table is not None and table.sells(item):
                return item not in pinned and table.stockable(item)
            cls = self.registry.resolve_item(item)
            return cls is not None and (not getattr(cls, "mode", "") or cls.mode == self.config.mode) and (item != 'shield' or self.config.enable_chaos)

        listed = {item: price for item, price in self.config.shop_prices.items() if stocked(item)}
        prices = shop_prices(listed, frozenset(self.config.shop_bankroll_pct), self.run.money,
                             self.config.shop_price_floor)
        # A table's pinned offers (e.g. J-54's Start Experiment) always take a slot.
        extra = tuple(ShopOffer(item, int(self.config.shop_prices[item]))
                      for item in pinned if item in self.config.shop_prices)
        slots = max(0, self.config.shop_slots - len(extra))
        stock = roll_stock(self.shop_seed, self.run.round, prices, slots, reroll=reroll)
        return replace(stock, offers=stock.offers + extra) if extra else stock

    def _fee(self) -> int:
        """Chips the table charges before this round's bet (0 on a plain table)."""
        return self.table.fee(self.run.round) if self.table is not None else 0

    def _describe_offer(self, item_id: str) -> str:
        if self.table is not None and self.table.sells(item_id):
            text = self.table.describe(item_id)
            if text:
                return text
        row = self.product(item_id)
        if row is not None:
            return row.description
        return self.registry.describe_item(item_id) or ITEM_HELP.get(item_id, "")

    def _table_cards(self) -> bool:
        """Let the table react to dealt or drawn cards; True when it ended the hand."""
        if self.table is None or self.state is None:
            return False
        self.state = self.table.after_cards(self._st)
        if not self.table.ends_hand:
            return False
        self.state = self._st.with_phase(GamePhase.RESOLVED)
        self._settle("push")
        return True

    def _cap_at_target(self) -> int:
        """A goal set as a multiple of the start is also the table's ceiling: chips above it are not
        paid (docs/design/CARRIED_CHIPS.zh-CN.md §4). Returns the chips cut."""
        over = self.run.money - self.run.target_money
        if not self.config.target_multiple or self.run.target_money <= 0 or over <= 0:
            return 0
        self.run.money = self.run.target_money
        self._notify(NoticeKind.TABLE_EVENT, f"The table pays up to {self.run.target_money}: "
                     f"{over} chips of this win are not paid.")
        return over

    def _check_can_bet(self) -> None:
        if self.phase == TablePhase.BETTING and not self.can_bet(self.run.money):
            self.run_end = RunEndResult(kind="defeat", message=NO_VALID_BET_MESSAGE)
            self._end_run()

    def _end_run(self) -> None:
        assert self.run_end is not None
        self._notify(
            NoticeKind.RUN_ENDED,
            self.run_end.message,
            {"kind": self.run_end.kind},
        )
        self._set_phase(TablePhase.RUN_OVER)
