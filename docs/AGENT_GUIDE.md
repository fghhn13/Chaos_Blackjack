# Chaos Blackjack — Agent Player Guide

This is the complete guide for an AI agent (typically an LLM driving a shell)
that plays Chaos Blackjack as a player — to test the game, evaluate a strategy
or just play. [AGENTS.md](../AGENTS.md) is the one-page quick reference; this
document explains everything in detail.

Contents: [Setup](#1-setup) · [Commands](#2-commands) · [What happens inside a command](#3-what-happens-inside-a-command) ·
[Observation reference](#4-observation-reference) · [Errors and recovery](#5-errors-and-recovery) ·
[Rules](#6-rules) · [Chaos AI and chaos rules](#7-chaos-ai-and-chaos-rules) · [Items](#8-items) ·
[Worked examples](#9-worked-examples) · [Strategy notes](#10-strategy-notes) ·
[Streaming mode and Python API](#11-streaming-mode-and-python-api) · [Reproducibility, logs and reporting](#12-reproducibility-logs-and-reporting) ·
[Fair play and cost](#13-fair-play-and-cost)

---

## 1. Setup

- Python 3.10+. From the repository root, nothing needs installing to play the agent interface (`pip install -e .` is optional).
- Run every command from the repository root.
- The run is stored in a **state file** between calls. Default: `.agent_runs/current.json` (git-ignored). Use `--state PATH` to keep several runs apart, e.g. one per test case.

## 2. Commands

```bash
python -m chaos_blackjack.agent [GLOBAL FLAGS] <subcommand> [ARGS]
```

Global flags go **before** the subcommand:

| Flag | Effect |
| ---- | ------ |
| `--state PATH` | run file to read / write |
| `--brief` | reply contains only `ok`, `events`, `error` and `obs.{phase, summary, hint, legal_actions, bet_range, last_round, run_end}` — recommended to save tokens |
| `--compact` | single-line JSON |

Subcommands:

| Subcommand | Purpose |
| ---------- | ------- |
| `new [--seed N] [--chaos] [--llm] [--start-money N] [--target-money N] [--max-steps N]` | start a run; **overwrites** the state file and its log |
| `observe` | current observation; changes nothing, not logged |
| `help` | list game commands |
| `bet <amount>` | place a bet (phase `betting`) |
| `act hit` / `act stand` / `act double` / `act surrender` | play your hand (phase `player_turn`) |
| `act use_item <item_id>` | use an item from your inventory (phase `player_turn`) |
| `play [new options]` | streaming JSON-lines mode, see §11 |

`new` options:

- `--seed N` — deterministic shuffle. Omit for a random seed (it is reported in `run.seed`).
- `--chaos` — the Chaos AI may change a rule every round (§7).
- `--llm` — the Chaos AI is a **real, billed** model behind the GPTsAPI relay instead of the offline stub. Needs `GPTSAPI_API_KEY` in `.env`. Only use it when your instructions say so.
- `--start-money N`, `--target-money N` — change the economy (defaults 100 → 400).
- `--max-steps N` — cap on accepted `bet` / `act` commands (default 2000).

Exit codes: `0` accepted, `1` rejected by the game (`ok: false`), `2` usage problem (no run file, bad state file, `--llm` without a key).

## 3. What happens inside a command

You only act at decision points. Everything in between runs automatically
inside the command you sent, and its events are returned in `events`:

```text
bet <n> ──► deal 2+2 cards
           └► [chaos mode] Chaos AI acts once (may add one rule or use one of your items)
           └► naturals check: player and/or dealer two-card 21 ends the round at once
           └► phase = player_turn  (or straight to settlement)

act hit      ──► one card; if you bust the round settles immediately
act double   ──► bet x2, one card, then stand (unless bust)
act stand    ──► dealer reveals and draws to 17+, round settles
act surrender──► round settles, half the bet returned

settlement   ──► bankroll, win streak, maybe an item reward
             └► run over (target reached / bankrupt)?  phase = run_over
             └► otherwise next round: phase = betting, obs.last_round = result
```

So a full round is usually `bet` → zero or more `act` → back at `betting`.

## 4. Observation reference

Every reply is `{"ok", "events", "obs", "run"}` (+ `"error"` when `ok` is false).
`obs.schema` is `1`; it will be incremented if the shape changes.

| Field | Meaning |
| ----- | ------- |
| `phase` | `betting`, `player_turn` or `run_over` (the only phases you will see) |
| `legal_actions` | exactly what you may send now: `["bet"]`, a subset of `hit stand double surrender use_item`, or `[]` |
| `hint` | the next command in plain words, e.g. `Your move: act hit \| stand` |
| `summary` | one paragraph describing the table; enough to decide on its own |
| `round` | round number |
| `bankroll`, `target` | current money and the goal |
| `bet_range` | `[min, max]` in `betting`, else `null` |
| `bet` | the bet on the current hand (after a double: the doubled amount) |
| `win_streak`, `reward_every` | consecutive wins so far / wins needed for an item |
| `you` | `{"cards": [...], "total": n}` during a hand, else `null` |
| `dealer` | `{"cards": ["K♣", "??"], "total": null}` while the hole card is hidden |
| `items` | `[{"id", "count", "help"}]` — your inventory |
| `chaos` | `{"enabled", "budget", "active_rules": [{"id", "help"}]}` |
| `action_help` | one-line explanation of each legal action |
| `last_round` | result of the most recent round (see below), `null` once you bet again |
| `run_end` | `{"kind": "victory" \| "defeat", "message"}` when the run is over |

Cards are `<rank><suit>`: ranks `A 2 … 10 J Q K`, suits `♠ ♥ ♦ ♣` (♥ ♦ are red). `??` is the face-down dealer card.

**Totals already apply every active chaos rule** — always use `you.total` rather than your own arithmetic.

`last_round` fields: `round`, `outcome` (`player`, `dealer`, `push`, `blackjack`, `surrender`), `player_total`, `dealer_total`, `player_bust`, `bet`, `delta` (bankroll change, signed), `money_after`, `reward` (item id or `null`), `doubled`, `dealer_blackjack`, `your_cards`, `dealer_cards` (both final hands, fully revealed).

`events` are short English lines in order, for example:
`Round 2 started, bet 10`, `⚡ Chaos Effect Triggered: rank adjustment -1 per card`,
`Chaos AI says: ...`, `You draw: Q`, `Dealer draws: 8`, `Dealer stands at 18.`,
`Dealer busts.`, `💀 BUST!`, `♠ BLACKJACK!`, `Dealer has blackjack.`,
`Double down! Bet is now 40.`, `You surrender. 10 returned.`,
`Next card rank: 7` (item result), `Reward earned: peek`.
Treat them as narration; the authoritative state is `obs`.

## 5. Errors and recovery

A rejected command changes nothing (no step is counted). Read `error.legal_actions` and send a valid command.

| `error.code` | Typical cause | What to do |
| ------------ | ------------- | ---------- |
| `illegal_action` | action not allowed now (e.g. `double` after hitting, `act` while betting), bet outside `bet_range`, item you don't own or that cannot be used | pick from `legal_actions` / `bet_range` |
| `invalid_argument` | missing or non-integer `amount`, missing item id, unknown action name | fix the argument |
| `unknown_command` | streaming mode: unknown `cmd` | use `observe`, `bet`, `act`, `help` |
| `run_over` | the run has ended | start a new one with `new` |
| `step_limit` | `--max-steps` reached | start a new run |
| `usage` (exit 2) | no run file yet, corrupt run file, `--llm` without a key | run `new`; check the path; drop `--llm` |

## 6. Rules

Economy

- Start with 100, win at 400 (bankroll `>=` target), lose at 0 or when you cannot place a legal bet (you need at least 2 to bet 1).
- Bet: integer from 1 to `floor(bankroll / 2)`. You can never bet everything.

Card values

- 2–10 face value, J/Q/K = 10, A = 11, but an Ace drops by 10 (to 1) whenever the hand would otherwise bust under the active bust limit (21, or 18 under Fragile Bust).
- Chaos rules change card values before summing, and shift **both** Ace values: under "values −1" an Ace is 10 or 0, under Suit Power a red Ace is 12 or 2. Aces stay soft under every rule.

Round

- You and the dealer get two cards; the dealer's second card is face down.
- Natural blackjack = exactly two cards totalling 21 (after chaos rules, and not a bust under them). Player natural pays **3:2**, rounded down (bet 5 → +7). Dealer natural ends the round before you act: you lose the bet, unless you also have a natural (push).
- `double` and `surrender` are only legal on your first decision (exactly two cards). Using an item does not count as a decision.
- Double: bet ×2, one card, then stand. If that card busts you, you lose the doubled bet.
- Surrender: you get `floor(bet / 2)` back, i.e. lose `bet - floor(bet/2)` (bet 15 → −8).
- Dealer draws until 17 or more and stands on any 17 (no soft-17 rule).
- Settlement: win `+bet`, loss `-bet`, push `0`, blackjack `+floor(bet*3/2)`.
- Bust (over 21, or over 18 under Fragile Bust) on your own hit/double settles the round immediately; the dealer does not draw.
- Win streak: each win or blackjack adds 1; anything else resets it. At 2 you receive a random item (`peek`, `shield` or `swap`) and the streak resets.

## 7. Chaos AI and chaos rules

With `--chaos`, after every deal the Chaos AI gets **one** chance to act, before the naturals check and before your first decision. It can:

- **apply one rule** for the rest of the round (listed in `obs.chaos.active_rules`, announced in `events`), or
- **use one of your items** (it is consumed — yes, it can burn your items), or
- do nothing.

At most one rule is active at a time; rules are cleared when the next round is dealt. Every action is checked against a permission profile; blocked actions show up as events and have no effect. With the offline stub the AI always applies "values −1"; with `--llm` a real model chooses (and may add a line of narration).

| Rule id | Effect | Implications |
| ------- | ------ | ------------ |
| `modify_card_value` | every card's value shifts by `delta` (stub: −1) | totals drop (an Ace is 10 or 0); more room before busting |
| `great_crash` | 10, J, Q, K are worth 1 | high cards stop being dangerous; naturals become impossible |
| `odd_even_chaos` | 2/4/6/8 +2 each, 3/5/7/9 −1 each | even cards push you toward bust |
| `suit_power` | red cards (♥ ♦) +1, black (♠ ♣) −1 | read suits, not just ranks |
| `fragile_bust` | bust threshold is 18 for both sides | stand earlier; dealer busts on 19+ too; a 21 is a bust, so no naturals |
| `reverse_bust` | the player's bust no longer counts as an automatic loss | if you bust on a hit the round still ends at once, but totals are compared and the higher total wins |
| `tiebreaker_shift` | ties go to the dealer or to the player instead of a push (see the rule's `help`) | a tie is no longer safe (or becomes a win) |

## 8. Items

Use with `act use_item <id>` during `player_turn`. Each use consumes one copy. Information items report through `events`.

| Item id | Effect |
| ------- | ------ |
| `peek` | reveals the rank of the next card in the deck |
| `fate_oracle` | reveals the ranks of the next 3 cards |
| `danger_radar` | how many 10/J/Q/K remain in the deck, and the ratio |
| `hole_card_hacker` | reveals the dealer's face-down card |
| `swap` | replaces your first card with the top card of the deck |
| `shield` | currently no game effect |

Revealed ranks never change `obs` (the hole card stays `??` there); remember them yourself.

## 9. Worked examples

Real transcripts (`--brief --compact`, `run` field omitted).

**A plain round, seed 7**

```text
$ python -m chaos_blackjack.agent new --seed 7
{"ok":true,"events":[],"obs":{"phase":"betting","summary":"Round 1. Bankroll 100/400.","hint":"Place a bet: bet <amount> with 1 <= amount <= 50.","legal_actions":["bet"],"bet_range":[1,50]}}

$ python -m chaos_blackjack.agent --brief --compact bet 20
{"ok":true,"events":["Round 1 started, bet 20"],"obs":{"phase":"player_turn","summary":"Round 1. Bankroll 100/400. Bet 20. You: 8♣ 3♥ = 11. Dealer: K♣ ?? = ?.","hint":"Your move: act hit | stand | double | surrender","legal_actions":["hit","stand","double","surrender"]}}

$ python -m chaos_blackjack.agent --brief --compact act hit
{"ok":true,"events":["You draw: Q"],"obs":{"phase":"player_turn","summary":"Round 1. Bankroll 100/400. Bet 20. You: 8♣ 3♥ Q♥ = 21. Dealer: K♣ ?? = ?.","hint":"Your move: act hit | stand","legal_actions":["hit","stand"]}}

$ python -m chaos_blackjack.agent --brief --compact act stand
{"ok":true,"events":["Dealer draws: 8","Dealer busts."],"obs":{"phase":"betting","summary":"Round 2. Bankroll 120/400.","hint":"Place a bet: bet <amount> with 1 <= amount <= 60.","legal_actions":["bet"],"bet_range":[1,60],
 "last_round":{"round":1,"outcome":"player","player_total":21,"dealer_total":23,"player_bust":false,"bet":20,"delta":20,"money_after":120,"reward":null,"doubled":false,"dealer_blackjack":false,"your_cards":["8♣","3♥","Q♥"],"dealer_cards":["K♣","5♥","8♦"]}}}
```

(Doubling on 11 would have paid +40 here.)

**Chaos mode, seed 11 — a rule changes the maths**

```text
$ python -m chaos_blackjack.agent new --seed 11 --chaos
$ python -m chaos_blackjack.agent --brief --compact bet 25
{"ok":true,"events":["Round 1 started, bet 25","⚡ Chaos Effect Triggered: rank adjustment -1 per card"],"obs":{"phase":"player_turn","summary":"Round 1. Bankroll 100/400. Bet 25. You: J♠ 7♠ = 15. Dealer: 7♦ ?? = ?. Active chaos rules: Rank values shifted by -1 per card (until cleared).", ...}}

$ python -m chaos_blackjack.agent --brief --compact act double
{"ok":true,"events":["Double down! Bet is now 50.","You draw: Q","💀 BUST!"],"obs":{"phase":"betting","summary":"Round 2. Bankroll 50/400.", ...,
 "last_round":{"outcome":"dealer","player_total":24,"bet":50,"delta":-50,"doubled":true,"your_cards":["J♠","7♠","Q♣"],"dealer_cards":["7♦","5♠"], ...}}}
```

J♠ 7♠ is 15, not 17, because of the −1 rule. Doubling on 15 was a bad idea.

**A rejected command**

```text
$ python -m chaos_blackjack.agent --brief --compact bet 30        # bankroll 50 -> max 25
{"ok":false,"events":[],"error":{"code":"illegal_action","message":"Invalid bet. Allowed range: 1~25","legal_actions":["bet"]},"obs":{"phase":"betting", ...,"bet_range":[1,25]}}
```

## 10. Strategy notes

Plain blackjack basic strategy is a good baseline when no chaos rule is active (dealer stands on all 17s, no split in this game):

- Hard 17+: stand. Hard 13–16: stand against dealer 2–6, hit against 7–A. Hard 12: stand against 4–6, else hit. 11 or less: hit.
- Double on 11 (except against an Ace), on 10 against 2–9, on 9 against 3–6.
- Soft hands (an Ace counting 11): hit soft 17 or less; stand soft 19+; soft 18 stands against 2–8.
- Surrender hard 16 against 9/10/A and hard 15 against 10.

Chaos adjustments:

- Re-read `you.total` and `chaos.active_rules` after every bet — the rule is chosen after the deal.
- `fragile_bust`: treat 18 as your 21; stand much earlier.
- `great_crash`: 10/J/Q/K are 1 — hitting is cheap.
- `reverse_bust`: a high bust total can still win; compare against the dealer's visible card.
- `tiebreaker_shift`: check whether ties now favour you or the dealer.

Bankroll: you must quadruple your money with bets capped at half your bankroll. Small flat bets are slow; the cap protects you from going broke in one hand but not in three.

## 11. Streaming mode and Python API

**Streaming** — one long-lived process, one JSON command per line on stdin, one compact JSON reply per line on stdout (no state file is written):

```bash
python -m chaos_blackjack.agent play --seed 7 --chaos
```

```text
{"cmd":"observe"}
{"cmd":"bet","amount":20}
{"cmd":"act","action":"hit"}
{"cmd":"act","action":"use_item","item":"peek"}
{"cmd":"new","seed":8,"chaos":true}
{"cmd":"help"}
{"cmd":"quit"}
```

The first reply (the initial observation) is printed before any input is read. Invalid JSON gets `{"ok":false,"error":{"code":"invalid_json",...}}` and the stream continues. `--brief` works here too.

**Python**:

```python
from chaos_blackjack.agent import AgentSession

s = AgentSession.new(seed=7, chaos=True)          # also start_money=..., target_money=...
r = s.execute({"cmd": "bet", "amount": 20})
r = s.execute({"cmd": "act", "action": "stand"})
saved = s.to_state()                               # JSON-safe dict
s2 = AgentSession.from_state(saved)                # continue later
```

## 12. Reproducibility, logs and reporting

- Same `--seed`, same options and the same accepted commands give exactly the same game, whether you play in one process or one command at a time. (Real-LLM chaos is not deterministic.)
- Each accepted or rejected `new` / `bet` / `act` is appended to `<state>.log.jsonl` (for the default state: `.agent_runs/current.log.jsonl`) with the command, `ok`, error code, events, phase and bankroll. `new` resets the log.
- When you report a problem found while playing, include: the `new` command (seed and flags), the sequence of commands, the reply that looked wrong, what you expected, and the log file path.

## 13. Fair play and cost

- Observations only contain what a player at the table could see. The run file keeps the deck order in a packed field — **do not decode or edit the run file**; use `observe`. Card-revealing items are part of the game and fine to use.
- Do not modify the game code to play; if something seems wrong, report it (§12).
- Without `--llm` nothing touches the network and nothing costs money. With `--llm`, every round costs one chat request (sometimes two). Never print or copy the API key.
