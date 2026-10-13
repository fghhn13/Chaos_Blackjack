# Agent quick reference

Chaos Blackjack is a blackjack run where an AI dealer may bend the rules. This
file tells an agent how to **play the game through the command line** (no GUI,
no screenshots) and how to work in the repo safely. Python 3.10+, no extra
packages needed to play.

**Full guide** (turn lifecycle, every observation field, chaos rule and item
catalog, worked transcripts, strategy, reporting): [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md).

## Play as an agent

Each command is one shell call. The run is saved to a state file between calls
(default `.agent_runs/current.json`; override with `--state PATH`, placed
**before** the subcommand). Every reply is JSON.

```bash
python -m chaos_blackjack.agent new --seed 7          # start a run (overwrites the run file)
python -m chaos_blackjack.agent observe               # look at the table, changes nothing
python -m chaos_blackjack.agent buy peek              # buy a shop item (betting phase)
python -m chaos_blackjack.agent reroll                # roll the shop's stock again (once per stock)
python -m chaos_blackjack.agent bet 20                # place a bet
python -m chaos_blackjack.agent act hit               # hit | stand | double | surrender
python -m chaos_blackjack.agent act use_item peek     # use an item from your inventory
python -m chaos_blackjack.agent --brief act stand     # smaller reply (recommended)
```

`new` options: `--seed N` (same seed + same commands = same game), `--chaos`
(the Chaos AI changes rules each round), `--llm` (the Chaos AI is a real,
**billed** model instead of the offline stub — only use when told to),
`--start-money N`, `--target-money N`, `--max-steps N`, `--profile NAME` (a balance
profile in `data/game.db`; default `$CHAOS_PROFILE` or `default`), `--mode ID`
(a game mode; `j54` is J-54's deck table, a demo — see below).

Global flags: `--brief` (only summary / hint / legal actions / results),
`--compact` (single-line JSON), `--state PATH`.

### The loop

1. Read `obs.hint` and `obs.legal_actions`.
2. Send exactly one of the legal actions.
3. Read `events` (what just happened) and the new `obs`.
4. Repeat until `obs.phase == "run_over"`.

You only ever act in three phases; everything else (Chaos AI turn, dealer
drawing, moving to the next round) happens automatically inside your command:

| `obs.phase`   | You send                          |
| ------------- | --------------------------------- |
| `betting`     | `bet <amount>` within `obs.bet_range`; optionally `buy <item>` or `reroll` first (see `obs.shop`) |
| `player_turn` | `act <action>` from `obs.legal_actions` |
| `run_over`    | nothing — read `obs.run_end`; `new` to play again |

### Reply shape (schema 2)

```json
{
  "ok": true,
  "events": ["Round 1 started, bet 20", "You draw: Q"],
  "obs": {
    "schema": 2,
    "phase": "player_turn",
    "legal_actions": ["hit", "stand"],
    "hint": "Your move: act hit | stand",
    "summary": "Round 1. Bankroll 100/300. Bet 20. You: 8♣ 3♥ Q♥ = 21. Dealer: K♣ ?? = ?.",
    "bankroll": 100, "target": 300, "bet": 20, "bet_range": null,
    "you": {"cards": ["8♣", "3♥", "Q♥"], "total": 21},
    "dealer": {"cards": ["K♣", "??"], "total": null},
    "items": [{"id": "peek", "count": 1, "help": "Reveal the rank of the next card in the deck."}],
    "shop": null,
    "chaos": {"enabled": true, "budget": 4, "active_rules": [{"id": "modify_card_value", "help": "..."}]},
    "action_help": {"hit": "take one more card", "stand": "end your turn; the dealer plays"},
    "last_round": null,
    "run_end": null
  },
  "run": {"seed": 7, "steps": 2, "state_file": "..."}
}
```

- Cards are `<rank><suit>` (`A`, `2`–`10`, `J`, `Q`, `K`; `♠ ♥ ♦ ♣`). `??` is the dealer's face-down card; its total is `null` until revealed.
- `obs.you.total` already includes active chaos rules — trust it over your own arithmetic.
- After a round settles, the next `obs` is `betting` and `obs.last_round` holds the result: `outcome` (`player` / `dealer` / `push` / `blackjack` / `surrender`), `delta` (bankroll change), both final hands, `doubled`.
- While betting, `obs.shop` is `{"offers": [{"item", "price", "sold", "affordable", "help"}], "restock_in": n, "reroll_price": n | null, "reroll_affordable": bool}`; `null` in other phases.
- On failure `ok` is `false` and `error` is `{code, message, legal_actions}`; the state is unchanged, so fix the command and retry. Codes: `illegal_action`, `invalid_argument`, `unknown_command`, `run_over`, `step_limit`, `usage`.
- Exit code: `0` ok, `1` command rejected, `2` usage or missing/invalid run file.

### Rules

- Bankroll starts at 100; reach the target (300) to win, or go bankrupt. You need at least 10 chips to bet.
- Bet each round: integer from 5 to half your bankroll (rounded down).
- Win `+bet`, lose `-bet`, push `0`. Original-card natural blackjack (A plus 10/J/Q/K) pays 3:2, rounded down. Both sides' naturals settle before Chaos or player actions.
- `double`: first decision only — bet doubles, you get exactly one card, then stand.
- `surrender`: first decision only — lose half the bet (rounded in the house's favour).
- Dealer draws to 17 and stands on 17+.
- Shop (betting phase only): 3 different items, each buyable once; restocks every 2 rounds. Prices are a percentage of your bankroll when the stock rolls (rounded half up, with a one-chip minimum). `reroll` rolls the current stock again once per stock for 3 chips. A purchase or reroll must leave at least 10 chips. `buy` / `reroll` are in `legal_actions` only when allowed.
- With `--chaos`, the Chaos AI may apply one rule per round, or leave the round calm (e.g. card values −1, ties go to the dealer, bust above 19, a bust becomes a push). Active rules are listed in `obs.chaos.active_rules` with a plain-English `help`.

### J-54's table (`--mode j54`, demo)

The deck lasts the whole run (every round reshuffles all of its cards) and
J-54's Chaos rules add or remove cards instead of changing values. A random
**protocol** is the goal: *Single Capture* (draw the Joker yourself; it starts
sealed until you buy `j54_start_experiment`) or *Capital* (reach the chip
target). A **compute fee** is charged before each bet and grows with the
round; the minimum bet is at least the fee. The shop sells **contracts**
(`buy j54_low_purge`, ...) that change the deck at once or on your next win;
they never enter `obs.items`. `obs.table` = `{"info": {"Protocol", "Joker" or
"Goal", "Deck", "Removed"?, "Fee", "Contracts"?}, "fee": n, "deck": {rank: count}}`
(null at other tables; the deck's make-up is public, its order is not); deck
changes are reported in `events`. Design: [docs/design/J54_TABLE.md](docs/design/J54_TABLE.md).

### Fair play

Observations contain only what a player at the table can see. The run file
stores the deck order in a packed field — **do not decode or edit the run
file**; use `observe`. Items that reveal cards are part of the game.

### Streaming mode (optional)

For a long-lived process: `python -m chaos_blackjack.agent play --seed 7`
reads one JSON command per line on stdin and writes one JSON reply per line:

```text
{"cmd":"buy","item":"peek"}
{"cmd":"reroll"}
{"cmd":"bet","amount":20}
{"cmd":"act","action":"double"}
{"cmd":"act","action":"use_item","item":"peek"}
{"cmd":"observe"}
{"cmd":"new","seed":8,"chaos":true}
{"cmd":"quit"}
```

Streaming mode does not write a run file.

### Python API

```python
from chaos_blackjack.agent import AgentSession

s = AgentSession.new(seed=7, chaos=True)
reply = s.execute({"cmd": "bet", "amount": 20})
reply = s.execute({"cmd": "act", "action": "stand"})
state = s.to_state()                 # JSON-safe; AgentSession.from_state(state) resumes
```

## Working in the repo

- Audio materials, cue ids, notice integration and offline checks: [docs/AUDIO_GUIDE.md](docs/AUDIO_GUIDE.md). `python -m chaos_blackjack.audio validate` needs no pygame or sound device; `preview` explicitly plays sound.
- GUI sound ids, animation timing, offline checks and approved export workflow: [assets/sounds/README.md](assets/sounds/README.md). `python scripts/export_sounds.py --verify` validates delivered clips without raw sources or playback.

- Repository content is English (UI strings, comments, docs, commits), except the intentionally Chinese player guide `docs/PLAYER_GUIDE.zh-CN.md`. Keep both guides in sync when rules change.
- Run tests with `python -m pytest`. Tests force `CHAOS_USE_LLM=0`; never make billed API calls in tests or CI.
- Credentials live only in the git-ignored `.env` (names in `.env.example`). Never print, commit or copy a real key. `python scripts/debug_llm.py models` checks the relay without billing a completion.
- Art: raw images live in the git-ignored `black-jack-assets/`; final `<id>.png` files go in `assets/`. Use `scripts/asset_tools.py`, `scripts/validate_assets.py`, `scripts/preview_assets.py` and `scripts/fetch_icons.py`; workflow and rules in `.claude/skills/art-asset-pipeline/SKILL.md`.
- Game numbers live in SQLite balance profiles (`data/game.db`, git-ignored). Shipped values: `chaos_blackjack/data/seed/default.sql` (the locked `default` profile is re-imported when it changes). Schema changes: new `chaos_blackjack/data/migrations/NNNN_*.sql`. Manage profiles with `python -m chaos_blackjack.data profiles | show | clone | set | diff | export | delete` (never edit the locked `default`; clone it). Saves (`run_save`) and preferences (`preference`) live in the same database; `python -m chaos_blackjack.data saves` lists saves, `import-saves` imports old JSON saves. Tests force `CHAOS_DB=:memory:` (use a tmp file when a test needs data to persist between connections); never commit a `.db` file.
- Meta progression (players, upgrades, run history, codex) follows `docs/design/META_PROGRESSION.md`; that file is the contract between agents. Cosmetics and achievements follow `docs/design/COSMETICS_ACHIEVEMENTS.md` (adding one is a catalog entry plus seed rows; see its section 2); modes, their hosts and pools follow `docs/design/AI_MODES.md`. The agent CLI does not use meta progression.
- Balance: the simulator is a separate, git-ignored repo in `black-jack-sim/` (see its README). It only imports the game through `bjsim/adapter.py`; after changing rules, prices or the controller API, run `python -m bjsim check` there and update that adapter if needed.
- Architecture: `core/` state + loop, `rules/` rule engine and chaos plugins, `items/` item plugins, `ai/` chaos pipeline and LLM backends, `app/` UI-agnostic `GameController` (a mode's own mechanics plug in through `app/table_mechanics.py`; J-54's are `j54/`; what the table shows comes from parts and per-mode layouts, see `docs/design/TABLE_UI.md`), `agent/` this agent interface, `gui/` Pygame client, `ui/` + `cli/` text CLI. See README.md.
