"""GameController — one run of Chaos Blackjack, independent of any UI.

Front-ends (CLI, GUI, tests, bots) drive it with a small command set and read
back two things:

* `view()`           -> GameView, an immutable snapshot to render
* `drain_notices()`  -> list[Notice], what happened since the last drain

Flow:  BETTING [-buy*] -place_bet-> [CHAOS -resolve_chaos->] PLAYER_TURN
       -hit/stand/double_down/use_item-> DEALER_TURN -dealer_step*-> ROUND_OVER
       -next_round-> BETTING ... until RUN_OVER.

Naturals are checked when the player turn opens (after chaos, so active
rules count): a player natural pays `blackjack_pays` (3:2), a dealer natural
wins at once, both is a push. Double and surrender are first-decision only.

The shop is open while betting: `buy(item_id)` spends bankroll on one of a
few offers, and the stock rolls again every `shop_refresh_rounds` rounds.

Every step is explicit (e.g. the dealer draws one card per `dealer_step()`),
so a GUI can animate between steps and a CLI can just loop.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import replace

from chaos_blackjack.ai.pipeline import OfflineChaosStub
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.app.economy import (
    RunState,
    bet_limits,
    can_bet,
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
from chaos_blackjack.app.shop import ShopState, needs_restock, roll_stock, rounds_until_restock
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
from chaos_blackjack.core.game_loop import GameLoop
from chaos_blackjack.core.game_state import GamePhase, GameState
from chaos_blackjack.core.run_state import RunSaveData
from chaos_blackjack.core.save_manager import save_game
from chaos_blackjack.events.dispatcher import EventDispatcher
from chaos_blackjack.events.event import Event
from chaos_blackjack.logic.run_end_policy import (
    CompositeRunEndPolicy,
    MoneyBankruptDefeatPolicy,
    MoneyTargetVictoryPolicy,
    RunEndPolicy,
    RunEndResult,
)
from chaos_blackjack.registry import get_registry
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
        save_fn: Callable[[RunSaveData, str], object] = save_game,
    ) -> None:
        from chaos_blackjack import auto_load_plugins

        auto_load_plugins()
        self.config = config or RunConfig()
        self._translator = EventTranslator()
        self._notices: list[Notice] = []
        self._dispatcher = EventDispatcher()
        self._dispatcher.set_default(self._on_core_event)

        factory = loop_factory or (lambda d: GameLoop(dispatcher=d))
        self.loop = factory(self._dispatcher)
        self.loop.initial_inventory = ()
        self._configure_chaos()
        self.rng = random.Random(self.config.seed)
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
            items=(),
        )
        self.state: GameState | None = None
        self.phase = TablePhase.BETTING
        self.last_result: RoundResult | None = None
        self.run_end: RunEndResult | None = None
        self._doubled = False
        self._dealer_blackjack = False
        self.hole_revealed = False
        # Shop rolls (and the offline Chaos AI) are seeded apart from the deal,
        # so buying never changes the cards.
        self.shop_seed = self.config.seed if self.config.seed is not None else random.randrange(2**31)
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
        base = config or RunConfig()
        cfg = replace(
            base,
            start_money=data.start_money,
            target_money=data.target_money,
            objective=data.objective,
            enable_chaos=bool(base.enable_chaos or data.enable_chaos),
        )
        c = cls(cfg, **kwargs)
        c.run.money = data.money
        c.run.round = data.round
        c.run.win_streak = data.win_streak
        c.run.current_bet = data.current_bet
        c.run.items = tuple(data.items)
        c.loop._chaos_actions_this_turn = int(data.chaos_actions_this_turn)
        if data.shop_seed is not None:
            c.shop_seed = data.shop_seed
        c.shop = ShopState.from_dict(data.shop) if data.shop else c._roll_shop()
        c.hole_revealed = data.hole_revealed
        c.run_end = None
        c.phase = TablePhase.BETTING

        if data.game_state is None:
            c._check_can_bet()
            return c

        c.state = snapshot_to_game_state(data.game_state)
        if data.active_modifiers:
            c.loop.modifiers = deserialize_active_modifiers(
                data.active_modifiers, registry=get_registry(), rule_params=cfg.chaos_rule_params,
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
        self.run.current_bet = amount
        self.last_result = None
        self.state = self.loop.new_round(
            seed=self.rng.randint(0, 2**30),
            inventory_override=self.run.items,
        )
        self._doubled = False
        self._dealer_blackjack = False
        self.hole_revealed = False
        self._notify(NoticeKind.ROUND_STARTED, data={"round": self.run.round, "bet": amount})
        if self.config.enable_chaos:
            self._set_phase(TablePhase.CHAOS)
        else:
            self._enter_player_turn()

    def buy(self, item_id: str) -> None:
        """Buy one shop offer. You must keep enough bankroll to place a bet."""
        self._require(Action.BUY)
        offer = self.shop.offer(item_id)
        if offer is None:
            raise ActionError(f"The shop has no {item_id!r} for sale")
        if not self.can_bet(self.run.money - offer.price):
            raise ActionError(f"Not enough chips: {item_id} costs {offer.price} and you must keep enough to bet")
        self.run.money -= offer.price
        self.run.items = self.run.items + (item_id,)
        self.shop = self.shop.with_sold(item_id)
        self._notify(
            NoticeKind.ITEM_BOUGHT,
            f"Bought {item_id} for {offer.price}.",
            {"item": item_id, "price": offer.price},
        )

    def resolve_chaos(self) -> None:
        """Let the Chaos AI act once. May block on an LLM call — GUIs should
        run this off the render thread."""
        self._require(Action.RESOLVE_CHAOS)
        llm = getattr(getattr(self.loop, "pipeline", None), "llm", None)
        if isinstance(llm, OfflineChaosStub):
            llm.reseed(f"{self.shop_seed}:chaos:{self.run.round}")
        self.state = self.loop.maybe_apply_chaos_phase(self._st)
        narration = self.loop.last_chaos_narration
        if narration:
            self._notify(NoticeKind.CHAOS_NARRATION, narration, {"text": narration})
        self._enter_player_turn()

    def hit(self) -> None:
        self._require(Action.HIT)
        self.state = self.loop.draw_for_player(self._st)
        self._settle_if_player_bust()

    def stand(self) -> None:
        self._require(Action.STAND)
        self._to_dealer()

    def double_down(self) -> None:
        """Double the bet, take exactly one card, then stand."""
        self._require(Action.DOUBLE)
        self.run.current_bet *= 2
        self._doubled = True
        self._notify(
            NoticeKind.DOUBLED,
            f"Double down! Bet is now {self.run.current_bet}.",
            {"bet": self.run.current_bet},
        )
        self.state = self.loop.draw_for_player(self._st)
        if not self._settle_if_player_bust():
            self._to_dealer()

    def surrender(self) -> None:
        """Give up the hand and get half the bet back."""
        self._require(Action.SURRENDER)
        refund = self.run.current_bet // 2
        self._notify(NoticeKind.SURRENDERED, f"You surrender. {refund} returned.", {"refund": refund})
        self.state = self._st.with_phase(GamePhase.RESOLVED)
        self._settle("surrender")

    def use_item(self, item_id: str) -> ItemResult:
        self._require(Action.USE_ITEM)
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
        if result.ok:
            # Swapping a card or dropping a rule can push the hand over.
            self._settle_if_player_bust()
        return result

    def dealer_step(self) -> bool:
        """Advance the dealer by one decision. Returns True while the dealer
        still has more to do."""
        self._require(Action.DEALER_STEP)
        ctx = self.loop.context()
        dv = self._value(self._st.dealer_hand)
        if self.loop.rules.is_bust(dv, ctx):
            self._notify(NoticeKind.DEALER_BUSTS, "Dealer busts.", {"total": dv})
        elif dv >= self.config.dealer_stand_on:
            self._notify(NoticeKind.DEALER_STANDS, f"Dealer stands at {dv}.", {"total": dv})
        elif self._st.deck:
            self.state = self.loop.draw_for_dealer(self._st)
            return True
        self.state = self._st.with_phase(GamePhase.RESOLVED)
        self._settle()
        return False

    def finish_dealer(self) -> None:
        while self.phase == TablePhase.DEALER_TURN and self.dealer_step():
            pass

    def next_round(self) -> None:
        self._require(Action.NEXT_ROUND)
        self.state = None
        self._set_phase(TablePhase.BETTING)
        if needs_restock(self.shop, self.run.round, self.config.shop_refresh_rounds):
            self.shop = self._roll_shop()
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
        )
        path = self._save_fn(data, name)
        self._notify(NoticeKind.GAME_SAVED, "Game saved successfully.", {"path": str(path)})
        return data

    # ------------------------------------------------------------ read side

    def bet_limits(self, money: int | None = None) -> tuple[int, int]:
        """Allowed bet range for `money` (default: the current bankroll) under this run's config."""
        m = self.run.money if money is None else money
        return bet_limits(m, min_bet=self.config.min_bet, max_fraction=self.config.max_bet_fraction)

    def can_bet(self, money: int | None = None) -> bool:
        """Whether `money` (default: the bankroll) still allows a minimum bet; shop
        purchases must leave this true."""
        m = self.run.money if money is None else money
        return can_bet(m, min_bet=self.config.min_bet, max_fraction=self.config.max_bet_fraction)

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
            player_cards = tuple(CardView(str(c.rank), c.suit) for c in st.player_hand)
            dealer_cards = tuple(
                CardView(str(c.rank), c.suit, face_up=not (hide_hole and i == 1))
                for i, c in enumerate(st.dealer_hand)
            )
            player_total = self._value(st.player_hand)
            if not hide_hole:
                dealer_total = self._value(st.dealer_hand)
        inventory = st.inventory if st is not None else self.run.items
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
            items=tuple(ItemView(i, n) for i, n in inventory_counts(inventory)),
            shop_offers=tuple(
                ShopOfferView(o.item, o.price, o.sold, not o.sold and self.can_bet(self.run.money - o.price))
                for o in self.shop.offers
            ),
            shop_restock_in=rounds_until_restock(self.shop, self.run.round, self.config.shop_refresh_rounds),
            hole_revealed=self.hole_revealed,
            chaos_enabled=self.config.enable_chaos,
            chaos_budget=st.chaos_budget_remaining if st is not None else self.loop.chaos_budget_initial,
            # Modifiers are only cleared on the next deal; between rounds none apply.
            active_rules=tuple(
                RuleView(str(getattr(m, "id", "?")), describe_modifier(m))
                for m in self.loop.modifiers.items
            ) if st is not None else (),
            narration=self.loop.last_chaos_narration,
            available_actions=self._available_actions(),
            last_result=self.last_result,
            run_end=self.run_end,
        )

    # -------------------------------------------------------------- internal

    @property
    def _st(self) -> GameState:
        assert self.state is not None
        return self.state

    def _value(self, hand) -> int:
        return self.loop.rules.hand_value(hand, self.loop.context())

    def _available_actions(self) -> frozenset[str]:
        actions = _ACTIONS_BY_PHASE[self.phase]
        if self.phase == TablePhase.PLAYER_TURN and len(self._st.player_hand) == 2:
            extra = set()
            if self.config.allow_double and self.run.money >= self.run.current_bet * 2:
                extra.add(Action.DOUBLE)
            if self.config.allow_surrender:
                extra.add(Action.SURRENDER)
            actions = actions | extra
        return actions

    def _require(self, action: str) -> None:
        if action not in self._available_actions():
            raise ActionError(f"'{action}' is not allowed during {self.phase.value}")

    def _set_phase(self, phase: TablePhase) -> None:
        prev = self.phase
        self.phase = phase
        self._notify(NoticeKind.PHASE_CHANGED, data={"from": prev.value, "to": phase.value})

    def _notify(self, kind: str, text: str = "", data: dict | None = None) -> None:
        self._notices.append(Notice(kind=kind, text=text, data=data or {}))

    def _on_core_event(self, event: Event) -> None:
        self._notices.append(self._translator.translate(event))

    def _is_natural(self, hand) -> bool:
        if len(hand) != 2:
            return False
        v = self._value(hand)
        return v == 21 and not self.loop.rules.is_bust(v, self.loop.context())

    def _enter_player_turn(self) -> None:
        self._set_phase(TablePhase.PLAYER_TURN)
        st = self._st
        player_nat = self._is_natural(st.player_hand)
        dealer_nat = self._is_natural(st.dealer_hand)
        if not (player_nat or dealer_nat):
            return
        if player_nat:
            self._notify(NoticeKind.PLAYER_BLACKJACK, "♠ BLACKJACK!")
        if dealer_nat:
            self._dealer_blackjack = True
            self._notify(NoticeKind.DEALER_BLACKJACK, "Dealer has blackjack.")
        self.state = st.with_phase(GamePhase.RESOLVED)
        self._settle("push" if player_nat and dealer_nat else "blackjack" if player_nat else "dealer")

    def _settle_if_player_bust(self) -> bool:
        pv = self._value(self._st.player_hand)
        if not self.loop.rules.is_bust(pv, self.loop.context()):
            return False
        self._notify(NoticeKind.PLAYER_BUST, "💀 BUST!", {"total": pv})
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
        dv = self._value(st.dealer_hand)
        out = outcome or self.loop.outcome_label(st)
        bet = self.run.current_bet
        delta = settlement_delta(bet, out, blackjack_pays=self.config.blackjack_pays)

        self.run.money += delta
        self.run.items = st.inventory
        update_streak(self.run, out)
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

        self.run_end = self.run_end_policy.check(self.run)
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
        pipeline.disabled_rules = frozenset(self.config.disabled_rules)
        if isinstance(pipeline.llm, OfflineChaosStub):
            pipeline.llm.choices = tuple(self.config.chaos_stub)

    def _roll_shop(self) -> ShopState:
        return roll_stock(self.shop_seed, self.run.round, self.config.shop_prices, self.config.shop_slots)

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
