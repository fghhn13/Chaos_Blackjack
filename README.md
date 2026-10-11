# Chaos Blackjack

[![CI](https://github.com/fghhn13/Chaos_Blackjack/actions/workflows/ci.yml/badge.svg)](https://github.com/fghhn13/Chaos_Blackjack/actions/workflows/ci.yml)

*Blackjack where a sandboxed Chaos AI bends the rules — playable in a Pygame GUI, a text CLI, or by LLM agents through the shell.*

📖 **How to play**: [玩家指南（中文）](docs/PLAYER_GUIDE.zh-CN.md) · [Agent player guide (English)](docs/AGENT_GUIDE.md) · [AGENTS.md quick reference](AGENTS.md)

---

## Overview

**Chaos Blackjack** separates **facts** (`GameState`) from **laws** (`RuleEngine` + registered chaos rule plugins). The Chaos AI never edits hands directly: it emits **structured JSON**, which is checked against **permissions**, then resolved through a central **registry** into rule modifiers or item uses.

- **Three front-ends** on one UI-agnostic `GameController`: a Pygame GUI, the original text CLI, and a JSON command interface for agent players.
- **Plugins**: chaos rules (`rules/plugins/`) and items (`items/`) self-register; prompts (`ai/prompts/*.txt`) and permission profiles (`ai/permissions/*.json`) are data files.
- **Optional real LLM**: an offline stub drives the Chaos AI by default; the [GPTsAPI](https://api2.gptsapi.net/tutorial) relay (OpenAI-compatible) can be switched on.
- **Player progression**: three named slots, Classic/Chaos modes, token rewards, permanent upgrades, starting consumables, checkpoints and run history.
- **Collection**: browse rules, items, modes and Chaos AIs with live balance values and deterministic animated demonstrations.
- **Responsive table**: background LLM calls, portrait advice, card/chip animations and synchronized casino sound cues.
- **SQLite balance profiles and content packs**: tune game and progression values, and add scoped items and Chaos AIs.

---

## Quick start

```bash
pip install -e ".[gui]"            # Python 3.10+
python -m chaos_blackjack.gui      # play in a window
```

On Windows, double-click `start_game.bat` to launch the GUI. It prefers a local
`.venv` or `venv`, then the active Python or Windows Python launcher (Python
3.10+). If Pygame is missing, it installs the GUI dependencies automatically
(internet required). Launch errors keep the console open. You can also pass
GUI options from a terminal: `start_game.bat --fullscreen` or
`.\start_game.bat --mute` in PowerShell. The launcher uses the game's
existing `.env` settings.

The game opens on the home screen. The first time, **Start game** creates your
player; after that, **Continue run** or **New run** (pick **Classic** or **Chaos**,
check your upgrades, choose items to bring) takes you to the table. Offline
Chaos mode needs no API key. To open the collection directly:

```bash
python -m chaos_blackjack.gui --scene codex
```

Other ways to play:

The authenticated browser edition runs the original Pygame GUI in WebAssembly,
including progression, upgrades and account saves. Registration requires a
16-digit invitation token. See [browser compatibility and builds](browser/README.md).
See [browser deployment and continuous delivery](deploy/README.md) for local
setup, HTTPS hosting, account administration and the production branch.

```bash
python cli/main.py                                   # text CLI (menu driven)
python -m chaos_blackjack.agent new --seed 7 --chaos # agent / scripted play, see AGENTS.md
```

### Conda (alternative)

```bash
conda env create -f environment.yml
conda activate chaos-blackjack
pip install -e .
```

Update after editing `environment.yml`: `conda env update -f environment.yml --prune`. Remove: `conda deactivate`, then `conda env remove -n chaos-blackjack`.

---

## Game rules

- Bankroll starts at **100**; reach **300** to win, or go bankrupt.
- Bet each round: integer from 1 to `floor(bankroll / 2)`.
- Win `+bet`, lose / bust `-bet`, push `0`.
- **Natural blackjack** (first two cards = 21) pays **3:2**, rounded down. A dealer natural wins before the player acts; two naturals push.
- **Double down** and **surrender** (half the bet back, rounded in the house's favour) on the first decision only.
- Dealer draws to 17 and stands on 17+.
- **Shop** (between rounds): spend bankroll on items. By default it shows 3 different items, each can be bought once, and it restocks every 2 rounds. Prices are a percentage of your bankroll when the stock rolls (never below the opening price), and you may **reroll** the stock once per restock for 10 chips. A purchase must leave enough to make a legal bet. Prices, slots and restocking come from the selected balance profile.
- **Chaos mode**: before each player turn the Chaos AI may apply one rule or leave the round calm — e.g. card values −1, ties go to the dealer, bust above 19, a bust becomes a push. Totals shown always include active rules. Winning with Chaos on earns 4 extra tokens.

These are the default profile's values; a balance profile, game mode or player
upgrade can change them. Natural blackjack, double down, surrender and the shop
are implemented in `GameController` (GUI and agent interface); the text CLI
still runs the original hit / stand loop with the old streak reward.

### Balance profiles (SQLite)

Every tunable number of a run is stored as a **balance profile** in
`data/game.db` (SQLite, created on first run, git-ignored; `CHAOS_DB` points
elsewhere).

| Table | Holds |
| ----- | ----- |
| `setting` | bankroll and target, payout ratio, dealer stand total, double / surrender, bet range (`bet.min`, `bet.max_fraction`), shop slots/restocking, portrait guidance probability and memory controls |
| `shop_item` | price, on sale or not, item tuning (`params`, e.g. Fate Oracle `{"cards": 3}`) |
| `chaos_rule` | on / off, fixed tuning that wins over the AI's params (`params`, e.g. Great Crash `{"ten_value": 1}`, Fragile Bust `{"bust_limit": 18}`), and how often the offline Chaos AI picks it (`stub_weight`, `stub_params`) |
| `meta_upgrade` | permanent and consumable upgrade effects, prices, cost increases, level limits and prerequisites |

- The `default` profile is generated from `chaos_blackjack/data/seed/default.sql`,
  the single source of truth for shipped values. It is locked and re-imported
  whenever that file changes; change shipped values there.
- To experiment, copy it into a new profile and edit that one. Every edit is
  validated (type, min / max, JSON params, no unknown keys) and rolled back if
  invalid; DB Browser for SQLite works too (checked when a run starts):

  ```bash
  python -m chaos_blackjack.data clone default tune-a
  python -m chaos_blackjack.data set tune-a item.peek.price 6
  python -m chaos_blackjack.data set tune-a rule.great_crash.params '{"ten_value": 5}'
  python -m chaos_blackjack.data diff default tune-a
  python -m chaos_blackjack.data export tune-a -o chaos_blackjack/data/seed/default.sql   # ship it
  ```

  Keys: settings (`run.start_money`, `bet.max_fraction`, ...), `item.<id>.<field>`
  and `rule.<id>.<field>`; `python -m chaos_blackjack.data --help` lists them.
  Compare profiles in the balance simulator with `python -m bjsim --profile tune-a ...`.
- Pick a profile with `--profile NAME` (GUI and agent `new`) or `CHAOS_PROFILE`.
  A run keeps the numbers it started with.
- Schema changes go in new `chaos_blackjack/data/migrations/NNNN_*.sql` files.

Portrait settings also come from the profile: `chaos.guidance_probability` (float
0..1, default 0.5), `chaos.memory_enabled` (bool, default false), and
`chaos.memory_limit` (integer >=1, default 32). For example, enable memory on an
editable profile with `python -m chaos_blackjack.data set tune-a chaos.memory_enabled 1`.
An upgrade fills these three settings into existing profiles while preserving
their other tuning. Saves keep every configuration field and enabled memory.

The same database keeps **saves** (`run_save`: the run's JSON, including the
numbers it was played with, so a save restores them even after its profile
changes) and **preferences** (`preference`, e.g. the GUI's Chaos Mode switch).
Saves from older versions (JSON files in `chaos_blackjack/saves/`) are imported
once with `python -m chaos_blackjack.data import-saves`; `python -m
chaos_blackjack.data saves` lists what is stored.

Player slots, owned upgrades, completed/abandoned runs and encountered codex
entries live in `player`, `player_upgrade`, `run_history` and `codex_seen`.
The profile's `meta.*` settings determine victory and consolation rewards.

**Meta progression** (player slots, tokens, upgrades, run history) also lives
there; see [docs/design/META_PROGRESSION.md](docs/design/META_PROGRESSION.md).
Upgrade costs, rewards and the catalog are part of the balance profile
(`meta.*` settings, `upgrade.<id>.<field>` keys). `python -m chaos_blackjack.data
players` and `history SLOT` show the players.

Game logic never reads the database: front-ends load a `Balance` and build a
`RunConfig` from it (`RunConfig.from_balance`). Tests use an in-memory database.

---

## Front-ends

### Pygame GUI

```bash
python -m chaos_blackjack.gui              # --fullscreen, --scene codex, --profile NAME
```

| Phase | Mouse | Keyboard |
| ----- | ----- | -------- |
| Betting | left-click a chip to add, right-click to remove; Clear / Max; Shop | ↑ / ↓ ±1, Enter deals, B shop (1–3 buy) |
| Your turn | Hit / Stand / Double / Surrender buttons | H / S / D / R |
| Round over | Next Round | Enter |
| Anywhere | — | Esc (back to the main menu, asks first), F11 fullscreen, F5 reload assets |

The window scales a fixed 1280×720 canvas with letterboxing. Choose **Chaos** in New run's mode list.

Chaos AI calls run in a background thread. An animated "The Chaos AI is thinking..."
indicator appears while the table waits; gameplay controls stay disabled, and Esc,
fullscreen and window events remain responsive. Returning to the menu discards the
old table's result without waiting for an in-flight request. No additional art is
needed for the procedural indicator.

In Chaos Mode, click the Chaos portrait while betting, choosing a player action,
or reviewing a round result to ask for a suggestion. The portrait also works while
the shop is open. A modal banner animates while the reply is generated and blocks
repeated clicks and gameplay; click **Continue** or press Enter after the reply.
While waiting, Esc opens the return-to-menu confirmation. Each interaction chooses
guidance or misdirection with **50% probability each by default**, without revealing which.
These are intent probabilities, not a guarantee of the model's advice accuracy.
The offline backend gives local suggestions; with a real LLM each poke makes one
billed completion, with no repair or automatic retry.

The AI receives a private snapshot containing hands, hidden cards, ordered deck,
effective totals and rules, bankroll, inventory, and shop stock/prices/restocking.
Replies only provide text; they cannot buy items, play cards, or change rules.
The reply parser accepts the requested `{"reply": "..."}` object or plain prose
from a backend, without an extra repair request; gameplay-action JSON is rejected.
The context uses the selected profile's bet limits and shop affordability, filters
disabled rule choices, and supplies fixed rule/item tuning and rule descriptions.
Public player observations continue to hide private cards. Run-local memory is
implemented but **disabled by default** (`RunConfig.chaos_memory_enabled=False`):
no history is collected, included in prompts, or written to saves. Enable it
through `chaos.memory_enabled` on an editable balance profile to retain at most
`chaos_memory_limit` events (default 32) across save/load. This is memory for
the current run; player progression is stored separately.
**Sound:** Kenney Casino Audio and Interface Sounds (CC0) provide sixteen GUI
cues synchronized to card, chip, banner and glitch animations. Master volume
defaults to 40%; **M** toggles mute, **+/-** changes it by 10 percentage points,
and **F5** reloads sound files as well as images. Preferences last for the
current process. Missing clips, mixer failure and SDL dummy audio are silent.
[Sound interface and timing](assets/sounds/README.md) ·
[Source credits](assets/CREDITS.md) · [Clip report](assets/sounds/REPORT.md).

The standalone casino audio library and offline validator remain available: `python -m chaos_blackjack.audio validate`.

#### Player progression and collection

The home screen shows the current player (top right; click to switch) and the
next step: **Continue run** with its mode, round and chips when a run is
unfinished, otherwise **New run**, plus **Upgrades**, **Collection** and **Run
history**. **Players** holds three named slots with play, create, rename and
confirmed delete actions. **New run** selects **Classic** or **Chaos**, shows the
permanent upgrades in effect and lets you bring one copy of each checked
consumable; nothing is spent until the run starts. Tokens persist between runs; bankroll belongs to the current run.

**Upgrades** uses tokens for permanent starting-bankroll, shop-slot and
discount upgrades, plus consumable starting items. The table's between-round
shop uses bankroll. Victory earns the profile's win reward; defeat earns capped
consolation based on rounds and peak bankroll. Abandoning earns no tokens and
does not return consumed starting items. The result screen settles each run
once and shows the token breakdown.

Player runs checkpoint at safe table phases. Closing the window preserves the
last checkpoint for **Continue run**; confirming a return to the main menu
abandons the run. Replacing an unfinished run also asks for confirmation.
History shows outcomes, bankroll, tokens, applied upgrades and encounter counts.

The **Collection** (scene id `codex`) is available from the home screen or `--scene codex`. Its rule, item, mode
and AI tabs show every entry. Detail pages use the selected profile's numbers;
card demonstrations run on a real controller with fixed deals and an offline
backend. **Space** pauses, **R** replays, **Left/Right** steps, and the wheel or
**Page Up/Page Down** scrolls descriptions. Selected content packs appear in
the collection. Browsing and demonstrations never spend tokens or call a paid model.

The agent CLI stays independent of player upgrades. Development
tools include `python -m chaos_blackjack.data players`, `history SLOT` and
`grant SLOT TOKENS`. See [Player GUI guide](docs/META_GUI.md),
[Meta API contract](docs/design/META_PROGRESSION.md) and
[Codex API and replay guide](docs/design/CODEX.md).

**Art is optional**: every asset has a procedural placeholder. Drop `<asset id>.png` into `assets/` (subfolders allowed), `black-jack-assets/exports/`, or any directory listed in `CHAOS_ASSETS_DIR`, then press F5. The ids are in `chaos_blackjack/gui/assets/manifest.py`; `python scripts/validate_assets.py` reports which are still placeholders and `python scripts/preview_assets.py` renders matte sheets on dark / felt / white backdrops to check alpha edges. A font in `assets/fonts/` overrides the UI font.

### Text CLI

```bash
python cli/main.py                 # 1) New Game  2) Load Game  3) Quit
python cli/main.py --enable-chaos
python cli/main.py demo            # one automated round, no input
```

Type `save` during a game to store the run in `data/game.db`; Load Game lists the saves. The CLI layout follows [UX_design.md](UX_design.md).

### Agent players

LLM agents (or scripts) play through one-shot shell commands; the run is kept in a state file between calls. Replies are JSON with a `summary`, a `hint`, the `legal_actions`, the events that just happened, and the last round's result. Hidden information (dealer hole card, deck order) never appears in observations, and the same seed plus the same commands always replays the same game.

```bash
python -m chaos_blackjack.agent new --seed 7 --chaos
python -m chaos_blackjack.agent --brief bet 20
python -m chaos_blackjack.agent --brief act double     # hit | stand | double | surrender | use_item <id>
python -m chaos_blackjack.agent --brief buy peek        # buy from the shop while betting
```

A streaming JSON-lines mode (`play`) and a Python API (`AgentSession`) are also available. Quick reference: **[AGENTS.md](AGENTS.md)**; full guide with rule/item catalogs, transcripts and strategy: **[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)**.

---

## Real LLM (optional)

The Chaos AI uses an offline stub by default — no network, no cost. To use the GPTsAPI relay:

```bash
cp .env.example .env
# in .env: CHAOS_USE_LLM=1 and GPTSAPI_API_KEY=sk-...
python scripts/debug_llm.py models   # list model ids (no completion billed)
python scripts/debug_llm.py smoke    # one billed request, max 16 output tokens
python scripts/debug_llm.py chaos    # one billed request with the real Chaos AI prompt
python -m chaos_blackjack.gui --chaos --llm  # billed Chaos turns and portrait interactions
```

| Variable | Default | |
| -------- | ------- | - |
| `CHAOS_USE_LLM` | `0` | `1` lets the GUI / CLI use the relay |
| `GPTSAPI_API_KEY` | — | required; keep it only in the git-ignored `.env` |
| `GPTSAPI_BASE_URL` | `https://api2.gptsapi.net/v1` | HTTPS origin, `/v1` at most once |
| `GPTSAPI_MODEL` | `gpt-6-luna` | exact id from `debug_llm.py models` |
| `GPTSAPI_TIMEOUT`, `GPTSAPI_MAX_TOKENS`, `GPTSAPI_USER_AGENT` | 45 s, 256, browser UA | optional |

Notes:

- Each chaos phase is one chat request (plus at most one repair request if the model returns invalid JSON). A failed request becomes a no-op; the game keeps going.
- The client (`chaos_blackjack/ai/gptsapi_llm.py`, stdlib only) rejects redirects, keeps TLS verification, redacts the key from every error and never retries automatically.
- The agent interface ignores `CHAOS_USE_LLM`; it uses the relay only with an explicit `new --llm`.
- GUI model calls run in a background thread with animated waiting banners; the window remains responsive.

---

## Architecture

```text
            GUI (gui/)        text CLI (ui/, cli/)      agent CLI (agent/)
                 \                    |                       /
                  └──────── GameController (app/) ───────────┘
                         view() · drain_notices() · commands
                                     │
                         GameLoop + GameState (core/)
                     ┌───────────────┼────────────────┐
              RuleEngine (rules/)  items/       ChaosPipeline (ai/)
                     │                               │
              rules/plugins/*        prompts · permissions · LLM backend
                     └──────── Registry (registry/) ─┘
```

| Layer | Responsibility |
| ----- | -------------- |
| `contracts/` | Shared protocols: `ChaosObservation`, `ItemProtocol`, `StructuredAIAction`, `LLMBackend` |
| `registry/` | `register_item` / `register_rule`, `auto_load_plugins()` |
| `core/` | `GameState`, `GameLoop` (orchestration; no imports of concrete plugins), saves |
| `rules/` | `DefaultBlackjackRules`; `rules/plugins/` for chaos perturbations |
| `items/` | Player tools — `use()` via `ItemContext` (no raw deck mutation) |
| `ai/` | `ChaosPipeline`, `StubLLM`, `GptsApiLLM`, prompt + permission loaders, `.env` loading |
| `events/` | `Event` / `EventDispatcher` |
| `app/` | `GameController` state machine (betting → chaos → player turn → dealer → round over → run over), `GameView`, `Notice` stream, `RunConfig` |
| `data/` | SQLite storage: migrations, seeded balance profiles, `Balance` loader, saves, preferences |
| `meta/`, `modes/` | Player slots, upgrade effects, rewards, tracked runs/history, selectable game modes |
| `codex/` | Registered reference providers and deterministic controller demonstrations; no GUI dependency |
| `content/`, `audio/` | Scoped content packs and the licensed casino sound catalog |
| `meta/` | Meta progression: players, upgrades, upgrade effects, run tracking and rewards |
| `modes/` | Game mode registry (`normal`, `chaos`) |
| `agent/` | `AgentSession`, JSON observations, agent CLI |
| `gui/` | Pygame app, scene stack, widgets, asset manager + placeholders, scenes |
| `ui/`, `cli/` | Text CLI |

**Plugin rule**: feature plugins depend only on `chaos_blackjack.contracts` and `chaos_blackjack.registry` and never import each other; core code resolves behaviour by **name** through the registry. Front-ends never decide rules: they render `GameView` and call controller commands.

### Project layout

```text
Black_jack/
├── chaos_blackjack/
│   ├── contracts/  registry/  core/  events/  logic/
│   ├── rules/plugins/        # chaos rule plugins (self-register)
│   ├── items/                # item plugins (self-register)
│   ├── ai/                   # pipeline, prompts/, permissions/, gptsapi_llm.py
│   ├── app/                  # GameController, views, notices, config
│   ├── data/                 # SQLite: migrations/, seed/default.sql, balances, saves, prefs
│   ├── meta/  modes/          # players, upgrades, run tracking, rewards and mode registry
│   ├── codex/                 # providers, live descriptions and controller demos
│   ├── content/  audio/       # content packs and casino sound catalog
│   ├── agent/                # agent-player interface
│   ├── gui/                  # Pygame client (assets/, components/, scenes/)
│   ├── ui/                   # text CLI session
├── assets/                   # drop final art here (see assets/README.md)
├── data/game.db              # profiles, players, saves, history and prefs (git-ignored)
├── cli/main.py
├── scripts/                  # debug_smoke.py, debug_llm.py
├── tests/
├── .github/workflows/ci.yml
├── docs/                     # PLAYER_GUIDE.zh-CN.md (players), AGENT_GUIDE.md (agents)
├── AGENTS.md                 # agent-player quick reference + repo notes
├── UX_design.md              # text CLI UX spec
├── pyproject.toml  environment.yml  .env.example
└── README.md
```

---

## Development

```bash
pip install -e ".[dev,gui,art]"
python -m pytest                   # GUI tests run headless (SDL dummy driver)
python scripts/debug_smoke.py      # registry + stub pipeline, no API key
python scripts/ci_smoke.py --gui   # integrated meta, codex, resources and headless GUI
python -m chaos_blackjack.content validate example
python -m chaos_blackjack.audio validate
python scripts/export_sounds.py --verify
```

Tests force `CHAOS_USE_LLM=0` and `CHAOS_DB=:memory:` and use fake transports or
temporary databases, so they never make billed requests or touch player saves.

**CI** ([workflow](.github/workflows/ci.yml)) runs on every push, pull requests
to `main` and manual dispatch: the full suite on Ubuntu (Python 3.10, 3.12) and
Windows (3.12), application/GUI and CLI smoke checks, content-pack validation
and sound verification. A separate job builds the source distribution and wheel,
installs the wheel, then checks its migrations, seeded values, prompts, sounds,
meta lifecycle and real home-to-collection navigation from outside the checkout.
Distribution files are uploaded as a workflow artifact. All runtime checks
disable billed calls and need no API secrets.

The optional [balance simulator](black-jack-sim/README.md) is a separate,
git-ignored repository. In its directory, run `python -m bjsim check --jobs 4`
with `PYTHONPATH` and `CHAOS_BLACKJACK_ROOT` set to the game checkout under test.
Its `upgrades` and `career` commands measure upgrade payback and token economy
using the same `build_run_config` and `reward_tokens` helpers as player runs.
The simulator is validated locally; it is not downloaded by the game CI.

---

## AI safety (by design)

- Structured output only: JSON matching `StructuredAIAction` (`action`, `rule_id`, `params`, `item_id`).
- **PermissionValidator**: `allowed_rules`, optional `allowed_items`, `max_actions_per_turn`, budget vs `chaos_budget_remaining`.
- Rejected actions emit `CHAOS_ACTION_REJECTED`; network or model failures fall back to a no-op.

---

## Extending

**Standard item / Chaos AI workflow:** [Content pack guide](docs/CONTENT_WORKFLOW.md).
Generate, validate, and launch a pack without changing the game loop:

```bash
python -m chaos_blackjack.content init lucky
python -m chaos_blackjack.content validate lucky
python -m chaos_blackjack.data clone default lucky
python -m chaos_blackjack.content install-shop lucky --profile lucky
python -m chaos_blackjack.content play lucky --profile lucky
```

The bundled `example` pack can be launched immediately. Add `--agent` for JSON
streaming play. Packs load into a registry scoped to the run; their item help,
starting inventory, balance-profile shop prices and selected AI are wired automatically.
Pack items are sold only when their plugin is loaded; win streaks grant no items.

1. **Chaos rule**: add `chaos_blackjack/rules/plugins/your_rule.py`, implement `from_params` → `RuleModifier`, call `register_rule("id", YourPlugin)`. Add an icon spec in `gui/assets/manifest.py` (a test checks every rule and item has one).
2. **Item**: preferably add it through a content pack. Implement `ItemProtocol` and return `ItemResult.effects` for state changes. Players and Chaos AI use the same executor. Built-in items can still self-register under `items/`; expose a `description` for shared help.
3. **Player action**: add a `GameController` method + `Action` id, then a row in the GUI's `ACTION_BUTTONS` and the agent's `_ACT_METHODS`.
4. **Prompt / difficulty**: add files under `ai/prompts/` or `ai/permissions/`, then `ChaosPipeline.from_profile_name("easy", "chaotic", your_llm)`.
5. **LLM provider**: implement `LLMBackend.complete(system, user) -> str` returning JSON, or reuse `GptsApiLLM` for any OpenAI-compatible relay.
6. **GUI scene**: subclass `Scene`, decorate with `@register_scene("name")`, import it in `gui/scenes/__init__.py`, open it with `app.scenes.push("name")`.

---

## Roadmap

- Background music and more final art from the asset repo.
- Agent interface: scenario files (rigged decks), replay, benchmark runner with baseline policies, MCP server.
- Split hands; move the text CLI onto `GameController`.

---

Made with controlled chaos.
