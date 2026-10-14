# Cosmetics, achievements and the player profile

Status: **agreed**, 2026-10-12; D2 (data and service), D3 (art aliases) and D4 (GUI) implemented. Extends
`META_PROGRESSION.md`; this file is the contract for the feature. Change it (in its own commit)
before changing a contract below.

**2026-10-14, the chip economy (META_PROGRESSION.md "Chip vault").** "Tokens"
below now means **chips**: the same `tokens` column and fields, shown as chips.
Looks are bought with chips again (`meta.unlock_all_cosmetics` 0; looks a player
was wearing were kept by migration 0008) and count towards lifetime spend; from
membership level 4 the Shop takes 5% off (meta/membership.py). Achievement
rewards are chips, rescaled for the vault (common 50-150, hard 300-500), and
seven achievements cover the build table and risky play: To the Brim (win at
the table's ceiling), In and Out (Poker Head within 5 rounds), All In (a hand
won with a Fourfold Ticket), Saved by the Bell (Bust Insurance turns a bust
into a push), Fresh Start (Fresh Hand into 21), Back from Broke (Poker Head
won after his relief) and Five Ways to Win (a Poker Head win with each core).
Their stats read RunTracker counters (`fourfold_wins`, `insurance_saves`,
`fresh_21`, `core`, `ceiling`) and `summary.after_relief`, which `finish_run`
adds.

## 1. Decisions

| Topic | Decision |
|---|---|
| Effect on play | None. Cosmetics only change art. Game logic, `RunConfig`, run fingerprints, the agent CLI and the simulator ignore them. |
| Ownership | Per player (slot), like tokens and upgrades. Deleting a player deletes its cosmetics, stats and achievements. |
| Cosmetic slots | `deck` (card back and face; a deck may keep the default face), `table`, `chips` (a whole set: 1, 5, 10, 25), `avatar`. The avatar is shown only on Home (player badge) and the profile for now. The slot was `card_back` before migration 0007 (docs/design/AI_MODES.md §5). |
| How cosmetics are obtained | Default (every player owns it), bought with tokens, or rewarded by an achievement. One cosmetic may have several sources. |
| Achievement rewards | Mostly tokens; a few give a cosmetic (optionally tokens as well). |
| Entry point | The player badge on Home opens the new **Profile** screen (avatar, stats, Wardrobe, Achievements). Switching players moves into Profile. |
| Where cosmetics are bought | Only in the Shop's **Cosmetics** area (tokens are spent only in the Shop). The Wardrobe only switches between owned looks. |
| Cosmetic series | `Cosmetic.series` ("core" or an expansion, e.g. "poker_head"); the Shop groups looks by it. |
| Simulator | Not involved. Cosmetic prices and achievement tokens are balance-profile numbers, but no bands are tuned for them yet. |
| First delivery | The pipeline and contracts, so that adding a cosmetic or an achievement is data plus art, not code. The first catalog is small. |

Naming: **cosmetic** = one unlockable look; **slot** = what it skins;
**wardrobe** = the screen where owned cosmetics are equipped (they are bought in the Shop). "Collection"
stays the codex.

## 2. Adding content (the goal of this design)

**A cosmetic** (no code outside the catalog):

1. Art: `<asset id>.png` in `assets/` (via the art pipeline), e.g. `card_back_neon.png`.
2. Catalog: one `register_cosmetic(...)` entry in `chaos_blackjack/cosmetics/catalog.py`
   (or in a content pack).
3. Optional price: one row in `cosmetic_price` in `seed/default.sql`. No row = not sold.

**An achievement** that counts something already tracked:

1. Catalog: one `register_achievement(...)` entry in `chaos_blackjack/achievements/catalog.py`.
2. Reward: one row in `achievement_reward` in `seed/default.sql` (tokens and/or a cosmetic id).

**A new stat** (only when no existing stat fits): one `register_stat(...)` in
`chaos_blackjack/achievements/stats.py` that reads the run, plus the counter in
`RunTracker` if the summary does not contain it yet. Runs settled before the
counter existed count it as 0.

Tests check that every catalog entry is consistent (§7), so a typo fails CI
instead of shipping a broken unlock.

## 3. Cosmetics

**Every look unlocked.** The balance setting `meta.unlock_all_cosmetics`
(on in the shipped `default` profile) makes every player own every look,
hidden ones included, in the wardrobe, the shop and the loadout. Nothing is
written to `player_cosmetic`, so turning it off (in a cloned profile) restores
each player's real collection.

### 3.1 Catalog (code registry, `chaos_blackjack/cosmetics/`)

```python
COSMETIC_SLOTS = ("deck", "table", "chips", "avatar")

# Base asset ids each slot replaces.
SLOT_ASSETS = {
    "deck": ("card_back", "card_front_blank"),
    "table":     ("table_background",),
    "chips":     ("chip_1", "chip_5", "chip_10", "chip_25"),
    "avatar":    ("avatar",),
}

@dataclass(frozen=True)
class Cosmetic:
    id: str                      # unique across slots, e.g. "card_back_neon"
    slot: str                    # one of COSMETIC_SLOTS
    name: str
    description: str = ""
    rarity: str = "common"       # common | rare | epic | legendary (display only)
    assets: dict[str, str] = {}  # base asset id -> this cosmetic's asset id; a base id left out draws itself
    preview: str | None = None   # asset id for the wardrobe tile; default: the slot's first asset
    default: bool = False        # owned by every player
    hidden: bool = False         # not listed until owned
    order: int = 0

register_cosmetic(c: Cosmetic) -> Cosmetic   # later registration with the same id wins (content packs)
cosmetics(slot: str | None = None) -> list[Cosmetic]
```

Every slot has exactly one `default=True` cosmetic with no `assets` (it draws
the base ids), so "nothing equipped" and "the default look" are the same thing.
Defaults: `card_back_standard`, `table_standard`, `chips_standard`,
`avatar_standard`. `register_cosmetic` rejects unknown slots, asset ids outside
the slot and unknown rarities.

Prices are numbers and live in the balance profile (§5.2), not in the catalog.
Where a cosmetic comes from is derived: `default`, a price row, and/or an
achievement whose reward names it.

### 3.2 Rendering: asset aliases

`AssetManager` follows aliases; components keep asking for base ids:

```python
assets.set_aliases(meta.asset_aliases(player_id))   # e.g. {"card_back": "card_back_crimson"}
assets.image("card_back")                           # draws "card_back_crimson"
assets.resolve("card_back")                         # -> "card_back_crimson"
```

- An alias is followed only when its target has a file or a manifest entry;
  otherwise the base id is drawn (missing skin art never shows the magenta
  checker). `source()` / `path()` / `has_file()` ignore aliases, so asset
  validation still reports each id itself.
- The image cache is keyed by the drawn id, so switching looks needs no reload.
- `gui.components.lobby.apply_loadout(app, player_id)` sets the aliases. It runs
  whenever Home resolves the current player (`current_player`) and on
  `choose_player`; screens that equip a cosmetic call it again. Without a
  player the aliases are empty.
- Wardrobe previews ask for the cosmetic's own asset ids directly, so they do
  not depend on what is equipped.

### 3.3 Placeholders

Cosmetics can ship before art. `gui/assets/placeholders.py` draws every slot
with parameters: `lattice_back(base, lattice, trim, edge)`,
`felt_table(felt, felt_light, rail)`, `chip(color, spots)` and
`avatar(emblem, background, ring)` (emblem `bust`, `spade` or `flag`). The
manifest registers the `avatar` base id (category `avatar`, 256x256) and the
built-in looks in `_SKINS`, each with its base asset's category and size, so
`scripts/validate_assets.py` applies the same alpha rules. Final
`<asset id>.png` art in `assets/` replaces a placeholder as usual; a cosmetic
added with art only needs no manifest entry.

### 3.4 Web build

Only equipped cosmetics are loaded at startup. Wardrobe tiles load their
preview lazily and show a neutral frame until it arrives. To be confirmed
against the browser startup cache when implementing.

## 4. Achievements and stats

### 4.1 Stats (registry, `chaos_blackjack/achievements/stats.py`)

A stat is a named number taken from one settled run. For every stat the player
keeps the lifetime `total` (sum over runs) and the `best` single run.

```python
@dataclass(frozen=True)
class RunFacts:                              # a settled run, independent of chaos_blackjack.meta
    mode: str
    result: str                              # victory | defeat
    rounds: int
    peak_money: int
    final_money: int
    summary: Mapping[str, Any]               # META_PROGRESSION.md section 5.3
    # count(key) -> int: a summary counter, or the sum of an {id: n} map; 0 when absent

@dataclass(frozen=True)
class Stat:
    id: str                                  # e.g. "victories_chaos"
    label: str
    from_run: Callable[[RunFacts], int]

register_stat(s: Stat) -> Stat
```

Built-in stats (new summary counters, added to `RunTracker`, are marked *):

| Stat | Run value |
|---|---|
| `runs` | 1 |
| `victories`, `victories_normal`, `victories_chaos` | 1 if won (in that mode) |
| `item_free_victories` | 1 if won without using an item |
| `rounds`, `peak_money` | from the run |
| `blackjacks`, `doubles`, `surrenders` | summary counters |
| `items_used`, `items_bought` | summary totals |
| `hands_won` *, `five_card_hands` * | hands won; hands won holding 5+ cards |
| `win_streak` * | longest win streak in the run |

Codex sightings (`codex_seen`) are not stats; custom checks read them from the
context (e.g. Rule Scholar).

### 4.2 Achievements (registry, `chaos_blackjack/achievements/`)

```python
@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    icon: str = "achievement"        # asset id
    stat: str | None = None          # declarative form: stat id ...
    goal: int = 1                    # ... reaches goal
    scope: str = "total"             # "total": lifetime value; "run": within one run
    check: Callable[[AchievementContext], tuple[int, int]] | None = None   # custom form: (progress, goal)
    hidden: bool = False             # shown as ??? until unlocked
    order: int = 0

register_achievement(a: Achievement) -> Achievement
achievements_catalog() -> list[Achievement]
```

Exactly one of `stat` or `check` is set (checked at registration, as are the
stat id, scope and goal). `AchievementContext(totals, best, seen, run)` holds
the lifetime totals and best runs (current run included), `codex_seen`, and
the run just settled (`RunFacts`, `None` during backfill). Progress is capped
at the goal. Most achievements are one declarative line:

```python
register_achievement(Achievement("first_win", "First Win", "Win a run.", stat="victories", goal=1))
register_achievement(Achievement("high_roller", "High Roller", "Reach 500 chips in one run.",
                                 stat="peak_money", goal=500, scope="run"))
```

### 4.3 Evaluation

- On `finish_run` (inside the same transaction): fold the run into
  `player_stat`, evaluate every locked achievement, record unlocks, grant
  rewards. Abandoned runs count for nothing. `run_history.tokens_earned` (and
  `PlayerStats.tokens_earned`) keep the run's own tokens; achievement tokens
  are paid on top.
- Unlocks are permanent, even if a later balance profile changes a goal.
- **Backfill**: when a player has settled runs but no stats yet (players
  created before migration 0006), the stats are rebuilt from `run_history`
  once and achievements are evaluated with no current run. It runs on the
  first `achievements`, `player_stats` or `finish_run` call (before the new
  run is folded in). Rewards are paid like any other; unlocks found by
  `finish_run` are part of its `RunReward`, the others are simply shown as
  unlocked.
- Achievements never unlock in the middle of a run (results show on Run
  result). A mid-run toast can be added later without changing the data.

## 5. Data (migration 0006)

### 5.1 Player side

```sql
CREATE TABLE player_cosmetic (            -- owned cosmetics (defaults are implicit, not stored)
    player_id   INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    cosmetic_id TEXT    NOT NULL,
    source      TEXT    NOT NULL,         -- shop | achievement:<id> | grant
    acquired_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_id, cosmetic_id)
);
CREATE TABLE player_loadout (             -- equipped; a missing slot means the default
    player_id   INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    slot        TEXT    NOT NULL,
    cosmetic_id TEXT    NOT NULL,
    PRIMARY KEY (player_id, slot)
);
CREATE TABLE player_stat (
    player_id INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    stat_id   TEXT    NOT NULL,
    total     INTEGER NOT NULL DEFAULT 0,   -- sum over settled runs
    best      INTEGER NOT NULL DEFAULT 0,   -- highest single run
    PRIMARY KEY (player_id, stat_id)
);
CREATE TABLE player_achievement (         -- a row = unlocked
    player_id      INTEGER NOT NULL REFERENCES player(id) ON DELETE CASCADE,
    achievement_id TEXT    NOT NULL,
    unlocked_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    run_id         INTEGER REFERENCES run_history(id) ON DELETE SET NULL,
    PRIMARY KEY (player_id, achievement_id)
);
```

Unknown ids (a cosmetic or achievement removed from the catalog) are kept in
the tables and ignored by the API; an equipped unknown cosmetic falls back to
the default.

### 5.2 Balance-profile side

```sql
CREATE TABLE cosmetic_price (
    profile_id  INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    cosmetic_id TEXT    NOT NULL,
    cost        INTEGER NOT NULL CHECK (cost >= 0),
    enabled     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (profile_id, cosmetic_id)
);
CREATE TABLE achievement_reward (
    profile_id     INTEGER NOT NULL REFERENCES balance_profile(id) ON DELETE CASCADE,
    achievement_id TEXT    NOT NULL,
    tokens         INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    cosmetic_ids   TEXT,                   -- comma-separated cosmetic ids; NULL: tokens only (0007)
    PRIMARY KEY (profile_id, achievement_id)
);
```

`chaos_blackjack.data show/set/diff/export` and `clone_profile` cover both tables
(keys `cosmetic.<id>.cost|enabled` and `reward.<achievement id>.tokens|cosmetic_ids`).
An achievement without a reward row unlocks with no reward. Migration 0006
gives existing editable profiles the starting rows.

## 6. Contracts

### 6.1 Meta API additions (`chaos_blackjack/meta/`)

```python
# Models
CosmeticOffer(cosmetic: Cosmetic, owned: bool, equipped: bool,
              price: int | None,            # None: not sold
              can_buy: bool, reason: str,   # reason when not owned and not buyable
              unlock_hint: str)             # e.g. "Achievement: First Win" or "120 tokens"
AchievementState(achievement: Achievement, unlocked: bool, unlocked_at: str | None,
                 progress: int, goal: int, reward_tokens: int, reward_cosmetics: tuple[str, ...])
Unlock(achievement_id, name, tokens, cosmetic_ids: tuple[str, ...])   # only looks that are new to the player

# Service
wardrobe(player_id, slot=None, profile=None) -> list[CosmeticOffer]   # hidden-and-unowned omitted
loadout(player_id) -> dict[str, str]            # slot -> cosmetic id, every slot filled (defaults)
asset_aliases(player_id) -> dict[str, str]      # base asset id -> asset id, for AssetManager
equip(player_id, cosmetic_id) -> dict[str, str] # MetaError if not owned; returns the new loadout
buy_cosmetic(player_id, cosmetic_id, profile=None) -> Player   # MetaError: not sold / owned / too few tokens
MetaService.grant_cosmetic(player_id, cosmetic_id) -> bool   # tools and tests; False if already owned
achievements(player_id, profile=None) -> list[AchievementState]
player_stats(player_id, *, best=False) -> dict[str, int]   # lifetime totals, or best single runs

# Changed
RunReward(..., unlocked: tuple[Unlock, ...] = ())
    # achievement tokens are added to `tokens` and appear in `breakdown`
    # as ("Achievement: <name>", n), after the run lines
```

`Player` gains `avatar: str` (the equipped avatar's asset id) so badges do not
need a second call.

### 6.2 Tools

`python -m chaos_blackjack.data achievements SLOT` (states and progress),
`cosmetics SLOT`, `grant-cosmetic SLOT ID`. The fake service (`meta.fake`)
gives "Ace" a few cosmetics, an equipped card back and some achievements.

## 7. Validation (tests)

- Every slot has exactly one default cosmetic; every cosmetic covers its
  slot's base asset ids; every cosmetic asset id is in the manifest or ships
  as a file.
- Every achievement names a registered stat or has a `check`; goals are >= 1.
- Every `cosmetic_price` / `achievement_reward` row in the seed names a
  registered cosmetic / achievement; reward cosmetics exist.
- Every non-default, non-hidden cosmetic is obtainable (sold or rewarded).
- Service: buy, equip, double buy, not enough tokens, unknown ids, finish_run
  unlocks once, backfill, delete player cascades.

## 8. Screens

```text
Home ── player badge (avatar · name · tokens) ─► Profile
                                                   ├─ Overview      avatar, name, lifetime stats; Rename
                                                   ├─ Wardrobe      tabs per slot: Decks / Tables / Chips / Avatars
                                                   ├─ Achievements  list with progress, rewards, hidden = ???
                                                   └─ Switch player ─► Players
Run result ── unlock cards (achievement, tokens, cosmetic with "Equip" button)
```

- **Profile** (`profile`): opened from the badge. "Switch player" leads to the
  existing Players screen, which keeps create / rename / delete.
- **Wardrobe**: switching only. A scrolling list of the owned looks per slot
  (with "owned / total" on each slot tab) and a "More in the Shop" button.
  A live mini table on the side shows the table, card back, chips and avatar
  together, updating on hover and keyboard focus. Previews draw each look's
  own asset ids (`assets.image(..., alias=False)`).
- **Shop › Cosmetics**: every listed look of the selected series, grouped by
  slot, with the same preview. Each row shows the look, name, rarity and one
  state: Equipped, Equip, a price button (buy; a second click equips), or
  locked with the unlock hint (achievement rewards).
- **Achievements**: unlocked first by default, then by progress. Each row:
  icon, name, description, progress bar (`total` scope) and reward.
- **Run result**: after the token breakdown, one card per unlock.

## 9. Delivery plan

| Step | Content |
|---|---|
| D1 | This document agreed; pointer in `META_PROGRESSION.md`. |
| D2 | Migration 0006, seed rows, registries (cosmetics, stats, achievements), service API, `finish_run` hook, backfill, data CLI, fake, tests (§7). No GUI. |
| D3 | `AssetManager` aliases, `avatar` and skin placeholders, applying the loadout in the app. Tests run headless. |
| D4 | GUI: Profile (Overview / Wardrobe / Achievements), badge with avatar, Run result unlock cards. `docs/META_GUI.md` updated. |
| D5 | First catalog: the two card backs already in `assets/` plus placeholders per slot; 10–15 achievements, most paying tokens. Player guides (EN + zh-CN) updated. |

## 10. Open points

- Exact prices and token rewards (placeholders until the economy is looked at again).
- Mid-run achievement toasts (data model already allows it).
