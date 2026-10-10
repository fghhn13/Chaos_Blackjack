# Chaos Blackjack

[![CI](https://github.com/fghhn13/Chaos_Blackjack/actions/workflows/ci.yml/badge.svg)](https://github.com/fghhn13/Chaos_Blackjack/actions/workflows/ci.yml)

*Blackjack where a sandboxed Chaos AI bends the rules — playable in a Pygame GUI, a text CLI, or by LLM agents through the shell.*

---

## Overview

**Chaos Blackjack** separates **facts** (`GameState`) from **laws** (`RuleEngine` + registered chaos rule plugins). The Chaos AI never edits hands directly: it emits **structured JSON**, which is checked against **permissions**, then resolved through a central **registry** into rule modifiers or item uses.

- **Three front-ends** on one UI-agnostic `GameController`: a Pygame GUI, the original text CLI, and a JSON command interface for agent players.
- **Plugins**: chaos rules (`rules/plugins/`) and items (`items/`) self-register; prompts (`ai/prompts/*.txt`) and permission profiles (`ai/permissions/*.json`) are data files.
- **Optional real LLM**: an offline stub drives the Chaos AI by default; the [GPTsAPI](https://api2.gptsapi.net/tutorial) relay (OpenAI-compatible) can be switched on.

---

## Quick start

```bash
pip install -e ".[gui]"            # Python 3.10+
python -m chaos_blackjack.gui      # play in a window
```

Other ways to play:

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

- Bankroll starts at **100**; reach **400** to win, or go bankrupt.
- Bet each round: integer from 1 to `floor(bankroll / 2)`.
- Win `+bet`, lose / bust `-bet`, push `0`.
- **Natural blackjack** (first two cards = 21) pays **3:2**, rounded down. A dealer natural wins before the player acts; two naturals push.
- **Double down** and **surrender** (half the bet back, rounded in the house's favour) on the first decision only.
- Dealer draws to 17 and stands on 17+.
- Every 2 consecutive wins grant 1 random item (`peek`, `swap`, `shield`, …).
- **Chaos mode**: before each player turn the Chaos AI may apply one rule — e.g. card values −1, ties go to the dealer, bust above 18. Totals shown always include active rules.

Natural blackjack, double down and surrender are implemented in `GameController` (GUI and agent interface); the text CLI still runs the original hit / stand loop.

All payout ratios and options live in `RunConfig` (`chaos_blackjack/app/config.py`).

---

## Front-ends

### Pygame GUI

```bash
python -m chaos_blackjack.gui              # --fullscreen, --scene gallery
```

| Phase | Mouse | Keyboard |
| ----- | ----- | -------- |
| Betting | left-click a chip to add, right-click to remove; Clear / Max | ↑ / ↓ ±1, Enter deals |
| Your turn | Hit / Stand / Double / Surrender buttons | H / S / D / R |
| Round over | Next Round | Enter |
| Anywhere | — | Esc (menu, asks first), F11 fullscreen, F5 reload assets |

The window scales a fixed 1280×720 canvas with letterboxing. Toggle **Chaos Mode** on the main menu.

**Art is optional**: every asset has a procedural placeholder. Drop `<asset id>.png` into `assets/` (subfolders allowed), `black-jack-assets/exports/`, or any directory listed in `CHAOS_ASSETS_DIR`, then press F5. The ids are in `chaos_blackjack/gui/assets/manifest.py`; the in-game **Asset Gallery** shows which are still placeholders and previews each image on dark / felt / white backdrops (B) to check alpha edges. A font in `assets/fonts/` overrides the UI font.

### Text CLI

```bash
python cli/main.py                 # 1) New Game  2) Load Game  3) Quit
python cli/main.py --enable-chaos
python cli/main.py demo            # one automated round, no input
```

Type `save` during a game to write a JSON save under `chaos_blackjack/saves/`; Load Game lists them. The CLI layout follows [UX_design.md](UX_design.md).

### Agent players

LLM agents (or scripts) play through one-shot shell commands; the run is kept in a state file between calls. Replies are JSON with a `summary`, a `hint`, the `legal_actions`, the events that just happened, and the last round's result. Hidden information (dealer hole card, deck order) never appears in observations, and the same seed plus the same commands always replays the same game.

```bash
python -m chaos_blackjack.agent new --seed 7 --chaos
python -m chaos_blackjack.agent --brief bet 20
python -m chaos_blackjack.agent --brief act double     # hit | stand | double | surrender | use_item <id>
```

A streaming JSON-lines mode (`play`) and a Python API (`AgentSession`) are also available. Full protocol: **[AGENTS.md](AGENTS.md)**.

---

## Real LLM (optional)

The Chaos AI uses an offline stub by default — no network, no cost. To use the GPTsAPI relay:

```bash
cp .env.example .env
# in .env: CHAOS_USE_LLM=1 and GPTSAPI_API_KEY=sk-...
python scripts/debug_llm.py models   # list model ids (no completion billed)
python scripts/debug_llm.py smoke    # one billed request, max 16 output tokens
python scripts/debug_llm.py chaos    # one billed request with the real Chaos AI prompt
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
- Calls currently run on the GUI thread, so the window pauses while the model answers.

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
│   ├── agent/                # agent-player interface
│   ├── gui/                  # Pygame client (assets/, components/, scenes/)
│   ├── ui/                   # text CLI session
│   └── saves/
├── assets/                   # drop final art here (see assets/README.md)
├── cli/main.py
├── scripts/                  # debug_smoke.py, debug_llm.py
├── tests/
├── .github/workflows/ci.yml
├── AGENTS.md                 # agent-player protocol + repo notes
├── UX_design.md              # text CLI UX spec
├── pyproject.toml  environment.yml  .env.example
└── README.md
```

---

## Development

```bash
pip install -e ".[dev,gui]"
python -m pytest                   # GUI tests run headless (SDL dummy driver)
python scripts/debug_smoke.py      # registry + stub pipeline, no API key
```

Tests force `CHAOS_USE_LLM=0` and use fake transports, so they never make billed requests.

**CI** (`.github/workflows/ci.yml`) runs on every push and on pull requests to `main`: pytest on Ubuntu (Python 3.10, 3.12) and Windows (3.12), plus offline smoke runs of the CLI demo, `debug_smoke.py` and the agent CLI. CI never calls the LLM relay and needs no secrets.

---

## AI safety (by design)

- Structured output only: JSON matching `StructuredAIAction` (`action`, `rule_id`, `params`, `item_id`).
- **PermissionValidator**: `allowed_rules`, optional `allowed_items`, `max_actions_per_turn`, budget vs `chaos_budget_remaining`.
- Rejected actions emit `CHAOS_ACTION_REJECTED`; network or model failures fall back to a no-op.

---

## Extending

1. **Chaos rule**: add `chaos_blackjack/rules/plugins/your_rule.py`, implement `from_params` → `RuleModifier`, call `register_rule("id", YourPlugin)`. Add an icon spec in `gui/assets/manifest.py` (a test checks every rule and item has one).
2. **Item**: add `chaos_blackjack/items/your_item.py`, implement `ItemProtocol`, call `register_item("id", YourItem)`. If it changes the table, add an effect to `ITEM_EFFECTS` in `app/item_use.py`; describe it for agents in `agent/observation.py` (`ITEM_HELP`).
3. **Player action**: add a `GameController` method + `Action` id, then a row in the GUI's `ACTION_BUTTONS` and the agent's `_ACT_METHODS`.
4. **Prompt / difficulty**: add files under `ai/prompts/` or `ai/permissions/`, then `ChaosPipeline.from_profile_name("easy", "chaotic", your_llm)`.
5. **LLM provider**: implement `LLMBackend.complete(system, user) -> str` returning JSON, or reuse `GptsApiLLM` for any OpenAI-compatible relay.
6. **GUI scene**: subclass `Scene`, decorate with `@register_scene("name")`, import it in `gui/scenes/__init__.py`, open it with `app.scenes.push("name")`.

---

## Roadmap

- GUI: item tray, Chaos AI panel and narration, save / load, LLM calls off the render thread.
- Animations, sound and music; final art from the asset repo.
- Agent interface: scenario files (rigged decks), replay, benchmark runner with baseline policies, MCP server.
- Split hands; move the text CLI onto `GameController`.

---

Made with controlled chaos.
