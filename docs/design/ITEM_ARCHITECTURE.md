# Products, choices and moves: the item architecture

Status: the contract for every table that sells or applies its own goods.
Implemented for Poker Head's build table (`chaos_blackjack/poker_head/`):
`catalog.py`, `ownership.py`, `effects.py`, `items.py`, `context.py`,
`evaluation.py`, `public.py`, `parts.py`, `table.py`. Choices, moves and the
explicit table hooks are shared (`app/choice.py`, `app/products.py`,
`app/table_mechanics.py`, `gui/scenes/choice.py`). J-54's contracts and the
classic item plugins still use their older paths (see section 9). Read this
before adding a product, an effect, a table action or a GUI panel for one.

`poker_head/catalog.py` keeps its compact `PRODUCTS` rows (kind `item`,
phases `"B"`/`"P"`) because the codex reference reads them; each row is also
registered in `app/products.py` as a `ProductDef` (kind `consumable`, phase
names), which the controller, GUI and agent read.

## 1. Goals

- A new product is **one catalog row plus one small handler**, never a branch
  in a shared method, the controller or the GUI.
- The GUI and the agent CLI show **the same legal moves**, derived from one
  function, with the same reasons for what is disabled.
- A choice (a core, a replacement, a target) **changes nothing until it is
  confirmed**; cancelling costs nothing.
- Public views carry **only what a player at the table may see**; private
  state (frozen deck order, private financial outcomes) never leaves the table.
- Classic play, J-54 and the legacy mode-less `--chaos` run exactly as before.

## 2. Layers

```
GUI / agent  --reads-->  GameView (moves, choice, typed table snapshot)
     |                          ^
     +--- sends a Move ---> GameController  (the only entry point and referee)
                               |
                 Choice  (pending question; nothing applied before `choose`)
                               |
                 Effects (passive hooks)  +  Item handlers (active uses)
                               |
     Ownership: Holdings (owned instances) / Loadout (core, slots) / Ledger (cash, positions)
                               |
                 Catalog: ProductDef rows (data; numbers come from the balance profile)
```

Each layer depends only on the layers below it. Handlers and effects talk to
the round through a narrow context object, never through the controller's
private members.

## 3. Catalog (`app/products.py`)

```python
@dataclass(frozen=True)
class ProductDef:
    id: str            # unique across the game, prefixed per table (ph_*, j54_*)
    name: str          # English UI name
    kind: str          # consumable | permanent | finance | core | contract
    description: str   # English effect text, one sentence
    style: str = ""    # build style / pool tag (long, retreat, exact, double, finance, common)
    phases: frozenset[str] = frozenset()   # where a consumable may be used: betting, player_turn
    target: str = ""   # what a use needs to choose: "", rule, holding, core
```

- `register_products(defs)` adds rows; `product(id)` looks one up. Name,
  description, kind and the phase label ("Before betting", "On your turn",
  "Before betting or on your turn", "Passive") always come from here.
- Prices and effect numbers live in the balance profile
  (`shop_item.price` / `params`, `mode.<id>.*` settings); the catalog never
  holds numbers.
- Tables declare which products their shop rolls; the controller does not
  hard-code pools.
- `ProductDef.group` (permanent, consumable, special = cores, money
  products, contracts and system items such as the core invitation) sets the
  GUI colour: icons are tinted at load time (`AssetSpec.tint`) and slots, list
  entries, shop cards and choice options are framed in `theme.GROUP_COLORS`.
- Poker Head's testing switch `mode.chaos.unlock_all` (off in the shipped
  profile) puts every product on the shelf and lifts the Private Account
  requirement; rules that are not unlocks (one copy of a permanent, one loan,
  no amendment without a core) still apply.

## 4. Ownership

| Object | Holds | Rules |
|---|---|---|
| `Holdings` | Owned consumables as instances: `uid`, product id, actual price paid, round bought, optional data (e.g. offered cores) | `run.items` is derived from it (compatibility view), never edited separately. Buy-back refunds a specific instance's `paid`. |
| `Loadout` | Core, "no core" flag, equipped permanents, slot count, per-product counters | Same product never twice. Counters are keyed by product, not by slot, so unequipping and re-equipping cannot reset a once-per-run or once-per-round use. Changing core keeps everything else. |
| `Ledger` | Open positions (`uid`, product, principal, debt, rounds left, wins), settled keys | Net assets = cash + open principal − all debt still owed. Unrealised profit is never counted. Every cash posting has a key; posting a key twice is an error. |

## 5. Effects and item handlers

**Passive effects** (cores and permanents, plus this round's prepared
consumables) implement only the hooks they need from a fixed list:

| Hook | Used for |
|---|---|
| `bust_limit(limit) -> int` | Room to Breathe, Temporary Allowance |
| `card_value(card, value) -> int` | Court Discount (player only) |
| `recognize(total) -> int` | Almost Perfect (20/22 count as 21) |
| `opening(state) -> state` | Comeback Ace, before naturals are checked |
| `natural(player, dealer) -> outcome or None` | Borrowed Glory |
| `player_turn()` | Sleeve Mark, Open Audit |
| `settle(settlement)` | multi-card rewards, Perfect Payout, Shared Risk, High Stakes, Recovery Receipt |
| `surrender_rate(rate) -> int` | Graceful Retreat, Retreat Discount, Loss Waiver |
| `double_multiplier(m) -> int` | Fourfold Ticket |
| `actions(actions)` | Exit Clause (late surrender), Raise Permission (late double) |
| `table_moves()`, `perform(action)` | Spare Sleeve (a once-per-round table action) |
| `removed()` | Recovery Receipt, Comeback Ace drop what they held when replaced |
| `price(kind, price) -> int`, `shop_slots(n)`, `free_rerolls(n)` | Purchasing Privilege, Private Account, Priority Exchange |
| `unlocks_finance`, `suppresses_chaos` (flags) | Private Account, Silence Seal |
| `investment_profit(profit) -> int` | Yield Privilege |

The table folds every active effect over each hook in a fixed order (core,
then permanents in slot order, then preparations). Player-only effects read
`actor` and leave the dealer's values alone.

**Active consumables** implement:

```python
class ItemHandler:
    def usability(self, ctx) -> Usability   # ok + an English reason when not
    def targets(self, ctx) -> tuple[ChoiceOption, ...]   # only for targeted items
    def apply(self, ctx, target: str) -> str            # the result message
```

`usability` is checked before `targets` and `apply`; a failed check spends
nothing. The phase test comes from `ProductDef.phases` and is done once by
the table, not by each handler. Handlers change the round only through the
context: `ctx.state` / `ctx.set_state`, `ctx.reveal_hole()`,
`ctx.add_cash()`, `ctx.value(hand, actor)`, `ctx.message()`,
`ctx.prepare(id)`, `ctx.ask(choice)`, `ctx.surrender()` (`poker_head/context.py`).

## 6. Choices (`app/choice.py`)

```python
@dataclass(frozen=True)
class Choice:
    kind: str                         # e.g. core, replace, target
    prompt: str
    options: tuple[ChoiceOption, ...] # id, label, description
    cancellable: bool = True
    payload: dict                     # what to do on `choose` (JSON-safe, saved)
```

- A command that needs a decision calls `controller.ask(choice)` and returns
  without changing anything. The controller keeps one pending choice, saves
  it with the run and publishes a `choice_opened` notice.
- While a choice is pending the only moves are `choose <option>`,
  `cancel` (when cancellable) and `save`.
- `choose` hands the choice and the option to the table
  (`resolve_choice`), which then performs the purchase or use as if it had
  been sent with that target. `cancel` drops the choice and nothing else.
- Commands that already carry the answer (`buy X --replace Y`,
  `use_item X --target T`) skip the question.
- The opening invitation (two cores or 30 chips) is a choice that cannot be
  cancelled.

## 7. Moves: one source of legality

`GameController.moves()` returns `Move(action, arg, label, enabled, reason)`
for everything a player could do now: bet, every shop offer, reroll, every
held item, hit / stand / double / surrender, every choice option, cancel,
next round and table actions (e.g. Spare Sleeve). `available_actions` is the
set of enabled actions, plus the automatic ones (`resolve_chaos`,
`dealer_step`, `save`).

- GUI: shop buttons, item slots, choice buttons and table action entries take
  `enabled` and `reason` from the matching move.
- Agent: `legal_actions` are the command names of enabled moves; items, shop
  offers and the choice show the same reasons.
- A test asserts that every enabled `Act` the GUI's parts produce is an
  enabled move, and the reverse for items, offers and choices.

Table-specific moves come from `TableMechanics.table_moves()` and run
through `controller.perform(action, arg)`.

## 8. Views

- `GameView.moves`, `GameView.choice` (a `ChoiceView` or None) and
  `GameView.table_public` (a frozen, table-specific dataclass with
  `to_dict()`) replace untyped dictionaries.
- Parts read only the view and the snapshot, never the table object.
- The snapshot is built from the table's state at the moment of the call;
  later changes to the table do not reach it, and editing it changes nothing.
- A test serialises the snapshot and the agent observation and checks that no
  undealt card and no private financial outcome appears.

## 9. Table mechanics interface

`app/table_mechanics.py` declares every hook the controller calls, each with
a neutral default. The controller never uses `getattr` to discover an
optional hook. Hooks added for the build table: `entered_betting`,
`before_bet` (a frozen deal), `before_naturals`, `natural_outcome`,
`settlement`, `entered_player`, `should_chaos`, `double_multiplier`,
`surrender_refund`, `persistent_rules`, `product` (the catalog row an id
stands for here, e.g. a starter alias), `purchase` (returns False for "not
mine"), `use_item` (returns None for "not mine"), `item_usability`,
`offer_price`, `offer_usability`, `reroll_price`, `rerolled`,
`resolve_choice`, `table_moves`, `perform`, `public`.

Controller entry points for tables and handlers: `ask`, `choose`,
`cancel_choice`, `moves`, `item_usability`, `offer_usability`,
`base_actions` (hand actions before any item check), `hand_value(hand,
actor)` and `check_terminal`.

Not migrated yet (planned, optional):

- J-54's contracts become `ProductDef(kind="contract")` rows with handlers
  over `DeckOp`; J-54's parts read a `J54Public` snapshot.
- Classic item plugins (`items/*.py`) keep the registry `ItemProtocol`;
  wrapping them as handlers would let them show phase labels too.

## 10. Adding things

| To add | Do |
|---|---|
| A consumable | Catalog row; handler class in `poker_head/items.py` registered under its id; `shop_item` seed row with price and params; tests for its usability and effect. |
| A permanent or core | Catalog row; effect class in `poker_head/effects.py` implementing its hooks; seed row; tests. |
| A financial product | Catalog row; its payout rule in `PokerHeadTable.after_settle` (positions live in `ownership.Ledger`); seed row; ledger tests (no double posting, net assets). |
| A table action | A `Move` from `table_moves()` and its branch in `perform()`; `listed=False` when a part shows it next to its object (e.g. Discard on each permanent in the bag) instead of in `core.actions`. |
| A goal that is not the bankroll | `TableMechanics.goal_progress(run)` -> `(label, value, target)`; the top bar then shows the bankroll alone with the goal bar under it. |
| A panel | A part reading `view.table_public`, placed by the mode's layout. |
| A question | `controller.ask(Choice(...))` plus its branch in `resolve_choice`. |

## 10a. Environment rules (Poker Head)

The dealer's rules are data too (`poker_head/environment.py`): a type, explicit
parameters, a duration and an age; text, signature and effects come from that
data. Hand rules act inside the one evaluation (`evaluation.py`); money, item,
shop and display rules act through the table (`settlement`, `item_usability`,
`offer_price`, `hidden_player_cards`). The offline director (`director.py`)
adds or replaces at most one rule per round, before betting, and its numbers
are `mode.chaos.director.*` settings. Tables show their own rules through
`TableMechanics.active_rules()` (a `RuleView` with scope, effect, rounds left,
removal and whether it is silenced).

## 11. Saves and randomness

- Every object above has `to_dict` / `from_dict` with a version; unknown
  versions are rejected, missing optional fields take defaults.
- Random draws use named, counter-seeded streams
  (`f"{seed}:{stream}:{n}"`), so shopping, rerolling, saving and loading do
  not shift the deal or a stock's private result.
- The frozen deal and private financial results are saved packed, like the
  agent run file's deck order, and never appear in a view.
