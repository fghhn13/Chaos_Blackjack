# J-54 "Joker Reshuffler": table design

Status: **superseded by v2**, implemented 2026-10-17: the table `j54` now
follows [J54_V2_SPEC.md](J54_V2_SPEC.md) (program of conditions, compute, deck
shaping, the meter and heat map, the Joker capture). This file keeps the
original concept and the v1 demo (concept agreed 2026-10-12; demo v1
implemented 2026-10-13, section 0) for reference. Wiki drafts:
`dealer-j54.html`, `table-j54.html`.

**Direction change, 2026-10-15**: the next version is built from composable
primitives (global sub-mode, draw policies, deck operations, per-side effect
rules, J-54's advantage, goals); the Joker hunt becomes one goal among
several. See [J54_PRIMITIVES.md](J54_PRIMITIVES.md). Sections 1–10 below
describe v1 and the original concept.

Theme: probability, calculation, rebuilding the deck. Poker Head bends the
*rules*; J-54, a clown-shaped calculating machine with a pixel face and a
cold, programmatic voice, changes the *cards*.

## 0. Demo v1 (implemented)

Mode `j54` ("J-54's Table (demo)", series `j54`, host `j54`), unlocked for
everyone. Code: `chaos_blackjack/j54/` (table, contracts),
`rules/plugins/j54_deck.py` (rules), `app/table_mechanics.py` (the hook the
controller calls), `ai/personas/j54.json` + `ai/hosts/j54.json` (host; the
author's 9 portraits). Agents: `python -m chaos_blackjack.agent new --mode j54`.

In v1:

- Persistent deck composition (section 1), saved with the run (`RunSaveData.table`).
- Protocols **Single Capture** and **Capital**, one drawn per run.
- Joker sealed until **Start Experiment** (always on the shelf, takes one of the
  3 slots). Drawn by the player on the deal, a hit or a double: the hand ends at
  once as a push and the run is won. Drawn by the dealer: J-54 swaps in the next
  card, shuffles the Joker back (never on top) and adds low cards. The Joker
  never stays in a hand, so it has no value yet.
- Compute fee before each bet; minimum bet = max(profile minimum, fee).
- Entropy after every round; Freeze skips it.
- Contracts: Low Purge (now), Streamline (next win), High Injection (now),
  Freeze (now), Start Experiment (now). Pending ones show at the table.
- **Deck operations** (`j54/deck_ops.py`): every rule, deck contract, entropy
  and the Joker penalty is data — `when` (now, round_end), `select` (rank:R,
  random_rank, low, high, any, drawn, player_hand, dealer_up, removed), `op`
  (add, remove, copy, move_top, move_bottom, return), `count` (n or all).
  Descriptions are generated. A new rule is a `chaos_rule` row plus a name in
  `rules/plugins/j54_deck.py`; a new deck contract is a `shop_item` row plus
  a name in `j54/contracts.py`. Deleted cards go to a removed pile.
- Chaos rules: Burn Protocol, Sample Injection, Redundancy Purge, Ace
  Injection, Layered Sort (high cards to the bottom of this round's deck),
  Data Backflow (4 removed cards return). Offline Chaos AI only; the LLM may
  pick them but has no J-54 prompt.
- **Deck inspection, always on and truthful**: hover the shoe to see the whole
  deck by rank (plus Joker state and removed cards); click it to pin the view.
  Agents get `obs.table.deck`. The order is never shown. (Lies and challenges
  are postponed.)
- Placeholder icons for contracts, rules, badges and the mode; no J-54 card art.
- **UI** (docs/design/TABLE_UI.md): the right column shows the shoe, a 13-bar
  deck strip, badges (Joker state or capital progress, compute fee and the
  next step, pending contracts, freeze) and item slots; the run panel adds
  Deck and Contracts tabs and a Run tab with the protocol and the fee table.

Not in v1: lies and challenges (section 6), Double Capture,
Eradication, Joker values, targeted contracts or items, a J-54 LLM prompt,
upgrades / achievements / cosmetics, simulator support, player-guide and
wiki pages.

v1 numbers (`seed/default.sql`, `mode.j54.*` settings and `j54_*` rows):

| Setting | Value |
|---|---|
| Capital target | 250 |
| Compute fee | 0, 1, 2, 4, 8 per 4-round step, then doubling |
| Entropy | 1 low card per round, 2 after the experiment starts |
| Dealer Joker penalty | 1 low card |
| Minimum deck | 12 cards |
| Shop | 3 offers, restocks every round |
| Contracts | Low Purge 10 (6 low cards, now), Streamline 20 (5 random, next win), High Injection 20 (3 high, now), Freeze 15 (3 rounds), Start Experiment 50 |

First pass with a scripted bot (200 seeds; basic strategy, buys Low Purge
from surplus, starts the experiment at <= 38 cards, bets up to half the
bankroll on a rich deck): Single Capture won ~23 % (median round 12), Capital
~19 % but with a **median win in round 4**; never buying won 0 % / ~2 % and died
around round 18. Capital therefore still allows lucky early wins (open
question below); capping bets at 25-30 % did not move its wins past round 5-6.
With Layered Sort and Data Backflow added: ~15 % / ~13 %, same shape. Measured edge of the bot's play: -1.3 %
per hand on a full deck, about 0 with 8 low cards removed, about +5 % with 16
removed. Lessons: a fee above ~2 per round outweighs the deck edge at these
bankrolls, so entropy (not the fee) carries most of the anti-stall pressure;
contracts must be cheap and restock often or shaping never pays back.

## 1. Decisions

| Topic | Decision |
|---|---|
| Persistent deck | The deck's **composition** lasts the whole run. Each round still shuffles the whole deck and deals from it (as today); rules and contracts change which cards it holds. No shoe or discard pile in v1. |
| Starting deck | Standard 52 cards, no Joker. Jokers enter only through the run's protocol (section 3). |
| Physical cards only | J-54 never fakes probabilities: every effect adds, removes or moves real cards. `peek`, `fate_oracle`, `danger_radar` stay truthful; a seed replays a run exactly. |
| Win condition | A **protocol** drawn at random per run and shown at the start (section 3). |
| Loss condition | Bankrupt, or unable to pay the next round's compute fee plus the minimum bet. Same for every protocol. |
| Chips | Life and budget, not the goal (except the Capital protocol). Spent on the compute fee and on **run contracts** (section 5). |
| Two phases | Early game: shape the deck in your favour to secure the economy. Late game: start the experiment and complete the protocol. The player chooses when. |
| Anti-rush | Winning fast is hard: Jokers start sealed and cost an expensive contract to release, so round 1 can never be won by luck. |
| Anti-stall | Idle rounds cannot win: the compute fee rises and J-54 adds low cards every round (entropy), which hurts both the economy and the protocol. |
| Deck info | Clicking J-54's portrait reports the deck, once per round. J-54 may lie; the player may challenge (section 6). |

## 2. Run loop

```
start ─▶ early: build the deck ─▶ start the experiment ─▶ late: complete the protocol ─▶ win / lose
         (earn chips, cut low cards)  (player picks the moment)  (J-54 fights back)
```

Start: 52-card deck, 100 chips, random protocol announced, J-54 intro.

Each round:

1. Pay the **compute fee** (rises with the round number).
2. **Contract shop** (betting phase): 3 offers, one reroll; reuses the existing shop.
3. Optional: inspect the deck via the portrait; optional challenge.
4. **Bet**: minimum bet = max(5, compute fee); maximum stays half the bankroll.
5. Deal → naturals settle → J-54 Chaos rule → player turn → dealer → settle.
6. End of round, in order: fire contracts whose trigger was met; apply burn
   effects; check the protocol; **entropy**: J-54 adds low cards.
7. Check the loss condition.

Target pacing (to tune in the simulator): a typical win in rounds 12–18;
the fee makes round ~25 a soft cap; wins in 8 rounds or fewer are rare. A
rating or achievement may reward fast wins (e.g. protocol done within 10
rounds); no hard round limit.

## 3. Protocols (win conditions)

| Protocol | Jokers | Win | Main levers |
|---|---|---|---|
| Single Capture | 1, sealed until released | The player draws it | Shrink the deck, hit aggressively |
| Double Capture | 2, sealed until released | The player draws both, over the run (a drawn Joker goes to a sample slot) | Same, longer |
| Eradication | 2, in the deck from the start; wild for the dealer | No Joker left in the deck | Targeted deletion, burn contracts |
| Capital | none | Reach 1000 chips | Pure deck economy |

- **Release** ("Start experiment" contract, ~150 chips) puts the sealed
  Jokers into the deck. From then entropy doubles and J-54's rules lean
  against the protocol.
- Only the **player** drawing a Joker counts for Capture. A Joker the dealer
  draws goes back into the deck, and J-54 adds 2–3 cards as a penalty.
- A player-drawn Joker ends the hand immediately with a run win (Single
  Capture) or goes to the sample slot (Double Capture).
- Eradication needs no release; its targeted-deletion contracts take that place.
- The same rules and contracts change meaning by protocol, e.g. Burn shrinks
  the deck under Capture but is the main way to delete a Joker under Eradication.
- Later: "Resonance" (both Jokers in one player hand at once), and a hidden-
  protocol variant to infer through inspection.

Rough odds (player draws ~2.8 cards per round): per-round capture chance ≈
2.8 / deck size, so ~5% at 53 cards, ~9% at 30, ~19% at 15.

## 4. Pressure

Compute fee (placeholder):

| Rounds | Fee per round |
|---|---|
| 1–4 | 2 |
| 5–8 | 5 |
| 9–12 | 10 |
| 13+ | 20, doubling every 4 rounds |

Entropy: at the end of each round J-54 adds 1 low card (2–6); 2 after the
experiment starts. Low cards favour the dealer and grow the deck, so waiting
weakens both the economy and the protocol.

## 5. Run contracts

The J-54 shop sells contracts instead of regular items. A contract has a
**price**, a **trigger**, an **effect** and a **duration**. Prices are fixed
chip amounts (not a percentage of the bankroll), so saving up for a big
contract is a real choice.

| Contract | Price | Trigger | Effect |
|---|---|---|---|
| Streamline | 100 | next won hand | delete 4 random cards |
| Targeted purge | 80 | next won hand | delete 2 cards of a chosen rank |
| Burn guarantee | 60 | next lost hand | burn every card drawn this round |
| Natural clause | 50 | next natural blackjack | delete 6 random cards |
| High injection | 60 | immediate | add 2 aces or 10-value cards (economy) |
| Freeze | 70 | immediate | J-54 adds no cards for 3 rounds |
| Start experiment | ~150 | immediate | release the sealed Jokers |
| Eradication clause | 120 | draw a Joker and win that hand | delete that Joker (Eradication only) |

Random deletion never removes a Joker under Capture protocols; under
Eradication it can (a good gamble).

Deck composition is the player's edge: because the full deck is reshuffled
every round, more 10-value cards and aces mean more 3:2 naturals and more
dealer busts. Cutting low cards early also shrinks the deck for the Joker
hunt later, so the two phases reinforce each other.

Regular items are not sold here; they are the reward for a correct
challenge (section 6).

## 6. Deck inspection and challenges

- Click J-54's portrait: once per round, it reports deck size, count per
  rank and Jokers left in the deck.
- With a small chance (~15%) the report lies by changing one number. The lie
  only touches numbers the player could compute (start deck + announced
  changes + cards seen), so careful players can always catch it. A lie about
  Jokers left is allowed (rare).
- The player may answer "That's wrong" once per report. Correct: a random
  item. Wrong: lose ~10% of the bankroll (minimum 5), so blind challenges have
  negative value.
- Whether J-54 lies comes from the seeded RNG, never from the LLM; the LLM
  only voices the line.
- Agent CLI: new commands `inspect` and `challenge`; observations never show
  whether a report was true.

## 7. Chaos rules (first batch)

All announced publicly when applied.

| Rule | Effect |
|---|---|
| Burn protocol | Cards drawn this round are removed from the deck after settling (Jokers excluded under Capture) |
| Sample injection | Add X (2–4) cards of one rank |
| Redundancy purge | Remove X cards of one rank |
| Ace injection | Add 1–2 aces |

Mode rule pool: these deck rules only (perhaps one existing rule). The
offline stub's weights depend on the protocol (more injection under Capture,
Joker copying only as J-54's counter under Eradication) and alternate
directions so the deck does not drift one way for long.

## 8. Chaos AI and host

- Mode: new series `j54`, `GameMode(id="j54", host="j54", ai_id=...)` per
  `AI_MODES.md` section 6; line library `ai/hosts/j54.json`.
- The LLM may see deck **composition**, never deck **order**; positions come
  from the seeded RNG, so the dealer cannot stack the deck.
- Portraits (`J54_expressions_512.zip`, 512×512 RGBA) and moods:

| Image | Like Poker Head's | Used for |
|---|---|---|
| `grand_welcome` | `welcome` | intro |
| `resting_mania` | `neutral` | idle |
| `card_reveal` | `present_card` | deck report, deck changes |
| `secretive_trick` | `hidden_card` | Chaos rule applied |
| `paranoid_analysis` | `suspicious` | player inspects or deletes |
| `guarded` | `puzzled` | player on a winning streak |
| `irritated` | `displeased` | player wins the run, lie caught |
| `glitching_frenzy` | `startled` | Joker appears, wrong challenge |
| `obsessive_lecture` | (new) | `summary_mood`, rules summary |

## 9. Implementation hooks

- `RunState`: deck composition, sealed Jokers, sample slot, pending
  contracts. `GameLoop.new_round` builds the deck from the composition
  instead of `_standard_deck()`.
- `RunConfig.objective` / `RunState.objective` already exist (only
  `double_money` today): register protocols as objectives.
- Items and contracts that pick a rank or card need a target argument:
  GUI picker and `act use_item <id> <arg>` in the agent CLI.
- Save, agent run file and simulator adapter (`bjsim/adapter.py`) must
  carry the persistent deck.
- Balance values go into the balance profile (seed SQL), not code.

## 10. Open questions

- Contracts: wait for a trigger, take effect at once, or both kinds? Do
  unfired contracts expire?
- Eradication: can the player use a drawn Joker (e.g. as a wild card) before
  it goes back into the deck?
- Starting chips vs the first contract's price (100 → can the player afford
  anything before winning a few hands?).
- Protocol choice: always random, or selectable after unlocking?
- Unlock condition for the table, and its rewards (deck, table cosmetics).
- Exact numbers: fee curve, entropy, lie chance, challenge penalty, prices.
- Capital protocol: a few lucky doubles reach the target by round 4-6, against
  "fewer rounds = harder". Options: the goal only counts from round N, a target
  that must be held for several rounds, or Capital only as a late protocol.
