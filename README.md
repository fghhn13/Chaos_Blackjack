# Chaos Blackjack

*A rule-perturbation card game framework with a sandboxed Chaos AI (v2)*

---

## Overview

**Chaos Blackjack** separates **facts** (`GameState`) from **laws** (`RuleEngine` + registered chaos rule plugins). The AI does not edit hands directly: it emits **structured JSON**, which is checked against **permissions**, then resolved through a central **registry** into rule modifiers or item uses.

v2 adds: **plugin auto-loading**, **external prompts** (`ai/prompts/*.txt`), **permission profiles** (`ai/permissions/*.json`), and an **execution pipeline** (`ChaosPipeline`) with a pluggable **LLM backend** (stub included).

---

## Architecture (v2)

```text
                 ┌─────────────────┐
                 │    Registry     │
                 └────────┬────────┘
                          │
    ┌─────────────┬───────┴────────┬──────────────┐
    ▼             ▼                ▼              ▼
 items/*.py   rules/plugins/*.py  prompts/*.txt  permissions/*.json
```

| Layer | Responsibility |
| ----- | ---------------- |
| `contracts/` | Shared protocols: `ChaosObservation`, `ItemProtocol`, `StructuredAIAction`, `LLMBackend` |
| `registry/` | `register_item` / `register_rule`, `auto_load_plugins()` |
| `core/` | `GameState`, `GameLoop` (orchestration only; no imports of concrete plugins) |
| `rules/` | Baseline `DefaultBlackjackRules`; `rules/plugins/` for chaos perturbations |
| `items/` | Player tools (`peek`, …) — `use()` via `ItemContext` (no raw deck mutation) |
| `ai/` | `ChaosPipeline`, `StubLLM`, prompt + permission loaders |
| `events/` | `Event` / `EventDispatcher` (e.g. `CHAOS_ACTION_REJECTED`, `ITEM_USED`) |

**Plugin rule**: feature plugins may depend on `chaos_blackjack.contracts` and `chaos_blackjack.registry` only; they must not import each other. Core code resolves behavior by **name** through the registry.

---

## Project layout

```text
Black_jack/
├── chaos_blackjack/
│   ├── contracts/
│   ├── registry/
│   ├── items/
│   ├── rules/
│   │   ├── plugins/          # chaos rule plugins (self-register)
│   │   ├── rule_engine.py
│   │   └── modifiers.py
│   ├── ai/
│   │   ├── prompts/          # .txt templates (package data)
│   │   ├── permissions/      # .json profiles (package data)
│   │   ├── pipeline.py
│   │   └── permission_validator.py
│   ├── core/
│   ├── ui/                   # interactive CLI (UX_design.md)
│   └── events/
├── cli/main.py
├── UX_design.md              # user-facing CLI UX spec
├── pyproject.toml
├── environment.yml           # conda 环境定义
└── README.md
```

---

## Requirements

- Python 3.10+
- **Gemini (optional, off by default)**: the game uses a **Stub LLM** (no network). To call Gemini, set **`CHAOS_USE_GEMINI=1`** in `.env` and a valid **`GOOGLE_API_KEY`** (copy from [`.env.example`](.env.example)). Keys: [Google AI Studio](https://aistudio.google.com/apikey). Without `CHAOS_USE_GEMINI=1`, an invalid or placeholder key is ignored and no API request is made.

### Conda（推荐）

在项目根目录执行：

```bash
conda env create -f environment.yml
conda activate chaos-blackjack
pip install -e .
```

更新依赖后若改了 `environment.yml`，可：

```bash
conda env update -f environment.yml --prune
```

删除环境：`conda deactivate` 后 `conda env remove -n chaos-blackjack`。

### pip / venv

```bash
cp .env.example .env
# Edit .env — set GOOGLE_API_KEY=...
pip install -e .
```

## Run

**Menu-driven CLI (MVP v1 run mode by default)**:

- Start bankroll: `100`
- Target bankroll: `400`
- Bet each round: integer in `1 .. floor(money * 0.5)`
- Settlement: win `+bet`, lose/bust `-bet`, push `0`
- Win streak reward: every 2 consecutive wins grants 1 random item
- Chaos is disabled by default in this mode

```bash
python cli/main.py
# then choose:
# 1) New Game
# 2) Load Game
# 3) Quit
```

**Enable chaos during interactive play** (optional):

```bash
python cli/main.py --enable-chaos
```

**Saving / Loading**
- Save during a running game by typing `save` at the in-game prompt.
- When loading, the CLI lists save files under `chaos_blackjack/saves/` (relative to project root).
- Each save stores run economy state, current round snapshot, active modifiers, and `chaos_actions_this_turn`.

**Non-interactive demo** (one automated round):

```bash
python cli/main.py demo
```

Call `auto_load_plugins()` before constructing `GameLoop` so items and rule plugins register (the CLI does this).

Editable install:

```bash
pip install -e .
```

## Tests & debug scripts

**pytest**（Conda 环境已含 pytest 时直接运行；否则 `pip install -e ".[dev]"`）：

```bash
pytest
```

**Manual smoke** (registry + stub pipeline, no API key):

```bash
python scripts/debug_smoke.py
```

**Gemini connectivity** (requires `.env` with `GOOGLE_API_KEY`):

```bash
python scripts/debug_gemini.py
```

---

## AI safety (by design)

- Structured output only: JSON matching `StructuredAIAction` (`action`, `rule_id`, `params`, `item_id`).
- **PermissionValidator**: `allowed_rules`, optional `allowed_items`, `max_actions_per_turn`, budget vs `chaos_budget_remaining` on `GameState`.
- Rejected actions emit `CHAOS_ACTION_REJECTED` (optional `EventDispatcher`).

---

## Extending

1. **New chaos rule**: add `chaos_blackjack/rules/plugins/your_rule.py`, implement `from_params` → `RuleModifier`, call `register_rule("id", YourPlugin)`.
2. **New item**: add `chaos_blackjack/items/your_item.py`, implement `ItemProtocol`, call `register_item("id", YourItem)`.
3. **New prompt / difficulty**: add files under `ai/prompts/` or `ai/permissions/`, then `ChaosPipeline.from_profile_name("easy", "chaotic", your_llm)`.
4. **Other LLM providers**: implement `LLMBackend.complete(system, user) -> str` returning JSON, or reuse `GeminiLLM` / `try_create_gemini_llm()` in [`chaos_blackjack/ai/gemini_llm.py`](chaos_blackjack/ai/gemini_llm.py).

---

## Future work

Personalities, dynamic prompts, player modeling, web UI, plugin marketplace.

---

Made with controlled chaos.
