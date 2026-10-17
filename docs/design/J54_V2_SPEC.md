# J-54 v2: implementation specification

Status: **scope frozen 2026-10-17**, to build. Design and evidence:
[J54_PRIMITIVES.md](J54_PRIMITIVES.md) (sections 0b, 0c, 10, 12). v1 (the
demo) is [J54_TABLE.md](J54_TABLE.md) section 0; this replaces it at the
table `j54`. Numbers below are first values: every one lives in the balance
profile (section 9) and is tuned by playing, not by changing code.

Theme unchanged: J-54, a calculating machine, runs an *experiment* on a deck
that lasts the run. It changes the cards' worth by announcing experiment
conditions; the player rebuilds the deck with a small budget of compute.

## 1. The run

| Item | Rule | Profile key (default) |
|---|---|---|
| Length | 16 rounds; round 16's settlement ends the run | `mode.j54.rounds` (16) |
| Start | 100 chips, 52-card deck, no Joker in the deck (one sealed) | `mode.j54.config.start_money` (100) |
| Win | the first time, **at a round's settlement from round 9 on**, chips ≥ target; or a **capture** (section 6) | `mode.j54.target_multiple` (1.75), `mode.j54.target_from_round` (9) |
| Lose | bankrupt (cannot place the minimum bet), or round 16 settles without a win | — |
| Bets | the profile's range: 5 to half the bankroll; no extra cap | — |
| Compute fee, contracts, protocols drawn per run | **removed** from v1 | — |

Target = `start_money × target_multiple`, rounded down to a multiple of 5.
`run.target_money` is set to it so the existing goal bar and run-end logic
work; the table's `victory()` adds the round-9 condition and the capture.

## 2. Compute (the shaping budget)

- A run-level integer `compute`, separate from chips. Income
  `mode.j54.compute_income` (2) is credited when a round enters betting
  (round 1 included); the bank holds at most `mode.j54.compute_cap` (8).
- Compute buys the operations of section 4 and the Joker release (section 6).
  It never buys items, bets or firmware.
- Shown as a badge in the right column ("Compute 4/8") and in
  `obs.table.public.compute`.

## 3. J-54's program (the rule schedule)

J-54 changes the rules itself (`environment_rules = True`,
`uses_chaos_budget = False`, `should_chaos()` False, `persistent_rules =
True`), exactly one **condition** active at a time, from this pool
(`chaos_rule` rows; names are neutral on purpose, the heat map tells the
player which way a rule points):

| id | Condition (J-54's cards only) | Camp | Params |
|---|---|---|---|
| `j54_black_plus` | J-54's black cards count +1 | classic | `amount` 1 |
| `j54_even_plus` | J-54's even ranks (2 4 6 8 10 Q) count +2 | classic | `amount` 2 |
| `j54_hearts_scale` | J-54's hearts count double | classic | `factor` 2 |
| `j54_stand_19` | J-54 stands on 19 | classic | `threshold` 19 |
| `j54_stand_15` | J-54 stands on 15 | anti | `threshold` 15 |
| `j54_low_plus` | J-54's low cards (2–6) count +3 | anti | `amount` 3 |
| `j54_faces_set` | J-54's J, Q, K count 5 | loner | `value` 5 |

v1's deck-operation rules (`j54_burn`, `j54_sample_injection`, ...) stay
registered for the codex but leave the mode's pool.

**Schedule.** Generated from the run seed at `start()`; saved with the run.
Segments of `mode.j54.segment_len` (`"2,4"`: 2 to 4 rounds) cover the 16
rounds; the first segment's rule is classic when `mode.j54.classic_opening`
(1); no rule twice in a row; the number of classic ↔ anti switches is drawn
from `mode.j54.cross_switches` (`"1,2"`; a switch to or from the loner counts
half, rounded down at the end). The segment rule changes at `entered_betting`
of the segment's first round, before shaping and betting, announced as a
table event ("Condition 3 begins: J-54's hearts count double"). Nothing
changes after the deal.

**Announcement** (`mode.j54.announce`, `"camp"`): on the last round of a
segment, at betting, J-54 announces the next segment's camp (`"camp"`:
"Next condition: anti camp"), the rule itself (`"rule"`), nothing (`"none"`),
or the whole program is readable in the Run panel from round 1
(`"schedule"`). The current condition shows as the single active rule
(`active_rules()`: name, scope "J-54's cards", effect, remaining rounds of
the segment, camp in `tier`).

## 4. Shaping the deck: the menu

Operations are **table moves** (`table_moves()` / `perform`), legal in the
betting phase only, paid in compute; the GUI offers them from the deck strip
and the actions row, the agent as `perform <action> <arg>`.

| Move | Arg | Cost | Effect |
|---|---|---|---|
| `j54_cut` | a rank+colour group (`5r`, `Kb`, ...) | `mode.j54.cut_cost` (1) | removes 2 cards of that rank and colour (or all that remain if fewer); without an arg it asks a Choice listing the groups present, each with its heat value |
| `j54_hot_purge` | none | `mode.j54.hot_purge_cost` (1) | removes `mode.j54.hot_purge_size` (3) cards of **one rank drawn at random among the `mode.j54.hot_purge_candidates` (3) ranks with the highest heat** (summed over both colours); the rank is announced after the purchase |
| `j54_release` | none | `mode.j54.release_cost` (6) | puts the sealed Joker into the deck (section 6); once per run |

Rules: a move is disabled with a reason when compute is short, when the deck
is at `mode.j54.min_deck` (16) cards, when the group is empty, or when the
Joker is already released. Removed cards go to the removed pile (shown in the
Deck panel). Nothing is ever inserted by the player (the Sample card and
Inject were tested and dropped; see J54_PRIMITIVES.md section 0c).

Entropy: after every settlement J-54 adds `mode.j54.entropy` (1) low card
(2–6, random rank and suit), as in v1. No injections in this version.

## 5. The meter and the heat map

`chaos_blackjack/j54/evaluator.py` (ported from the rule lab's exact
evaluator: i.i.d. draws from the deck's composition, J-54 peeks for a
natural, naturals settle first, the player hits or stands to maximise the
objective; pure Python, standard library only):

```python
@dataclass(frozen=True)
class Valuation:
    dealer_rules: tuple[Mapping[str, Any], ...]   # {"op": "bonus"|"scale"|"set", "filter": ..., "amount"/"factor"/"value"}
    player_rules: tuple[Mapping[str, Any], ...]   # the firmware, same shape, player side
    dealer_stand_on: int = 17
    player_bust: int = 21
    dealer_bust: int = 21
    joker_in_deck: bool = False      # Joker: a soft ace for the player, 0 for J-54, never a natural

class Evaluator:
    def __init__(self, valuation: Valuation) -> None: ...
    def stats(self, deck: Iterable[Card]) -> HandStats
        # win, push, loss (probabilities), ev (in bets, 3:2 naturals), capture (P the player draws the Joker in the hand, 0 without one)
    def heat(self, deck: Iterable[Card]) -> dict[str, float]
        # rank+colour group -> change of win probability, in percentage points, when one card of the group is removed (positive = removing helps the player)
```

Filters as in the lab: `color:black`, `parity:even`, `suit:♥`, `face`,
`low`, `rank:7`, `ranks:4-6`. Results are cached by composition and
valuation. Budget: a 52-card evaluation and its 26 heat values in well
under a second in CPython; the table recomputes once per betting phase and
after each operation.

What the player sees (via `TablePublic` for `j54`, section 8):

- **The meter**: the bar (win probability) as a gauge with the betting
  **bands** marked, and the band's suggested stake: below 50 % the minimum,
  50–55 % 10 % of the bankroll, 55–60 % 20 %, 60 % and up 30 %
  (`mode.j54.bands`, `"50:10,55:20,60:30"`). The suggestion is advice only;
  the bet range is unchanged.
- **The deck strip** (13 bars, as in v1) coloured by heat: a rank whose
  removal helps the player is green, one to keep is red, the shade by
  magnitude; the tooltip gives both colours' values and the count. The strip
  shows the deck the next round is dealt from, under the active condition
  and the firmware. It shows **direction, never a plan**.
- The agent gets the same numbers: `bar`, `ev`, `band`, `heat`.

## 6. The Joker: the capture route

- One Joker is **sealed** at the start. `j54_release` (section 4) puts it
  into the deck for the rest of the run. The Joker is a soft ace for the
  player and 0 for J-54, never part of a natural, never removed by any
  operation or by entropy.
- When the **player** draws it, the hand plays on. At settlement, if the
  round is ≥ `mode.j54.capture_from_round` (9) and the outcome is not a loss
  (win, push, natural; not a surrender), the run is **won by capture**
  ("Sample captured"). Otherwise the Joker is shuffled back into the deck
  (never on top) and the hand settles normally; before round 9 J-54 says the
  sample "is not recorded yet".
- When **J-54** draws it, it swaps in the next card, shuffles the Joker back
  (never on top) and adds `mode.j54.dealer_joker_penalty` (1) low card, as
  in v1.
- The Joker's state (sealed / in the deck / captured) is a badge and in the
  public snapshot; the meter shows `capture` per hand once it is in the deck.

Why these numbers: the release passed its lines in the lab but a capture
counted from any round gave a non-shaping player +34 pp of luck; counting
it from round 9 is the first fix to try, "third card or later" the second.

## 7. Firmware (the player's build pick)

At `start()` the table asks a Choice (`kind="firmware"`, not cancellable):
three firmwares drawn by the seed from the catalog plus "No firmware". A
firmware is one rule on the **player's** values or bust line for the whole
run, paid from the starting chips (the price is deducted at once; shown in
the option). Catalog (`mode.j54.firmware.<id>.price`):

| id | Rule | Price (chips) |
|---|---|---|
| `fw_mid` | your 4, 5 and 6 count 10 | 50 |
| `fw_fives` | your 5s and 6s count 10 | 20 |
| `fw_low` | your 2, 3 and 4 count 10 | 40 |
| `fw_margin` | you bust only above 22 | 30 |

`mode.j54.firmwares_offered` (3). The firmware is shown next to the compute
badge and in the Run panel; it enters the evaluator as `player_rules` /
`player_bust`, so the heat map and the meter include it.

## 8. Public snapshot, agent and GUI

`TablePublic` for J-54 (`j54/public.py`, frozen, JSON-safe; never undealt
cards, never the deck order):

```python
compute: int; compute_cap: int
condition: {"id", "name", "camp", "rounds_left"}
announcement: str | None            # "Next condition: anti camp", or None
program: tuple[...] | None          # the whole schedule when announce == "schedule", else None
firmware: {"id", "name"} | None
joker: "sealed" | "in the deck" | "captured"
bar: float; ev: float; band: {"low": int, "stake_pct": int, "suggested": int}; capture: float
heat: {group: pp}                   # 26 groups; the GUI sums per rank for the strip
deck_size: int; removed: int
bounty: {"rank": str, "chips": int} | None   # section 10
```

Agent (`AGENTS.md`, `docs/AGENT_GUIDE.md` §8c, schema 3 unchanged): the
moves appear in `obs.table_actions` (`j54_cut <group>`, `j54_hot_purge`,
`j54_release`) with reasons; the firmware and the cut target are
`obs.choice` (kinds `firmware`, `cut_target`); `obs.table.public` holds the
snapshot above; `obs.table.deck` keeps the rank counts.

GUI (`j54/parts.py`, layout in `modes/__init__.py`; `docs/design/TABLE_UI.md`):
the right column keeps the deck pile, the strip (now a heat map), badges
(compute, condition with rounds left and the announcement, Joker, firmware),
item slots and buttons; the Deck panel adds the removed pile and the full
heat table; the Run panel shows the goal bar, the program (as far as the
tier reveals it) and the firmware; the Contracts tab is removed. The strip's
bars carry an `Act` for `j54_cut` on their group when legal; the buttons row
offers Hot Purge and Release when legal.

## 9. Balance profile

New `balance_setting` rows (`mode.j54.*`), all integers or short strings:
`rounds` 16 · `target_multiple` 1.75 · `target_from_round` 9 ·
`compute_income` 2 · `compute_cap` 8 · `cut_cost` 1 · `hot_purge_cost` 1 ·
`hot_purge_size` 3 · `hot_purge_candidates` 3 · `release_cost` 6 ·
`capture_from_round` 9 · `dealer_joker_penalty` 1 · `entropy` 1 ·
`min_deck` 16 · `segment_len` "2,4" · `cross_switches` "1,2" ·
`classic_opening` 1 · `announce` "camp" · `bands` "50:10,55:20,60:30" ·
`firmwares_offered` 3 · `firmware.fw_mid.price` 50 · `firmware.fw_fives.price`
20 · `firmware.fw_low.price` 40 · `firmware.fw_margin.price` 30 · `bounty` 2 ·
`config.start_money` 100.

Removed: `protocols`, `capital_target`, `experiment_jokers`, `fee_steps`,
`fee_step_rounds`, `entropy_experiment`, `config.shop_refresh_rounds`; the
`shop_item` rows of the five v1 contracts. New `chaos_rule` rows for the
seven conditions (params above, weight irrelevant: the program picks them).
The locked `default` profile re-imports from the seed; no migration is
needed unless a new table is required.

## 10. Small extras in this version

- **Sample bounty** (Collection as a side reward, the only form that
  survived the lab): with each condition J-54 names the rank it values most
  under it: the rank whose removal helps the player most on the heat map at
  the switch (both colours summed, ties by rank order), or, when no removal
  helps, the rank the condition raises most for J-54; every card of that rank that lands in the
  player's hand pays `mode.j54.bounty` (2) chips at settlement, win or lose.
  Shown as a badge; announced with the condition.
- **Host lines**: new intro / condition / capture / victory / defeat beats
  in `ai/hosts/j54.json` (the mode drops "(demo)" from its name).
- **Difficulty tiers** are not a UI feature yet: the profile's `announce`,
  `cross_switches` and `classic_opening` are the dials; a cloned profile is
  a tier.

## 11. Engine hooks this needs

- **Per-side card values.** J-54's conditions change only J-54's values,
  the firmware only the player's. Follow Poker Head's path
  (`poker_head/evaluation.py`, its `card_value(card, value)` effects with an
  `actor`, and `bust_limit`); if the shared engine lacks an actor-aware
  hook, add one in `rules/modifiers.py` (`adjust_rank_value_for(card,
  base, actor)` with a neutral default) and use it from both tables rather
  than special-casing J-54 in the controller.
- **Dealer stand threshold per round**: a `TableMechanics.dealer_stand_on(default)
  -> int` hook (neutral default returns `default`), read where the dealer
  draws; J-54 returns the active condition's threshold.
- **Player bust line** for `fw_margin`: the same path Poker Head's Room to
  Breathe uses.
- `GameLoop.new_round` already takes the table's `round_cards()`.

Everything else (moves, choices, badges, snapshot, save, agent) uses hooks
that exist (`app/table_mechanics.py`, `app/choice.py`, `app/view.py`).

## 12. Tests

`tests/test_j54.py` is rewritten for v2 (v1's fee, contract and protocol
tests go). At least: the program covers 16 rounds with the configured
switches and a classic opening and is saved and restored; the condition
changes at the segment's first betting phase and the announcement comes one
round earlier; compute income, cap and costs; Cut removes the group and
Hot Purge a hottest-three rank, both refused at the floor; release once,
capture wins only from round 9 and only on a non-loss, the Joker returns
otherwise; J-54 never keeps the Joker; entropy; the firmware changes the
player's values only and costs chips; the bounty pays; victory at the
target only from round 9; the evaluator's bar matches a Monte Carlo of a
plain deck within 1 pp and its heat has the plain-blackjack signs (removing
5s helps, removing tens hurts); the public snapshot and the agent
observation carry the fields of section 8; 20 seeded runs finish without
errors; a save in the middle of a choice restores it. Tests force
`CHAOS_USE_LLM=0` and `CHAOS_DB=:memory:` as everywhere.

## 13. Work packages

| Package | Owns (files) | Depends on |
|---|---|---|
| **A. Evaluator** | `chaos_blackjack/j54/evaluator.py` (new), `tests/test_j54_evaluator.py` (new) | nothing; the interface of section 5 |
| **B. Table core** | `chaos_blackjack/j54/table.py`, `program.py` (new), `firmware.py` (new), `rules/plugins/j54_conditions.py` (new), `app/table_mechanics.py` (one hook), `rules/modifiers.py` (actor hook if needed), the controller / game loop call sites of those hooks, `modes/__init__.py` (mode def, layout untouched), `data/seed/default.sql`, `tests/test_j54.py`; may delete `j54/contracts.py` | nothing; uses the evaluator only through its interface (import it where needed; if the module is not there yet, the snapshot's `bar` / `heat` are `None` and the Hot Purge picks among the three *lowest* ranks until it is) |
| **C. Surface** | `j54/public.py` (new), `j54/parts.py`, the layout in `modes/__init__.py`, `agent/observation.py` if a field is missing, `ai/hosts/j54.json`, `AGENTS.md`, `docs/AGENT_GUIDE.md`, `docs/PLAYER_GUIDE.zh-CN.md`, `docs/design/TABLE_UI.md` | A and B merged |

A and B run in parallel in their own worktrees; C after both are merged.
The simulator adapter (`black-jack-sim/bjsim/adapter.py`) is checked once C
is in.
