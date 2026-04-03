# Chaos Blackjack

*A Rule-Perturbation Card Game with AI as a Chaos Agent*

---

## Overview

**Chaos Blackjack** is a minimal, extensible card game framework: the AI is not the opponent — it is a **rule manipulator**. The Chaos Agent perturbs how rules are applied; game state stays a pure data layer and changes only through the game loop / events.

---

## Architecture (layers)

| Layer | Role |
| ----- | ---- |
| `core/` | `GameState` (facts), `GameLoop` (orchestration) |
| `rules/` | `RuleEngine` + `RuleModifier` / `ActiveModifiers` |
| `events/` | `Event`, `EventType`, `EventDispatcher` |
| `ai/` | `ChaosAgent` protocol — proposes modifiers only |
| `cli/` | Thin entrypoint |

Design goals: **state vs rules separation**, **bounded chaos**, **swap implementations** (rules engine, agent, UI) without rewriting the core.

---

## Project layout

```text
Black_jack/
├── chaos_blackjack/
│   ├── core/           # game_state.py, game_loop.py
│   ├── rules/          # rule_engine.py, modifiers.py
│   ├── events/         # event.py, dispatcher.py
│   └── ai/             # chaos_agent.py
├── cli/
│   └── main.py
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## Requirements

- Python 3.10+
- Git (optional): open a terminal **inside this project folder** and run `git init` to create the repository. If automated tools struggle with the apostrophe in `fghn's`, use Explorer → “Open in Terminal” from this directory, then run `git init`.

## Run

```bash
python cli/main.py
```

Optional editable install (so you can `import chaos_blackjack` from anywhere):

```bash
pip install -e .
```

---

## Extending

- **New events**: add to `EventType`, register handlers on `EventDispatcher`, emit from `GameLoop` (or a future pure reducer).
- **New chaos**: implement `ChaosAgent.maybe_propose_modifier` and return a `RuleModifier`.
- **New rules**: implement `RuleEngine` or extend `DefaultBlackjackRules`.
- **UI / web**: add a new package (e.g. `web/`) that calls `GameLoop` and renders state — keep IO out of `core/` and `rules/`.

---

## Future work

- AI personality, LLM rule generation, player modeling, web UI, deck-building modes.

---

Made with controlled chaos.
