# Meta progression, player saves, run history and the codex

Status: **agreed plan**, 2026-10-10. Shared contract for the three agents
working on it. Change this file (in its own commit) before changing a
contract below.

## 1. Decisions

| Topic | Decision |
|---|---|
| Tokens | A win pays tokens. A loss pays a small consolation based on rounds survived and peak bankroll. |
| Temporary upgrades | Consumables: bought in the meta shop, stacked in the player's inventory, one is used up at the start of the next run. |
| Player saves | 3 named slots. |
| Codex | Every entry is shown normally (icon + name). No locks or silhouettes for now; "seen" data is collected for later. |
| Game modes | Selectable when starting a run. Only the current two: `normal` and `chaos`. Both unlocked. The `unlock_mode` upgrade effect exists but has no catalog entry yet. |
| Agents / simulator | The agent CLI stays without meta progression (fair, reproducible). The simulator gets upgrade and token-economy experiments (M5). |
| Numbers | All prices, rewards and upgrade values live in the balance profile (seed/default.sql), so `chaos_blackjack.data set/diff/export` and `bjsim --profile` work on them. Values below are placeholders. |

Naming: a **player** is a meta save (slot). A **balance profile** is a set of
numbers. Never call a player a "profile".

## 2. Concepts

```
player (slot 1-3) ── tokens, permanent upgrades (with level), consumables (with count)
   │
   ├─ start run(mode) ─► RunConfig = balance profile + mode + permanent upgrades + one use of each selected consumable
   │                       └─ game logic unchanged; the run's fingerprint shows the upgrades
   └─ finish run ──────► tokens (win or consolation), run_history row, codex_seen updates
```

## 3. Data model (migration 0003, owner: agent A)

```sql
CREATE TABLE player (
    id INTEGER PRIMARY KEY, slot INTEGER NOT NULL UNIQUE CHECK (slot BETWEEN 1 AND 3),
    name TEXT NOT NULL, tokens INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')), last_played_at TEXT
);
CREATE TABLE player_upgrade (            -- permanent: level; consumable: count
    player_id INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    upgrade_id TEXT NOT NULL, amount INTEGER NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (player_id, upgrade_id)
);
CREATE TABLE run_history (
    id INTEGER PRIMARY KEY, player_id INTEGER REFERENCES player(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL, ended_at TEXT, mode TEXT NOT NULL,
    balance_profile TEXT, balance_hash TEXT, seed INTEGER,
    result TEXT,                          -- victory | defeat | abandoned | NULL while running
    rounds INTEGER, final_money INTEGER, peak_money INTEGER, tokens_earned INTEGER,
    upgrades TEXT,                        -- JSON {upgrade_id: level/count used}
    summary TEXT                          -- JSON, see 5.3
);
CREATE TABLE codex_seen (
    player_id INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, entry_id TEXT NOT NULL,
    first_seen_at TEXT NOT NULL, times INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (player_id, kind, entry_id)
);
-- Balance-profile side (catalog and tuning):
CREATE TABLE meta_upgrade (
    profile_id INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    upgrade_id TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('permanent', 'consumable')),
    effect TEXT NOT NULL, params TEXT,    -- effect id + JSON params
    cost INTEGER NOT NULL CHECK (cost >= 0), cost_step INTEGER NOT NULL DEFAULT 0,  -- level n costs cost + (n-1)*cost_step
    max_level INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1,
    requires TEXT,                        -- upgrade id that must be owned first, or NULL
    PRIMARY KEY (profile_id, upgrade_id)
);
ALTER TABLE run_save ADD COLUMN player_id INTEGER REFERENCES player(id) ON DELETE CASCADE;
ALTER TABLE run_save ADD COLUMN run_id INTEGER REFERENCES run_history(id);
```

New settings (placeholders):

| Key | Default | Meaning |
|---|---|---|
| `meta.win_tokens` | 10 | tokens for a victory |
| `meta.loss_per_round` | 0.2 | consolation per round survived |
| `meta.loss_per_peak_gain` | 4 | consolation per 100 % of start bankroll gained at the peak |
| `meta.loss_cap` | 5 | consolation maximum |

Consolation = `min(loss_cap, floor(rounds * loss_per_round + max(0, peak - start) / start * loss_per_peak_gain))`.

Initial catalog (placeholders):

| upgrade_id | kind | effect | params | cost (+step) | max |
|---|---|---|---|---|---|
| `start_money` | permanent | `run.start_money_add` | `{"amount": 10}` | 15 (+10) | 3 |
| `shop_slot` | permanent | `shop.slots_add` | `{"amount": 1}` | 40 | 1 |
| `shop_discount` | permanent | `shop.discount_pct` | `{"pct": 10}` | 25 (+15) | 2 |
| `start_<item>` (one per shop item) | consumable | `run.starting_item` | `{"item": "<item>"}` | ≈ half the shop price | — |

## 4. Extension points (code registries)

| Registry | Owner | Adding content |
|---|---|---|
| Upgrade effects `register_effect(id, fn(config, amount, params) -> RunConfig)` | A | new effect = code; new upgrade using an effect = one `meta_upgrade` row |
| Game modes `register_mode(GameMode)` | A | `GameMode(id, name, description, icon, overrides: dict, unlocked_by: str or None)` |
| Codex providers `register_codex_provider(kind, fn(config) -> list[CodexEntry])` | C | providers read the rule / item / mode / AI registries, so plugins and content packs appear without codex changes |

## 5. Contracts

### 5.1 Meta API (owner A; `chaos_blackjack/meta/`; B builds against it)

```python
list_slots() -> list[PlayerSlot]                    # always 3; PlayerSlot(slot, player: Player | None)
create_player(slot: int, name: str) -> Player       # MetaError if taken / bad name
rename_player(player_id, name) -> Player
delete_player(player_id) -> None
get_player(player_id) -> Player                     # Player(id, slot, name, tokens, upgrades: dict[str, int], stats: PlayerStats)

meta_shop(player_id, profile: str | None = None) -> list[UpgradeOffer]
    # UpgradeOffer(upgrade_id, name, description, kind, owned, max_level, next_cost, can_buy, reason)
buy_upgrade(player_id, upgrade_id) -> Player        # MetaError with a player-readable message

modes() -> list[GameMode]
start_run(player_id, mode_id, *, consumables: list[str] = (), profile=None, seed=None) -> RunStart
    # RunStart(run_id, config: RunConfig, applied: dict[str, int]); consumables are used up here
finish_run(run_id, controller) -> RunReward         # RunReward(tokens, breakdown: list[tuple[str, int]], player)
abandon_run(run_id) -> None                          # quitting mid-run: result "abandoned", no tokens
history(player_id, limit=50) -> list[RunRecord]
```

A ships the signatures plus an in-memory fake (`meta/fake.py`, same behaviour,
no database) in its first commit so B can build screens before the real
store lands.

### 5.2 Controller hook (owner A)

`GameController.add_listener(fn: Callable[[Notice], None])` — called for every
notice without consuming it (the GUI keeps draining notices as today). The
meta layer uses it to build the run summary.

### 5.3 Run summary JSON

```json
{"rules_seen": {"great_crash": 2}, "items_used": {"peek": 3}, "items_bought": {"swap": 1},
 "rounds": 23, "peak_money": 260, "blackjacks": 2, "doubles": 4, "surrenders": 1,
 "chaos_ai": "default"}
```

### 5.4 Codex (owner C; `chaos_blackjack/codex/`)

```python
CodexEntry(kind, id, name, icon: str, summary: str, detail: Callable[[RunConfig], str],
           demo: DemoScript | None, order: int = 0)
codex_kinds() -> list[CodexKind]                     # rule, mode, item, ai (label, order)
codex_entries(kind=None, config=None) -> list[CodexEntry]

DemoScript(player: tuple[str, ...], dealer: tuple[str, ...], deck: tuple[str, ...],
           chaos: bool, steps: tuple[DemoStep, ...])          # cards like "K♠"
DemoStep(action, arg=None, caption="")   # action: deal | apply_rule | use_item | hit | stand |
                                         #         double | surrender | dealer | caption | pause
run_demo(script, config) -> list[DemoFrame]          # DemoFrame(view: GameView, caption, notices)
```

Demos run on a real `GameController` with a rigged deal, so they always match
the rules and the profile's numbers. Entries without a demo show a large icon
and the text. The GUI only plays frames.

## 6. Screens

| Screen | Owner | Content |
|---|---|---|
| Player select | B | 3 slots: create / continue / rename / delete (confirm) |
| Hub | B | tokens, Start run (mode picker + consumables to bring), Meta shop, History, Codex, Settings, back |
| Meta shop | B | permanent upgrades (level pips, next cost) and consumables (owned count) |
| Run result | B | victory / defeat, token breakdown, back to hub (replaces the ending scene when a player is active) |
| History | B | list of runs, detail with summary |
| Codex | C | tabs per kind, grid of icon + name; detail: animated demo + text with live numbers |

Main menu keeps "Quick play" (no player, as today) and the developer asset gallery.

## 7. Work split

| Step | Agent | Branch | Depends on |
|---|---|---|---|
| 0. Integrate `codex/chaos-poke`, `feat/table-ui` (content packs, casino audio), `feat/animations` + `feat/sound` into `main`; move content-pack `reward_items` onto the shop | B | `integration/main` | — |
| M1–M2 data, meta logic, modes, effects, controller hook, fake | A | `feat/meta-core` | base `codex/chaos-poke` |
| M4a codex registry, providers, demo scripts and `run_demo` (headless, tested) | C | `feat/codex-core` | base `codex/chaos-poke` |
| M3 GUI screens | B | `feat/meta-gui` | step 0, A's fake (then real API) |
| M4b codex GUI | C | `feat/codex-gui` | step 0, M4a |
| M5 simulator upgrades / token economy, first pricing | A | `black-jack-sim` | M2 |

File ownership, to avoid conflicts:

- A: `chaos_blackjack/meta/**`, `chaos_blackjack/modes/**`, `data/migrations/0003_*`, the meta rows in
  `data/seed/default.sql`, `app/config.py` and `app/controller.py` changes, `data/__main__.py`
  (player / history commands), `tests/test_meta_*`.
- B: `gui/scenes/{player_select,hub,meta_shop,run_result,history}.py`, `gui/scenes/menu.py`,
  new `gui/components/*` for those screens, `tests/test_gui_meta_*`.
- C: `chaos_blackjack/codex/**`, `gui/scenes/codex*.py`, new codex components, codex icon specs in
  `gui/assets/manifest.py` (mode icons via `scripts/fetch_icons.py`), `tests/test_codex_*`.
- Shared, append-only: `gui/scenes/__init__.py` imports, `gui/texts.py`, docs. Rebase before merging.

## 8. Rules for every agent

- Repository content in English; `docs/PLAYER_GUIDE.zh-CN.md` stays Chinese and in sync.
- Tests force `CHAOS_USE_LLM=0` and `CHAOS_DB=:memory:`; use a tmp database when data must persist
  between connections. No billed calls.
- Game logic never reads the database; front-ends build a `RunConfig`.
- New numbers go into the balance profile, not into code.
- Done = feature tests + full suite green + `python -m bjsim check` in `black-jack-sim/`
  unchanged (or bands updated on purpose in the same change) + docs updated.
