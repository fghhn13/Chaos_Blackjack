"""Poker Head's build table: cores, permanents, consumables and a money ledger.

The table coordinates; it holds no per-product logic:

* catalog.py   — the 41 products (names, kinds, phases); numbers from the profile
* ownership.py — Holdings (bought consumables), Loadout (core, slots), Ledger (positions)
* effects.py   — passive hooks of cores, permanents and this round's preparations
* items.py     — one handler per consumable (usability, targets, apply)
* evaluation.py — the actor-aware hand values every check uses
* public.py    — the snapshot a player may see; parts.py draws it

Goal: net assets (cash + open principal − debt owed) reach the target.
Questions (opening core, replacing a permanent, an item's target) go through
`GameController.ask` and change nothing until answered. The deal of each round
is fixed before betting (Fate Forecast shows part of it), from a stream seeded
by the run seed and the round, so shopping, rerolling or loading never changes
the cards. See docs/design/ITEM_ARCHITECTURE.md.
"""

from __future__ import annotations

import base64
import json
import math
import random
import zlib
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from chaos_blackjack.app.choice import USABLE, Choice, ChoiceOption, Move, Usability, unusable
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.products import ProductDef, product as catalog_product
from chaos_blackjack.app.shop import ShopOffer, ShopState
from chaos_blackjack.app.table_mechanics import TableMechanics, register_table
from chaos_blackjack.app.view import Action, RuleView, TablePhase
from chaos_blackjack.contracts.items import ItemResult
from chaos_blackjack.core.game_loop import _standard_deck
from chaos_blackjack.core.game_state import Card, Rank
from chaos_blackjack.poker_head.catalog import COMMON, CORES, PERMANENTS, PRODUCTS, SHOP_IDS, canonical, product
from chaos_blackjack.poker_head.context import BuildContext
from chaos_blackjack.poker_head.effects import Effect, Settlement, build_effect
from chaos_blackjack.poker_head.director import STAGE_NAMES, Director, from_legacy
from chaos_blackjack.poker_head.environment import EnvRule
from chaos_blackjack.poker_head.evaluation import BuildRules
from chaos_blackjack.poker_head.items import build_handler
from chaos_blackjack.poker_head.ownership import Holding, Holdings, Ledger, Loadout
from chaos_blackjack.poker_head.public import EntryView, PokerHeadPublic, PositionView

SAVE_VERSION = 2
CASH = "cash"  # the opening invitation's "no core, extra chips" option
DISCARD = "ph_discard"  # table action: drop an equipped permanent (it can be offered again)


def _action_error(text: str):
    from chaos_blackjack.app.controller import ActionError

    return ActionError(text)


@dataclass
class RoundState:
    """What lasts until this round settles."""

    preparations: list[str] = field(default_factory=list)  # consumables prepared (effects.py)
    used: list[str] = field(default_factory=list)          # once-per-round permanents already used
    shown: list[str] = field(default_factory=list)         # a revealed next rank
    forecast: list[str] = field(default_factory=list)      # Fate Forecast's cards
    forecast_changed: bool = False


@dataclass
class ShopCounters:
    stock_round: int = 0
    roll_number: int = 0        # rolls of this stock (seeds each roll)
    paid_used: int = 0
    free_used: int = 0
    extra_offer: dict | None = None   # Private Account's extra slot of this stock


class PokerHeadTable(TableMechanics):
    id = "poker_head"
    persistent_rules = True
    uses_chaos_budget = False  # the director, not the Chaos AI, changes the rules here
    environment_rules = True

    @classmethod
    def enabled(cls, config):
        return config.mode_settings.get("chaos.build_version") == 1

    @classmethod
    def goal(cls, config):
        return f"Reach {config.target_money} net assets"

    def __init__(self, config, seed, notify):
        super().__init__(config, seed, notify)
        self.ctx = BuildContext(self)
        self.holdings = Holdings()
        self.loadout = Loadout()
        self.ledger = Ledger()
        self.round = RoundState()
        self.shop_counters = ShopCounters()
        self.claim: dict | None = None       # Recovery Receipt: {"round", "refund"}
        self.ace_pending = False              # Comeback Ace arms the next opening card
        self.environment: list[EnvRule] = []   # the dealer's environment rules (environment.py)
        # How rules left the table: {"type", "signature", "cause", "round"} (the director's cooldowns read it).
        self.env_history: list[dict] = []
        self._finance_cash = 0                 # money positions pay out after the hand (settlement -> after_settle)
        self.acted_round = 0                   # the round the director last acted in (once per round)
        self.prepared: tuple[Card, ...] | None = None   # this round's deal (private)
        self.prepared_round = 0
        self.last_settled = 0

    # --- setup ----------------------------------------------------------------

    def bind(self, controller):
        self.c = controller
        controller.loop.rules = BuildRules(self, controller.loop.rules)
        # The environment comes from the offline director (never an LLM, never the registry's Chaos rules).
        settings = {k[len("chaos."):]: v for k, v in self.config.mode_settings.items() if k.startswith("chaos.")}
        self.director = Director(settings, self.seed, self.setting("rule_slots"))

    def setting(self, key):
        value = self.config.mode_settings["chaos." + key]
        if key in ("approx_values", "min_bets"):
            return tuple(int(x) for x in str(value).split(","))
        return value

    def param(self, item_id, key):
        return self.config.item_params[canonical(item_id)][key]

    def message(self, text, kind=NoticeKind.ITEM_RESULT):
        self.notify(kind, text, {"text": text, "table": self.id, "ok": True})

    def effects(self) -> list[Effect]:
        """Active passive effects: core, permanents in slot order, then this round's preparations."""
        return [build_effect(self.ctx, i) for i in (*self.loadout.active(), *self.round.preparations)]

    def product(self, item_id: str) -> ProductDef | None:
        return catalog_product(canonical(item_id))

    # --- run ------------------------------------------------------------------

    def start(self, run):
        run.objective = "net_assets"
        for item_id in run.items:  # starter items from meta progression
            self.holdings.add(item_id, 0)
        gift = self.holdings.add("ph_gift", 0, self._core_offer("ph_gift"))
        self._sync_items()
        self._ask_opening(gift)

    def _core_offer(self, source: str) -> tuple[str, ...]:
        pool = [x for x in CORES if x != self.loadout.core]
        return tuple(random.Random(f"{self.seed}:choice:{self.holdings.sequence + 1}").sample(pool, 2))

    def _ask_opening(self, gift: Holding) -> None:
        options = tuple(ChoiceOption(c, PRODUCTS[c].name, PRODUCTS[c].description) for c in gift.choices)
        options += (ChoiceOption(CASH, f"Take {self.setting('decline_cash')} chips",
                                 "Play the whole run without a core."),)
        self.c.ask(Choice("opening", "The dealer's invitation: choose your core, or take the chips.",
                          options, cancellable=False, payload={"holding": gift.uid}))

    def summary(self):
        return [f"Reach {self.config.target_money} net assets: cash, plus money invested, minus what you owe. "
                "Choose a core, build in three slots, and watch the minimum bet rise."]

    def min_bet(self, round_no):
        levels = self.setting("min_bets")
        index = (round_no - 1) // self.setting("bet_step_rounds")
        if index < len(levels):
            return levels[index]
        return levels[-1] + (index - len(levels) + 1) * self.setting("bet_step_add")

    def goal_progress(self, run):
        return ("Net assets", self.ledger.net_assets(run.money), run.target_money)

    def net_assets(self, run=None) -> int:
        return self.ledger.net_assets((run or self.c.run).money)

    def victory(self, run):
        if self.c.choice is not None or self.ledger.net_assets(run.money) < run.target_money:
            return None
        # Settle at cost: open principal comes back, owed repayments are paid, no unearned interest.
        run.money = self.ledger.net_assets(run.money)
        self.ledger.close_all()
        return f"Your net assets reached {run.target_money}. Poker Head concedes the table."

    def info(self, run):
        core = PRODUCTS[self.loadout.core].name if self.loadout.core else "No core" if self.loadout.no_core else "Not chosen"
        rows = [("Net assets", f"{self.net_assets(run)}/{run.target_money}"), ("Cash", str(run.money)),
                ("Invested", str(self.ledger.invested)), ("Debt", str(self.ledger.debt)), ("Core", core),
                ("Build", f"{len(self.loadout.equipped)}/{self.setting('build_slots')}"),
                ("Minimum bet", str(self.min_bet(run.round)))]
        if self.round.forecast:
            rows.append(("Forecast", " ".join(self.round.forecast) + (" (deck changed)" if self.round.forecast_changed else "")))
        if self.round.shown:
            rows.append(("Next rank", " ".join(self.round.shown)))
        return tuple(rows)

    def public(self) -> PokerHeadPublic:
        def entry(item_id):
            p = PRODUCTS[canonical(item_id)]
            return EntryView(p.id, p.name, p.description)

        run = self.c.run
        stage = self.director.stage(run.round)
        return PokerHeadPublic(
            core=entry(self.loadout.core) if self.loadout.core else None, no_core=self.loadout.no_core,
            slots=self.setting("build_slots"), equipped=tuple(entry(x) for x in self.loadout.equipped),
            cash=run.money, invested=self.ledger.invested, debt=self.ledger.debt,
            net_assets=self.net_assets(run), target=run.target_money,
            positions=tuple(PositionView(p.id, PRODUCTS[p.id].name, p.principal, p.debt, p.remaining, p.wins)
                            for p in self.ledger.positions),
            preparations=tuple(entry(x) for x in self.round.preparations),
            forecast=tuple(self.round.forecast), forecast_changed=self.round.forecast_changed,
            next_rank=" ".join(self.round.shown),
            claim_refund=self.claim["refund"] if self.claim else 0, claim_round=self.claim["round"] if self.claim else 0,
            ace_armed=self.ace_pending, min_bet=self.min_bet(run.round), rule_slots=self.setting("rule_slots"),
            dealer_stage=STAGE_NAMES[min(stage.index, len(STAGE_NAMES) - 1)], dealer_slots=stage.slots)

    # --- shop -------------------------------------------------------------------

    def sells(self, item_id):
        return item_id in SHOP_IDS

    def describe(self, item_id):
        p = product(item_id)
        return p.description if p else ""

    @property
    def unlock_all(self) -> bool:
        """Testing switch (mode.chaos.unlock_all): every product on the shelf, money products without a core."""
        return bool(self.config.mode_settings.get("chaos.unlock_all", 0))

    def _finance_unlocked(self) -> bool:
        return self.unlock_all or any(e.unlocks_finance for e in self.effects())

    def _stock_blocker(self, item_id: str) -> str:
        """Why an offer may not be stocked or bought now ("" = it may)."""
        p = PRODUCTS.get(item_id)
        if p is None or item_id not in SHOP_IDS:
            return "Not sold at this table."
        if p.kind == "permanent" and self.loadout.has(item_id):
            return "Already equipped."
        if p.kind == "finance":
            if not self._finance_unlocked():
                return "Needs the Private Account core."
            if item_id == "ph_loan" and self.ledger.has("ph_loan"):
                return "One loan at a time."
        if item_id == "ph_change" and self.loadout.no_core:
            return "You took the opening chips: no core this run."
        return ""

    def stockable(self, item_id):
        return not self._stock_blocker(item_id)

    def _price_factors(self, item_id: str) -> list[tuple[Fraction, str]]:
        """(factor, source name) of everything changing an offer's price now."""
        p = PRODUCTS.get(item_id)
        if p is None:
            return []
        out = [(r.price_factor(p.kind), r.title) for r in self.env_rules()]  # the dealer's first
        out += [(e.price_factor(p.kind), PRODUCTS[e.id].name) for e in self.effects()]
        return [(f, name) for f, name in out if f != 1]

    def offer_price(self, item_id, price):
        """Base price × markups × discounts, rounded up once, at least one chip (§3.8)."""
        factor = Fraction(1)
        for f, _ in self._price_factors(item_id):
            factor *= f
        return price if factor == 1 else max(1, math.ceil(price * factor))

    def offer_note(self, item_id):
        # float(): Fraction supports format specs only from Python 3.12.
        return ", ".join(f"{'+' if f > 1 else '−'}{float(abs(f - 1) * 100):g}% {name}"
                         for f, name in self._price_factors(item_id))

    def offer_usability(self, offer):
        blocker = self._stock_blocker(offer.item)
        if blocker:
            return unusable(blocker)
        if offer.item == "ph_loan":  # borrowing adds cash
            return USABLE
        if not self.c.can_bet(self.c.run.money - self.offer_price(offer.item, offer.price)):
            return unusable("Keep enough chips to bet.")
        return USABLE

    def _shop_slots(self) -> int:
        slots = self.config.shop_slots
        for e in self.effects():
            slots = e.shop_slots(slots)
        return slots

    def roll_shop(self, reroll=False):
        r = self.c.run.round
        if self.c.choice is not None and self.c.choice.kind == "opening":
            return ShopState(r, ())
        sc = self.shop_counters
        if not reroll and sc.stock_round != r:
            self.shop_counters = sc = ShopCounters(stock_round=r)
        if self.unlock_all:  # every product, grouped, cheapest first; blocked ones show why
            order = {"consumable": 0, "permanent": 1, "special": 2}
            ids = sorted((x for x in SHOP_IDS if x in self.config.shop_prices),
                         key=lambda x: (order[PRODUCTS[x].to_def().group], self.config.shop_prices[x], x))
            return ShopState(sc.stock_round, tuple(ShopOffer(x, self.config.shop_prices[x]) for x in ids))
        rng = random.Random(f"{self.seed}:shop:{sc.stock_round}:{sc.roll_number}")
        pool = [x for x in SHOP_IDS if self.stockable(x) and x in self.config.shop_prices]
        picked: list[str] = []
        count = self._shop_slots()
        common = [x for x in pool if x in COMMON]
        if common:
            picked.append(rng.choice(common))
        chance = (self.setting("permanent_early") if sc.stock_round <= 3 else
                  self.setting("permanent_middle") if sc.stock_round <= 6 else self.setting("permanent_late"))
        style = PRODUCTS[self.loadout.core].style if self.loadout.core else ""
        while len(picked) < count:
            remaining = [x for x in pool if x not in picked]
            if not remaining:
                break
            permanent = rng.random() < chance
            candidates = [x for x in remaining if (PRODUCTS[x].kind == "permanent") == permanent] or remaining
            weights = [self.setting("style_weight") if PRODUCTS[x].style == style else 1 for x in candidates]
            picked.append(rng.choices(candidates, weights=weights)[0])
        offers = tuple(ShopOffer(x, self.config.shop_prices[x]) for x in picked)
        sc.extra_offer = offers[-1].to_dict() if len(offers) > self.config.shop_slots else None
        return ShopState(sc.stock_round, offers, rerolled=bool(sc.paid_used))

    def _adjust_extra_slot(self) -> None:
        """A core change gives or takes Private Account's extra slot on the current stock."""
        if self.unlock_all:
            return  # the whole catalog is on the shelf already
        sc, shop = self.shop_counters, self.c.shop
        base = shop.offers[:self.config.shop_slots]
        if self._shop_slots() > self.config.shop_slots:
            if sc.extra_offer is None:
                taken = {o.item for o in base}
                pool = [x for x in SHOP_IDS if self.stockable(x) and x not in taken and x in self.config.shop_prices]
                if pool:
                    item = random.Random(f"{self.seed}:extra:{sc.stock_round}:{sc.roll_number}").choice(pool)
                    sc.extra_offer = ShopOffer(item, self.config.shop_prices[item]).to_dict()
            if sc.extra_offer:
                base += (ShopOffer.from_dict(sc.extra_offer),)
        self.c.shop = replace(shop, offers=base)

    def reroll_price(self, price):
        if self.unlock_all:
            return None  # the whole catalog is already on the shelf
        sc = self.shop_counters
        free = 0
        for e in self.effects():
            free = e.free_rerolls(free)
        if sc.free_used < free:
            return 0
        return self.config.shop_reroll_price if sc.paid_used == 0 else None

    def rerolled(self, price):
        sc = self.shop_counters
        if price == 0:
            sc.free_used += 1
        else:
            sc.paid_used += 1
        sc.roll_number += 1
        return True

    def purchase(self, item_id, option=""):
        c = self.c
        p = PRODUCTS.get(item_id)
        if p is None:
            return False
        offer = c.shop.offer(item_id)
        if offer is None:
            raise _action_error(f"The shop has no {p.name} for sale.")
        usable = c.offer_usability(offer)
        if not usable:
            raise _action_error(usable.reason)
        if p.kind == "permanent" and len(self.loadout.equipped) >= self.setting("build_slots"):
            if not option:
                c.ask(Choice("replace", f"Your build slots are full. Replace which permanent with {p.name}?",
                             tuple(ChoiceOption(x, PRODUCTS[x].name, PRODUCTS[x].description)
                                   for x in self.loadout.equipped),
                             payload={"item": item_id}))
                return True
            if option not in self.loadout.equipped:
                raise _action_error("Choose an equipped permanent to replace.")
        elif option:
            raise _action_error("A replacement is only needed when every build slot is full.")
        price = self.offer_price(item_id, offer.price)
        c.run.money -= price
        c.shop = c.shop.with_sold(item_id)
        sc = self.shop_counters
        if sc.extra_offer and sc.extra_offer["item"] == item_id:
            sc.extra_offer["sold"] = True
        if p.kind == "permanent":
            if option:
                build_effect(self.ctx, option).removed()
                self.loadout.equipped.remove(option)
            self.loadout.equipped.append(item_id)
        elif p.kind == "item":
            self.holdings.add(item_id, price, self._core_offer(item_id) if item_id == "ph_change" else ())
            self._sync_items()
        else:
            params = self.config.item_params[item_id]
            if item_id == "ph_loan":
                self.ledger.open(item_id, 0, params["repay"], params["rounds"])
                c.run.money += params["advance"]
            else:
                self.ledger.open(item_id, price, 0, params["rounds"])
        verb = "Borrowed with" if item_id == "ph_loan" else "Bought"
        text = f"{verb} {p.name}" + (f" for {price} chips." if item_id != "ph_loan" else ".")
        if option:
            text += f" It replaces {PRODUCTS[option].name}."
        self.notify(NoticeKind.ITEM_BOUGHT, text, {"item": item_id, "price": price, "table": True})
        return True

    # --- choices ------------------------------------------------------------------------

    def resolve_choice(self, choice, option):
        if choice.kind == "replace":
            self.purchase(choice.payload["item"], option)
        elif choice.kind == "discard":
            self.discard_permanent(option)
        elif choice.kind == "opening":
            self._open_with(choice.payload["holding"], option)
        elif choice.kind == "target":
            holding = self.holdings.get(choice.payload["holding"])
            if holding is None:
                raise _action_error("That item is gone.")
            result = self._use(holding, option)
            if not result.ok:
                raise _action_error(result.message)
            self.message(result.message)
        else:
            raise _action_error(f"Unknown choice {choice.kind!r}")

    def _open_with(self, uid: str, option: str) -> None:
        gift = self.holdings.get(uid)
        if option == CASH:
            self.loadout.no_core = True
            self.c.run.money += self.setting("decline_cash")
            text = f"You took {self.setting('decline_cash')} chips and play without a core."
        else:
            self.loadout.core = option
            text = f"Core chosen: {PRODUCTS[option].name}."
        if gift is not None:
            self.discard(gift)
        self.c.shop = self.roll_shop()
        self.message(text)
        self.director_turn()  # round 1's environment, once the core is chosen

    def discard_permanent(self, item_id: str) -> None:
        """Drop an equipped permanent: what it held is lost, and the shop may stock it again."""
        if item_id not in self.loadout.equipped:
            raise _action_error("That permanent is not equipped.")
        build_effect(self.ctx, item_id).removed()
        self.loadout.equipped.remove(item_id)
        self.message(f"Discarded {PRODUCTS[item_id].name}.")

    def set_core(self, core: str) -> None:
        self.loadout.core = core
        self._adjust_extra_slot()

    # --- items -------------------------------------------------------------------------

    def _sync_items(self) -> None:
        """run.items (and the round's inventory) mirror the holdings."""
        self.c.run.items = self.holdings.ids()
        if self.c.state is not None:
            self.c.state = self.c.state.with_inventory(self.c.run.items)

    def discard(self, holding: Holding) -> None:
        self.holdings.remove(holding.uid)
        self._sync_items()

    def _ban(self) -> EnvRule | None:
        return next((r for r in self.env_rules() if r.bans_items), None)

    def item_usability(self, item_id):
        p = product(item_id)
        if p is None:
            return None
        if p.kind != "item":
            return unusable("Not a usable item.")
        holding = self.holdings.first(item_id)
        if holding is None:
            return unusable("You don't have that item.")
        phase = {TablePhase.BETTING: "B", TablePhase.PLAYER_TURN: "P"}.get(self.c.phase, "")
        if phase not in p.phases or not phase:
            return unusable(f"{p.to_def().when} only.")
        if p.id == "ph_gift":
            return unusable("Answered at the start of the run.")
        if self._ban() is not None:
            return USABLE  # spending it only lifts the ban: no target or other condition (§3.7)
        return build_handler(self.ctx, p.id).usability(holding)

    def item_note(self, item_id):
        p = product(item_id)
        if p is None or p.kind != "item" or self._ban() is None:
            return ""
        return "Item Ban: using it only lifts the ban, with no effect."

    def use_item(self, item_id, target=""):
        p = product(item_id)
        if p is None:
            return None
        holding = self.holdings.first(item_id)
        usable = self.c.item_usability(item_id)
        if holding is None or not usable:
            return ItemResult(False, usable.reason or "You don't have that item.")
        ban = self._ban()
        if ban is not None:
            self.discard(holding)
            self.lift_rule(ban, "sacrificed")
            return ItemResult(True, f"{ban.title} lifted: {p.name} was spent with no effect.")
        handler = build_handler(self.ctx, p.id)
        targets = handler.targets(holding)
        if targets and not target:
            self.c.ask(Choice("target", handler.prompt(), targets, payload={"holding": holding.uid}))
            return ItemResult(True, "")
        return self._use(holding, target)

    def _use(self, holding: Holding, target: str) -> ItemResult:
        p = product(holding.id)
        handler = build_handler(self.ctx, p.id)
        usable = handler.usability(holding)
        if not usable:
            return ItemResult(False, usable.reason)
        targets = handler.targets(holding)
        if targets and target not in {t.id for t in targets}:
            return ItemResult(False, "Choose one of the offered targets.")
        if not targets and target:
            return ItemResult(False, f"{p.name} needs no target.")
        text = handler.apply(holding, target)
        if self.holdings.get(holding.uid) is not None:
            self.discard(holding)
        handler.after()
        self._refresh_turn()
        return ItemResult(True, text)

    def _refresh_turn(self) -> None:
        """A card or item changed your turn: per-turn effects (Open Audit) look again."""
        if self.c.phase == TablePhase.PLAYER_TURN and self.c.state is not None:
            for e in self.effects():
                e.player_turn()

    def deck_changed(self) -> None:
        """A card effect moved the deck: the forecast and a revealed rank are out of date."""
        if self.round.forecast:
            self.round.forecast_changed = True
        self.round.shown = []

    # --- own actions ----------------------------------------------------------------------

    def table_moves(self):
        if self.c.choice is not None:
            return ()
        moves = [m for e in self.effects() for m in e.table_moves()]
        if self.c.phase == TablePhase.BETTING:  # the bag lists these next to each permanent
            moves += [Move(DISCARD, x, f"Discard {PRODUCTS[x].name}", listed=False) for x in self.loadout.equipped]
        return tuple(moves)

    def perform(self, action, arg):
        if action == DISCARD:
            p = PRODUCTS[arg]
            self.c.ask(Choice("discard", f"Discard {p.name}? Its build slot is freed and it may be offered in the "
                              "shop again. Nothing is refunded.", (ChoiceOption(arg, f"Discard {p.name}", p.description),),
                              payload={"item": arg}))
            return None
        for e in self.effects():
            if e.perform(action):
                self._refresh_turn()
                return None
        raise _action_error(f"Unknown action {action!r}")

    def augment_actions(self, actions):
        if self.c.phase != TablePhase.PLAYER_TURN:
            return actions
        out = set(actions)
        for e in self.effects():
            e.actions(out)
        return frozenset(out)

    def double_multiplier(self):
        multiplier = 2
        for e in self.effects():
            multiplier = e.double_multiplier(multiplier)
        return multiplier

    def surrender_loss(self, bet: int) -> int:
        rate = self.setting("base_surrender_pct")
        for e in self.effects():
            rate = e.surrender_rate(rate)
        return math.ceil(bet * rate / 100)

    def surrender_refund(self, bet):
        return bet - self.surrender_loss(bet)

    # --- Chaos rules ---------------------------------------------------------------------

    def _suppressed(self) -> bool:
        return any(e.suppresses_chaos for e in self.effects())

    def lift_rule(self, rule: EnvRule, cause: str) -> None:
        """Take a rule off the table (removed, sacrificed, expired, replaced) and remember how."""
        self.environment = [r for r in self.environment if r is not rule]
        self.env_history.append({"type": rule.type, "signature": rule.signature, "cause": cause,
                                 "round": self.c.run.round})

    def hidden_player_cards(self):
        """Face-Down Card: the second opening card until you stand (§3.9)."""
        state = self.c.state
        if state is None or len(state.player_hand) < 2 or not any(r.hides_second_card for r in self.env_rules()):
            return frozenset()
        return frozenset({1})

    def env_rules(self) -> tuple[EnvRule, ...]:
        """The environment rules in force this round (none while Silence Seal is prepared)."""
        return () if self._suppressed() else tuple(self.environment)

    def rule_views(self):
        """Every rule on the table (silenced ones too), for Clause Removal's choice."""
        return tuple(_RuleView(r.type, r.title, r.text()) for r in self.environment)

    def active_rules(self):
        silenced = self._suppressed()
        return tuple(RuleView(r.type, r.text(), r.title, r.effect_text(), r.scope, r.remaining, r.removal_text(),
                              silenced, r.icon) for r in self.environment)

    def remove_rule(self, rule_type: str) -> str:
        """Clause Removal: take a rule off for good (its type then cools down)."""
        rule = next(r for r in self.environment if r.type == rule_type)
        self.lift_rule(rule, "removed")
        return rule.title

    def should_chaos(self):
        return False  # the director acts before betting (director.py); nothing changes after the deal

    # --- the director -----------------------------------------------------------------------

    def director_turn(self) -> None:
        """This round's one environment action, before shopping and betting (§2.1, §7)."""
        round_no = self.c.run.round
        if self.acted_round == round_no or (self.c.choice is not None and self.c.choice.kind == "opening"):
            return
        self.acted_round = round_no
        action = self.director.decide(round_no, list(self.environment), self.env_history)
        if action.kind == "calm":
            self._announce("Poker Head leaves the table as it is this round.", "calm")
            return
        rule = action.rule
        if action.kind == "replaced":
            self.lift_rule(action.replaced, "replaced")
            text = f"Poker Head replaces {action.replaced.title} with {rule.title}."
        else:
            text = f"Poker Head changes the table: {rule.title}."
        self.environment.append(rule)
        self._announce(f"{text} {rule.effect_text()} {rule.duration_text()}", action.kind, rule)

    def _announce(self, text: str, action: str, rule: EnvRule | None = None) -> None:
        """A rule change is a Chaos rule notice (the host reacts, the table glitches); a calm round is a table event."""
        data = {"text": text, "table": self.id, "environment": action}
        if rule is None:
            self.notify(NoticeKind.TABLE_EVENT, text, data)
            return
        self.notify(NoticeKind.RULE_MODIFIER_APPLIED, text,
                    {**data, "rule": rule.type, "rule_id": rule.icon, "rule_name": rule.title})

    def _age_rules(self) -> None:
        """A round settled: every rule is one round older; timed rules that ran out leave."""
        kept = []
        for rule in self.environment:
            older = rule.aged()
            if older.expired:
                self.env_history.append({"type": rule.type, "signature": rule.signature, "cause": "expired",
                                         "round": self.c.run.round})
                self.message(f"{rule.title} has ended.", NoticeKind.TABLE_EVENT)
            else:
                kept.append(older)
        self.environment = kept

    # --- round ---------------------------------------------------------------------------

    def entered_betting(self):
        self.director_turn()

    def before_bet(self):
        return self.prepare_deck()

    def prepare_deck(self) -> tuple[Card, ...]:
        """This round's deal, fixed before betting so a forecast holds whatever you buy."""
        if self.prepared is None or self.prepared_round != self.c.run.round:
            cards = _standard_deck()
            random.Random(f"{self.seed}:deal:{self.c.run.round}").shuffle(cards)
            self.prepared, self.prepared_round = tuple(cards), self.c.run.round
        return self.prepared

    def forecast_cards(self) -> tuple[Card, ...]:
        """The first two cards left after the four-card opening deal."""
        return self.prepare_deck()[4:6]

    def before_naturals(self, state):
        self.round.used, self.round.shown = [], []
        for e in self.effects():
            state = e.opening(state)
        return state

    def natural_outcome(self, player, dealer):
        for e in self.effects():
            outcome = e.natural(player, dealer)
            if outcome is not None:
                return outcome
        return None

    def entered_player(self):
        self._refresh_turn()

    def settlement(self, state, outcome, bet, doubled, delta):
        """The hand's cash result. Money positions mature in the same pass, so a Withdrawal Limit caps
        the round's profit once, across the hand and every matured investment (§3.6)."""
        if outcome == "surrender":
            delta = -self.surrender_loss(bet)
        s = Settlement(outcome, bet, doubled, delta, len(state.player_hand),
                       self.ctx.value(state.player_hand), self.c.run.round)
        for e in self.effects():
            e.settle(s)
        hand = s.hand()
        matured = []
        if self.last_settled != self.c.run.round:
            self.last_settled = self.c.run.round
            matured = self._mature(won=outcome in ("player", "blackjack"))
        cap = next((r for r in self.env_rules() if r.profit_cap is not None), None)
        if cap is not None:
            hand, matured = self._cap_profit(cap, hand, matured)
        self._finance_cash = 0
        for p, back, profit in matured:
            self._finance_cash += back + profit
            verb = "repaid" if p.id == "ph_loan" else "matured"
            self.message(f"{PRODUCTS[p.id].name} {verb}: {back + profit:+d} chips.", NoticeKind.TABLE_EVENT)
        return hand + s.extra

    def _mature(self, won: bool) -> list[tuple[Any, int, int]]:
        """(position, money back that is not profit, profit) of each position maturing this round."""
        out = []
        for p in self.ledger.advance(won=won):
            params = self.config.item_params[p.id]
            if p.id == "ph_loan":
                out.append((p, -p.debt, 0))
                continue
            if p.id == "ph_bond":
                payout = params["payout"] if p.wins >= params["wins"] else params["failure"]
            elif p.id == "ph_stock":
                lucky = random.Random(f"{self.seed}:stock:{p.uid}").random() < params["probability"]
                payout = params["payout"] if lucky else 0
            else:
                payout = params["payout"]
            profit = payout - p.principal
            for e in self.effects():
                profit = e.investment_profit(profit)
            # A loss eats into the principal; only a gain is profit.
            out.append((p, p.principal + min(0, profit), max(0, profit)))
        return out

    def _cap_profit(self, rule: EnvRule, hand: int, matured):
        """Keep at most the cap of this round's positive profit; cut the hand's profit first."""
        pool = max(0, hand) + sum(profit for _, _, profit in matured)
        excess = max(0, pool - rule.profit_cap)
        if not excess:
            return hand, matured
        self.message(f"{rule.title}: {excess} chips of profit are lost.", NoticeKind.TABLE_EVENT)
        cut = min(excess, max(0, hand))
        hand, excess = hand - cut, excess - cut
        capped = []
        for p, back, profit in matured:
            cut = min(excess, profit)
            capped.append((p, back, profit - cut))
            excess -= cut
        return hand, capped

    def after_settle(self, state, outcome, modifiers, run):
        run.money += self._finance_cash
        self._finance_cash = 0
        self.round = RoundState(used=self.round.used)
        self._age_rules()

    # --- save ------------------------------------------------------------------------------

    def to_dict(self):
        data = {
            "kind": self.id, "version": SAVE_VERSION,
            "loadout": self.loadout.to_dict(), "holdings": self.holdings.to_dict(), "ledger": self.ledger.to_dict(),
            "round": {"preparations": list(self.round.preparations), "used": list(self.round.used),
                      "shown": list(self.round.shown), "forecast": list(self.round.forecast),
                      "forecast_changed": self.round.forecast_changed},
            "shop": {"stock_round": self.shop_counters.stock_round, "roll_number": self.shop_counters.roll_number,
                     "paid_used": self.shop_counters.paid_used, "free_used": self.shop_counters.free_used,
                     "extra_offer": dict(self.shop_counters.extra_offer) if self.shop_counters.extra_offer else None},
            "claim": dict(self.claim) if self.claim else None, "ace_pending": self.ace_pending,
            "prepared_round": self.prepared_round, "acted_round": self.acted_round,
            "environment": [r.to_dict() for r in self.environment],
            "env_history": [dict(x) for x in self.env_history],
            "last_settled": self.last_settled,
        }
        if self.prepared:
            # The deal is private: packed like the agent run file's deck order.
            cards = [[str(x.rank), x.suit] for x in self.prepared]
            data["prepared_packed"] = base64.b64encode(zlib.compress(json.dumps(cards).encode())).decode()
        return data

    def restore(self, data):
        if data.get("kind") != self.id or data.get("version") not in (1, SAVE_VERSION):
            raise ValueError("Unsupported Poker Head build save.")
        if data["version"] == 1:
            data = _upgrade_v1(data)
        self.loadout = Loadout.from_dict(data.get("loadout", {}))
        self.holdings = Holdings.from_dict(data.get("holdings", {}))
        self.ledger = Ledger.from_dict(data.get("ledger", {}))
        r = data.get("round", {})
        self.round = RoundState(list(r.get("preparations", [])), list(r.get("used", [])), list(r.get("shown", [])),
                                list(r.get("forecast", [])), bool(r.get("forecast_changed", False)))
        sc = data.get("shop", {})
        self.shop_counters = ShopCounters(int(sc.get("stock_round", 0)), int(sc.get("roll_number", 0)),
                                          int(sc.get("paid_used", 0)), int(sc.get("free_used", 0)),
                                          sc.get("extra_offer"))
        self.claim = data.get("claim")
        self.ace_pending = bool(data.get("ace_pending", False))
        self.environment = [EnvRule.from_dict(x) for x in data.get("environment", [])]
        if not self.environment and data.get("rule_data"):  # the first prototype's registry rules (§5)
            mapped = {}
            for old in data["rule_data"]:
                rule = from_legacy(old)
                if rule is not None:
                    mapped.setdefault(rule.type, rule)
            self.environment = list(mapped.values())
        self.acted_round = int(data.get("acted_round", data.get("prepared_round", 0)))
        self.env_history = [dict(x) for x in data.get("env_history", [])]
        self.prepared_round = int(data.get("prepared_round", 0))
        self.last_settled = int(data.get("last_settled", 0))
        self.prepared = None
        if data.get("prepared_packed"):
            cards = json.loads(zlib.decompress(base64.b64decode(data["prepared_packed"])))
            self.prepared = tuple(Card(Rank(rank), suit) for rank, suit in cards)
        self._validate()
        self._sync_items()

    def _validate(self) -> None:
        lo = self.loadout
        if lo.core is not None and lo.core not in CORES:
            raise ValueError("Unknown Poker Head core in save.")
        if (len(lo.equipped) > self.setting("build_slots") or len(set(lo.equipped)) != len(lo.equipped)
                or any(x not in PERMANENTS for x in lo.equipped)):
            raise ValueError("Invalid Poker Head loadout in save.")


@dataclass(frozen=True)
class _RuleView:
    id: str
    label: str
    help: str


def _upgrade_v1(d: dict[str, Any]) -> dict[str, Any]:
    """A save from the first build prototype (version 1, flat fields)."""
    positions = [{"uid": x["uid"], "id": x["id"], "principal": int(x.get("principal", 0)),
                  "debt": 50 if x["id"] == "ph_loan" else 0, "remaining": int(x["remaining"]), "wins": int(x.get("wins", 0))}
                 for x in d.get("contracts", [])]
    return {
        "kind": d["kind"], "version": SAVE_VERSION,
        "loadout": {"core": d.get("core"), "no_core": d.get("no_core", False), "equipped": d.get("equipped", [])},
        "holdings": {"sequence": d.get("sequence", 0),
                     "items": [{"uid": x["uid"], "id": x["id"], "paid": x.get("paid", 0), "choices": x.get("choices", [])}
                               for x in d.get("instances", [])]},
        "ledger": {"sequence": d.get("sequence", 0), "positions": positions},
        "round": {"preparations": d.get("preparations", []), "used": d.get("used", []), "shown": d.get("shown", []),
                  "forecast": d.get("forecast", []), "forecast_changed": d.get("forecast_changed", False)},
        "shop": {"stock_round": d.get("stock_round", 0), "roll_number": d.get("roll_number", 0),
                 "paid_used": d.get("paid_used", 0), "free_used": int(bool(d.get("free_used", False))),
                 "extra_offer": d.get("extra_offer")},
        "claim": d.get("claim"), "ace_pending": d.get("ace_pending", False), "rule_data": d.get("rule_data", []),
        "prepared_round": d.get("prepared_round", 0), "last_settled": d.get("last_settled", 0),
        **({"prepared_packed": d["prepared_packed"]} if d.get("prepared_packed") else {}),
    }


register_table("chaos", PokerHeadTable)
