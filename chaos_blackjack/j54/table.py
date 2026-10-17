"""J-54's table (v2): an experiment on a deck that lasts the run (docs/design/J54_V2_SPEC.md).

* The deck's cards persist between rounds; every round shuffles all of them.
  Its make-up is public (`deck_counts`); its order never is.
* J-54 runs a **program** of conditions (j54/program.py,
  rules/plugins/j54_conditions.py): one at a time, each changing J-54's cards
  or its stand threshold, switched at the first betting phase of a segment and
  announced a round ahead (`mode.j54.announce`).
* The player shapes the deck with **compute** (income every betting phase, a
  cap): table moves Cut (two cards of a rank and colour) and Hot Purge (cards
  of a hot rank), and Release, which puts the sealed Joker into the deck.
* Goal: chips at the target at a settlement from round 9, or a **capture**:
  the player holds the Joker at a non-losing settlement from round 9. The run
  is lost at bankruptcy or when round 16 settles without a win.
* The run opens with a **firmware** choice (j54/firmware.py): one rule on the
  player's cards or bust line, paid from the starting chips.
* After every settlement J-54 adds low cards (entropy); a Joker J-54 draws is
  shuffled back with a low card as a penalty. Removals and additions use the
  deck-operation engine (j54/deck_ops.py).

Card values are per side (`J54Rules`): conditions change J-54's cards only,
the firmware the player's only. Random choices use a counter-seeded RNG, so a
run replays identically however it is saved and resumed.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from chaos_blackjack.app.choice import Choice, ChoiceOption, Move
from chaos_blackjack.app.notices import NoticeKind
from chaos_blackjack.app.table_mechanics import Notify, TableMechanics, register_table
from chaos_blackjack.app.view import RuleView, TablePhase
from chaos_blackjack.core.game_state import Card, GameState, Rank
from chaos_blackjack.j54 import onboarding as first_visit
from chaos_blackjack.j54.deck_ops import JOKER, RANKS, SUITS, DeckContext, DeckOp, apply, is_joker
from chaos_blackjack.j54.firmware import CATALOG as FIRMWARES, NO_FIRMWARE, Firmware, firmware
from chaos_blackjack.j54.program import Program, generate, int_range
from chaos_blackjack.j54.public import J54Snapshot, heat_text, hottest_ranks, measure, snapshot
from chaos_blackjack.rules.modifiers import adjust_rank_value_for
from chaos_blackjack.rules.plugins.j54_conditions import CONDITIONS, ConditionModifier, build_condition
from chaos_blackjack.rules.rule_engine import BLACKJACK, DefaultBlackjackRules, RuleContext, bust_limit

if TYPE_CHECKING:
    from chaos_blackjack.app.config import RunConfig
    from chaos_blackjack.app.controller import GameController
    from chaos_blackjack.app.economy import RunState

SAVE_VERSION = 2
TABLE_EVENT = NoticeKind.TABLE_EVENT  # notice kind of everything the table announces

# Table moves (`perform <action> <arg>`) and choice kinds.
CUT = "j54_cut"
HOT_PURGE = "j54_hot_purge"
RELEASE = "j54_release"
FIRMWARE_CHOICE = "firmware"
CUT_CHOICE = "cut_target"

# The Joker's states.
SEALED, IN_DECK, CAPTURED = "sealed", "in the deck", "captured"

COLOURS = {"r": "red", "b": "black"}
_RED = ("♥", "♦")
ANNOUNCE = ("camp", "rule", "none", "schedule")
NOT_LOST = ("player", "push", "blackjack")   # outcomes that capture the Joker (not a loss, not a surrender)

# Used when a balance profile has no mode.j54.* settings (e.g. cloned before them).
DEFAULTS: dict[str, Any] = {
    "rounds": 16,
    "target_multiple": 1.75,
    "target_from_round": 9,
    "compute_income": 2,
    "compute_cap": 8,
    "cut_cost": 1,
    "cut_size": 2,
    "hot_purge_cost": 1,
    "hot_purge_size": 3,
    "hot_purge_candidates": 3,
    "release_cost": 6,
    "capture_from_round": 9,
    "dealer_joker_penalty": 1,
    "entropy": 1,
    "min_deck": 16,
    "segment_len": "2,4",
    "cross_switches": "1,2",
    "classic_opening": 1,
    "announce": "camp",
    "bands": "50:10,55:20,60:30",
    "firmwares_offered": 3,
    "firmware.fw_mid.price": 50,
    "firmware.fw_fives.price": 20,
    "firmware.fw_low.price": 40,
    "firmware.fw_margin.price": 30,
    "bounty": 2,
}


def joker() -> Card:
    return Card(Rank(JOKER), "")


def standard_cards() -> list[Card]:
    return [Card(Rank(r), s) for s in SUITS for r in RANKS]


def group_of(card: Card) -> str:
    """A card's rank+colour group: "5r", "Kb"."""
    return f"{card.rank}{'r' if card.suit in _RED else 'b'}"


def group_label(group: str) -> str:
    """"5r" -> "5 red"."""
    return f"{group[:-1]} {COLOURS[group[-1]]}"


GROUPS = tuple(f"{r}{c}" for r in RANKS for c in COLOURS)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _settings(config: "RunConfig") -> dict[str, Any]:
    return {**DEFAULTS, **{k[4:]: v for k, v in config.mode_settings.items() if k.startswith("j54.")}}


def target_money(config: "RunConfig") -> int:
    """start_money × target_multiple, rounded down to a multiple of 5."""
    s = _settings(config)
    return int(config.start_money * float(s["target_multiple"]) // 5 * 5)


def _action_error(text: str) -> Exception:
    from chaos_blackjack.app.controller import ActionError

    return ActionError(text)


# --------------------------------------------------------------------------- values


class J54Rules(DefaultBlackjackRules):
    """Per-side values: J-54's condition on J-54's cards, the firmware on the player's.

    Each card has a high and a low value (equal unless it is an ace, or the
    Joker in the player's hand, which is a soft ace; J-54's Joker counts 0).
    Every operation changes both values; aces drop to low while the hand
    would bust. Naturals use the two original cards and never come here.
    """

    def __init__(self, table: "J54Table") -> None:
        self.table = table

    def card_range(self, card: Card, ctx: RuleContext) -> tuple[int, int]:
        player = ctx.actor == "player"
        if is_joker(card):
            return (11, 1) if player else (0, 0)
        high = self._card_base_value(card)
        low = 1 if str(card.rank).upper() == "A" else high
        for m in (*ctx.modifiers.items, *self.table.value_modifiers()):
            high, low = (adjust_rank_value_for(m, card, high, ctx.actor),
                         adjust_rank_value_for(m, card, low, ctx.actor))
        fw = self.table.firmware
        if player and fw is not None:
            high, low = fw.card_value(card, high), fw.card_value(card, low)
        return high, low

    def limit(self, ctx: RuleContext) -> int:
        limit = bust_limit(ctx)
        fw = self.table.firmware
        if ctx.actor == "player" and fw is not None and limit == BLACKJACK:  # a lower Chaos limit still wins
            limit = fw.bust_limit(limit)
        return limit

    def hand_value(self, hand: tuple[Card, ...], ctx: RuleContext) -> int:
        ranges = [self.card_range(card, ctx) for card in hand]
        total = sum(high for high, _ in ranges)
        limit = self.limit(ctx)
        for drop in sorted((high - low for high, low in ranges if high > low), reverse=True):
            if total <= limit:
                break
            total -= drop
        return total

    def is_bust(self, value: int, ctx: RuleContext) -> bool:
        return value > self.limit(ctx)

    def compare_player_dealer(self, state: GameState, ctx: RuleContext) -> str:
        pc, dc = replace(ctx, actor="player"), replace(ctx, actor="dealer")
        p, d = self.hand_value(state.player_hand, pc), self.hand_value(state.dealer_hand, dc)
        flags = ctx.modifiers.chaos_flags()
        if self.is_bust(p, pc):
            return "push" if "reverse_bust" in flags else "dealer"
        if self.is_bust(d, dc):
            return "player"
        if p != d:
            return "player" if p > d else "dealer"
        if "player_wins_ties" in flags:
            return "player"
        return "dealer" if "dealer_wins_ties" in flags else "push"


# --------------------------------------------------------------------------- the table


class J54Table(TableMechanics):
    id = "j54"
    persistent_rules = True
    uses_chaos_budget = False  # J-54's program, not the Chaos AI, changes the rules here
    # False: the codex reads this flag as "Poker Head's environment catalog"; J-54's rules are its
    # registered conditions (the mode's pool), which the codex lists as its rules.
    environment_rules = False
    has_shop = False  # compute buys the moves; nothing is sold here

    @classmethod
    def goal(cls, config: "RunConfig") -> str:
        s = _settings(config)
        return (f"Reach {target_money(config)} chips from round {s['target_from_round']}, "
                "or capture the Joker")

    def __init__(self, config: "RunConfig", seed: int | str, notify: Notify) -> None:
        super().__init__(config, seed, notify)
        self.settings = _settings(config)
        self.conditions: dict[str, ConditionModifier] = {
            rid: build_condition(rid, config.chaos_rule_params.get(rid, {})) for rid in self._pool()}
        self.program: Program = generate(
            seed, self.rounds, {rid: m.camp for rid, m in self.conditions.items()},
            int_range(self.settings["segment_len"]), int_range(self.settings["cross_switches"]),
            bool(int(self.settings["classic_opening"])))
        self.cards: list[Card] = standard_cards()
        self.removed: list[Card] = []
        self.compute = 0
        self.joker = SEALED
        self.firmware_id: str | None = None
        self.segment = -1               # index of the condition in force (-1 before round 1)
        self.entered_round = 0          # the round whose betting phase the table last entered
        self.announcement: str | None = None
        self.bounty_rank: str | None = None
        self.won: str | None = None
        self.lost: str | None = None
        self._bounty_paid = 0           # chips the settling hand's bounty paid (settlement -> after_settle)
        self._ops = 0                   # RNG counter (saved), see _rng
        self._meter: tuple | None = None  # the evaluator's last reading (j54/public.py measure)
        self.guide = first_visit.Guide()  # first-visit explanations and the meter hint (j54/onboarding.py)

    def _pool(self) -> tuple[str, ...]:
        pool = self.config.rule_pool
        ids = tuple(r for r in (pool if pool is not None else CONDITIONS) if r in CONDITIONS)
        return ids or tuple(CONDITIONS)

    def bind(self, controller: "GameController") -> None:
        self.c = controller
        controller.loop.rules = J54Rules(self)

    # --- helpers ----------------------------------------------------------

    def _rng(self) -> random.Random:
        self._ops += 1
        return random.Random(f"{self.seed}:j54:{self._ops}")

    def _say(self, text: str, **data: Any) -> None:
        self.notify(TABLE_EVENT, text, {"text": text, "table": self.id, **data})

    def _int(self, key: str) -> int:
        return int(self.settings[key])

    @property
    def rounds(self) -> int:
        return self._int("rounds")

    @property
    def compute_cap(self) -> int:
        return self._int("compute_cap")

    @property
    def min_deck(self) -> int:
        return self._int("min_deck")

    @property
    def deck_size(self) -> int:
        return len(self.cards) + (1 if self.joker == IN_DECK else 0)

    @property
    def firmware(self) -> Firmware | None:
        return firmware(self.firmware_id)

    def firmware_price(self, firmware_id: str) -> int:
        return self._int(f"firmware.{firmware_id}.price")

    def condition(self) -> ConditionModifier | None:
        if self.segment < 0:
            return None
        return self.conditions.get(self.program.segments[self.segment].rule)

    def value_modifiers(self) -> tuple[ConditionModifier, ...]:
        """The condition's value change, for J54Rules (none before round 1 or for a threshold)."""
        m = self.condition()
        return (m,) if m is not None and m.rule is not None else ()

    def rounds_left(self) -> int:
        """Rounds the condition in force still holds, this one included."""
        if self.segment < 0:
            return 0
        return max(0, self.program.segments[self.segment].end - self.entered_round + 1)

    def _run(self, op: DeckOp):
        ctx = DeckContext(self.cards, self.removed, self._rng, self.min_deck)
        return apply(op, ctx)

    def deck_counts(self) -> tuple[tuple[str, int], ...]:
        """How many cards of each rank the deck holds (all of them, whatever is in play)."""
        return tuple((r, sum(1 for c in self.cards if str(c.rank) == r)) for r in RANKS)

    def group_counts(self) -> dict[str, int]:
        """Cards per rank+colour group ("5r", "Kb"), every group listed."""
        out = dict.fromkeys(GROUPS, 0)
        for c in self.cards:
            out[group_of(c)] += 1
        return out

    # --- the evaluator's reading (j54/public.py) -----------------------------

    def _hottest_ranks(self, n: int) -> list[str]:
        """The `n` ranks present with the highest heat, summed over both colours, under the condition and
        the firmware (ties by rank order)."""
        return hottest_ranks(measure(self)[1], n)

    def _bounty_rank(self) -> str:
        """The rank J-54 values most under the condition in force: the rank whose worth for J-54 the
        condition raises most over the four suits, ties by rank order (the first rank when nothing rises)."""
        m = self.condition()
        if m is None or m.rule is None:
            return RANKS[0]
        base = DefaultBlackjackRules()

        def gain(rank: str) -> int:
            cards = [Card(Rank(rank), s) for s in SUITS]
            return sum(m.adjust_rank_value_for(c, base._card_base_value(c), "dealer") - base._card_base_value(c)
                       for c in cards)

        return max(RANKS, key=lambda r: (gain(r), -RANKS.index(r)))

    # --- run --------------------------------------------------------------

    def start(self, run: "RunState") -> None:
        first_visit.run_started(self)
        run.objective = "j54"
        run.target_money = target_money(self.config)
        self._enter_round(run.round)
        self._ask_firmware()

    def _ask_firmware(self) -> None:
        first_visit.firmware_offered(self)
        count = min(self._int("firmwares_offered"), len(FIRMWARES))
        offered = random.Random(f"{self.seed}:j54:firmware").sample(sorted(FIRMWARES), count)
        options = tuple(ChoiceOption(f, f"{FIRMWARES[f].name} ({self.firmware_price(f)} chips)", FIRMWARES[f].text)
                        for f in offered)
        options += (ChoiceOption(NO_FIRMWARE, "No firmware", "Keep every chip and play your cards as printed."),)
        self.c.ask(Choice(FIRMWARE_CHOICE, "J-54 offers firmware for your side of the table. It lasts the whole "
                          "run and is paid from your starting chips.", options, cancellable=False,
                          payload={"offered": list(offered)}))

    def _install_firmware(self, option: str) -> None:
        if option == NO_FIRMWARE:
            self._say("No firmware: you play your cards as printed.", effect="firmware")
            return
        fw = FIRMWARES.get(option)
        if fw is None:
            raise _action_error("Choose one of the offered firmwares.")
        price = self.firmware_price(option)
        if not self.c.can_bet(self.c.run.money - price):
            raise _action_error(f"{fw.name} costs {price} chips: keep enough to bet.")
        self.c.run.money -= price
        self.firmware_id = option
        self._say(f"Firmware installed: {fw.name}. {fw.text} ({price} chips)", effect="firmware",
                  firmware=option, price=price)

    def summary(self) -> list[str]:
        s = self.settings
        return [f"Experiment protocol: {self.rounds} rounds. Reach {target_money(self.config)} chips at a "
                f"settlement from round {s['target_from_round']}, or hold my Joker when a hand you do not lose "
                f"settles from round {s['capture_from_round']}.",
                "My conditions change my cards, never yours. Spend compute to cut the deck; after each hand I "
                "add a low card."]

    def info(self, run: "RunState") -> tuple[tuple[str, str], ...]:
        # The condition in force is the table's active rule (active_rules), so it is not repeated here.
        rows: list[tuple[str, str]] = [("Compute", f"{self.compute}/{self.compute_cap}")]
        snap = self.public()
        rows.append(("Meter", f"{snap.bar:.1%} win, EV {snap.ev:+.2f} bets, suggested stake {snap.band['suggested']}"
                     + (f", capture {snap.capture:.1%}" if self.joker == IN_DECK else "")))
        if self.announcement:
            rows.append(("Next", self.announcement))
        fw = self.firmware
        rows.append(("Firmware", fw.name if fw else "None"))
        rows.append(("Joker", self.joker))
        rows.append(("Goal", f"{run.target_money} chips from round {self.settings['target_from_round']}"))
        rows.append(("Deck", _plural(self.deck_size, "card")))
        if self.removed:
            rows.append(("Removed", _plural(len(self.removed), "card")))
        if self.bounty_rank:
            rows.append(("Bounty", f"{self.bounty_rank}: {self._int('bounty')} chips per card in your hand"))
        return tuple(rows)

    def victory(self, run: "RunState") -> str | None:
        return self.won

    def host_variant(self, event: str) -> str:
        return "capture" if event == "victory" and self.joker == CAPTURED else ""

    def defeat(self, run: "RunState") -> str | None:
        return self.lost

    def active_rules(self) -> tuple[RuleView, ...]:
        m = self.condition()
        if m is None:
            return ()
        left = self.rounds_left()
        return (RuleView(m.id, f"{m.name}: {m.text}. {_plural(left, 'round')} left in this condition.",
                         m.name, f"{m.text}.", "J-54's cards", left, "Changes when the condition's rounds end.",
                         icon=m.id, tier=m.camp),)

    def public(self) -> J54Snapshot:
        return snapshot(self)

    def onboarding(self, guided: bool) -> tuple:
        return first_visit.take(self, guided)

    # --- program and compute -------------------------------------------------

    def entered_betting(self) -> None:
        self._enter_round(self.c.run.round)

    def _enter_round(self, round_no: int) -> None:
        """A round's betting phase: compute income, then the program (before shaping and betting)."""
        if round_no == self.entered_round:
            return
        self.entered_round = round_no
        income = self._int("compute_income")
        gained = max(0, min(self.compute_cap, self.compute + income) - self.compute)
        self.compute += gained
        if gained:
            self._say(f"Compute +{gained} ({self.compute}/{self.compute_cap}).", effect="compute")
        index = self.program.index_at(round_no)
        if index != self.segment:
            self.segment = index
            m = self.condition()
            assert m is not None
            self.bounty_rank = self._bounty_rank()
            seg = self.program.segments[index]
            self._say(f"Condition {index + 1} begins: {m.text}. It holds for {_plural(seg.length, 'round')}. "
                      f"Bounty: {self._int('bounty')} chips for every {self.bounty_rank} in your hand.",
                      effect="condition", rule=m.id, camp=m.camp, bounty=self.bounty_rank)
        self.announcement = self._announce(round_no)
        if self.announcement:
            self._say(self.announcement, effect="announcement")
        first_visit.entered_betting(self)

    def _announce(self, round_no: int) -> str | None:
        """What J-54 says on the last round of a condition about the next one."""
        seg = self.program.at(round_no)
        nxt = self.program.next_after(round_no)
        mode = self.settings["announce"]
        if nxt is None or round_no != seg.end or mode not in ("camp", "rule"):
            return None
        m = self.conditions[nxt.rule]
        if mode == "camp":
            return f"Next condition: {m.camp} camp."
        return f"Next condition: {m.text}."

    def dealer_stand_on(self, default: int) -> int:
        m = self.condition()
        return m.threshold if m is not None and m.threshold is not None else default

    def should_chaos(self) -> bool:
        return False  # the program acts before betting; nothing changes after the deal

    # --- moves ----------------------------------------------------------------

    def _blocker(self, cost: int, removes: bool = True) -> str:
        if self.compute < cost:
            return f"Not enough compute: {cost} needed, {self.compute} held."
        if removes and len(self.cards) <= self.min_deck:
            return f"The deck is at its minimum of {self.min_deck} cards."
        return ""

    def cut_reason(self, group: str) -> str:
        """Why `group` cannot be cut now ("" = it can)."""
        if group not in GROUPS:
            return "Unknown group."
        blocker = self._blocker(self._int("cut_cost"))
        if blocker:
            return blocker
        if not self.group_counts()[group]:
            return f"No {group_label(group)} card is left in the deck."
        return ""

    def table_moves(self) -> tuple[Move, ...]:
        if self.c.choice is not None or self.c.phase != TablePhase.BETTING:
            return ()
        cut_cost, purge_cost, release_cost = (self._int("cut_cost"), self._int("hot_purge_cost"),
                                              self._int("release_cost"))
        counts = self.group_counts()
        cut = self._blocker(cut_cost)
        moves = [Move(CUT, "", f"Cut ({cut_cost} compute)", not cut, cut)]
        for group in GROUPS:  # the deck strip offers these on its bars
            reason = self.cut_reason(group)
            moves.append(Move(CUT, group, f"Cut {group_label(group)} ({counts[group]} left)", not reason, reason,
                              listed=False))
        purge = self._blocker(purge_cost)
        moves.append(Move(HOT_PURGE, "", f"Hot Purge ({purge_cost} compute)", not purge, purge))
        release = "The Joker is already released." if self.joker != SEALED else self._blocker(release_cost, False)
        moves.append(Move(RELEASE, "", f"Release the Joker ({release_cost} compute)", not release, release))
        return tuple(moves)

    def perform(self, action: str, arg: str) -> object:
        if action == CUT and not arg:
            self._ask_cut()
        elif action == CUT:
            self._cut(arg)
        elif action == HOT_PURGE:
            self._hot_purge()
        elif action == RELEASE:
            self._release()
        else:
            raise _action_error(f"Unknown action {action!r}")
        return None

    def _ask_cut(self) -> None:
        counts = self.group_counts()
        options = tuple(ChoiceOption(g, f"{group_label(g)} ({counts[g]} left)", self._heat_text(g))
                        for g in GROUPS if not self.cut_reason(g))
        if not options:
            raise _action_error(self._blocker(self._int("cut_cost")) or "Nothing to cut.")
        self.c.ask(Choice(CUT_CHOICE, f"Cut which group? {_plural(self._int('cut_size'), 'card')} of it leave "
                          f"the deck for {self._int('cut_cost')} compute.", options, payload={}))

    def _heat_text(self, group: str) -> str:
        """The group's heat for the cut choice: "+0.3 pp · cut" / "-0.2 pp · keep"."""
        return heat_text(measure(self)[1].get(group, 0.0))

    def _cut(self, group: str) -> None:
        reason = self.cut_reason(group)
        if reason:
            raise _action_error(reason)
        self.compute -= self._int("cut_cost")
        pool = [c for c in self.cards if group_of(c) == group]
        picked = self._rng().sample(pool, min(self._int("cut_size"), len(pool)))
        gone = []
        for card in picked:
            if len(self.cards) <= self.min_deck:
                break
            self.cards.remove(card)
            self.removed.append(card)
            gone.append(card)
        self._say(f"Cut {group_label(group)}: {', '.join(f'{c.rank}{c.suit}' for c in gone)} removed "
                  f"({self.compute} compute left).", effect="cut", group=group, cards=len(gone))

    def _hot_purge(self) -> None:
        blocker = self._blocker(self._int("hot_purge_cost"))
        if blocker:
            raise _action_error(blocker)
        candidates = self._hottest_ranks(self._int("hot_purge_candidates"))
        if not candidates:
            raise _action_error("Nothing to purge.")
        self.compute -= self._int("hot_purge_cost")
        rank = self._rng().choice(candidates)
        op = DeckOp("remove", f"rank:{rank}", self._int("hot_purge_size"))
        result = self._run(op)
        self._say(f"Hot Purge drew rank {rank}: {_plural(len(result.cards), 'card')} removed "
                  f"({self.compute} compute left).", effect="hot_purge", rank=rank, cards=len(result.cards))

    def _release(self) -> None:
        if self.joker != SEALED:
            raise _action_error("The Joker is already released.")
        blocker = self._blocker(self._int("release_cost"), removes=False)
        if blocker:
            raise _action_error(blocker)
        self.compute -= self._int("release_cost")
        self.joker = IN_DECK
        self._say(f"Joker released: the sample is in the deck. Hold it when a hand you do not lose settles from "
                  f"round {self.settings['capture_from_round']}.", effect="release")

    # --- choices --------------------------------------------------------------

    def resolve_choice(self, choice: Choice, option: str) -> None:
        if choice.kind == FIRMWARE_CHOICE:
            self._install_firmware(option)
        elif choice.kind == CUT_CHOICE:
            self._cut(option)
        else:
            raise _action_error(f"Unknown choice {choice.kind!r}")

    # --- round ------------------------------------------------------------

    def round_cards(self) -> tuple[Card, ...]:
        return tuple(self.cards) + ((joker(),) if self.joker == IN_DECK else ())

    def after_cards(self, state: GameState) -> GameState:
        """J-54 never keeps the Joker: it swaps in the next card and shuffles the Joker back (never on
        top), adding a low card as a penalty. A Joker you draw stays in your hand."""
        deck = list(state.deck)
        dealer = list(state.dealer_hand)
        for i, card in enumerate(dealer):
            if is_joker(card) and deck:
                dealer[i] = self._take(deck)
                deck.insert(self._rng().randint(min(1, len(deck)), len(deck)), card)
                penalty = self._int("dealer_joker_penalty")
                added = self._run(DeckOp("add", "low", penalty)).cards if penalty else []
                extra = f" and adds {', '.join(str(c.rank) for c in added)}" if added else ""
                self._say(f"J-54 drew the Joker. It shuffles it back{extra}.", effect="dealer_joker")
        return replace(state, dealer_hand=tuple(dealer), deck=tuple(deck))

    @staticmethod
    def _take(deck: list[Card]) -> Card:
        """The first card of `deck` that is not a Joker (removed from it)."""
        for i, card in enumerate(deck):
            if not is_joker(card):
                return deck.pop(i)
        return deck.pop(0)

    def settlement(self, state: GameState, outcome: str, bet: int, doubled: bool, delta: int) -> int:
        """The sample bounty: every card of J-54's named rank in your hand pays, win or lose."""
        n = sum(1 for c in state.player_hand if self.bounty_rank and str(c.rank) == self.bounty_rank)
        self._bounty_paid = n * self._int("bounty")
        return delta + self._bounty_paid

    def after_settle(self, state: GameState, outcome: str, modifiers: Any, run: "RunState") -> None:
        round_no = run.round
        if self._bounty_paid:
            self._say(f"Bounty: {self._bounty_paid} chips for your {self.bounty_rank}s.", effect="bounty",
                      chips=self._bounty_paid)
            self._bounty_paid = 0
        if any(is_joker(c) for c in state.player_hand):
            capture_from = self._int("capture_from_round")
            if round_no >= capture_from and outcome in NOT_LOST:
                self.joker = CAPTURED
                self.won = "Sample captured. The experiment is complete."
                self._say("You hold the Joker and the hand is not lost: sample captured.", effect="capture")
                return
            if round_no < capture_from:
                self._say(f"You drew the Joker, but the sample is not recorded yet (from round {capture_from}). "
                          "It returns to the deck.", effect="joker_returns")
            else:
                self._say("You drew the Joker but lost the hand. It returns to the deck.", effect="joker_returns")
        n = self._int("entropy")
        if n:
            op = DeckOp("add", "low", n)
            self._say(f"Entropy: J-54 {self._run(op).summary(op)}.", effect="entropy")
        if round_no >= self._int("target_from_round") and run.money >= run.target_money:
            self.won = f"Capital reached: {run.money} chips. The experiment is complete."
        elif round_no >= self.rounds:
            self.lost = f"Round {self.rounds} is over and the experiment ended without a result."

    # --- save -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.id, "version": SAVE_VERSION,
            "program": self.program.to_list(),
            "cards": [[str(c.rank), c.suit] for c in self.cards],
            "removed": [[str(c.rank), c.suit] for c in self.removed],
            "compute": self.compute,
            "joker": self.joker,
            "firmware": self.firmware_id,
            "segment": self.segment,
            "entered_round": self.entered_round,
            "announcement": self.announcement,
            "bounty_rank": self.bounty_rank,
            "won": self.won,
            "lost": self.lost,
            "ops": self._ops,
            "onboarding": self.guide.to_dict(),
        }

    def restore(self, data: dict[str, Any]) -> None:
        if data.get("kind") != self.id or data.get("version") != SAVE_VERSION:
            raise ValueError("This J-54 save is from the demo table and cannot be resumed.")
        program = Program.from_list(data["program"])
        if any(s.rule not in self.conditions for s in program.segments):
            raise ValueError("Unknown J-54 condition in save.")
        if data.get("firmware") not in (None, *FIRMWARES):
            raise ValueError("Unknown J-54 firmware in save.")
        if data.get("joker") not in (SEALED, IN_DECK, CAPTURED):
            raise ValueError("Invalid J-54 Joker state in save.")
        self.program = program
        self.cards = [Card(Rank(r), s) for r, s in data.get("cards", [])]
        self.removed = [Card(Rank(r), s) for r, s in data.get("removed", [])]
        self.compute = int(data.get("compute", 0))
        self.joker = str(data["joker"])
        self.firmware_id = data.get("firmware")
        self.segment = int(data.get("segment", -1))
        self.entered_round = int(data.get("entered_round", 0))
        self.announcement = data.get("announcement")
        self.bounty_rank = data.get("bounty_rank")
        self.won = data.get("won")
        self.lost = data.get("lost")
        self._ops = int(data.get("ops", 0))
        self.guide.restore(data.get("onboarding", {}))


register_table("j54", J54Table)
