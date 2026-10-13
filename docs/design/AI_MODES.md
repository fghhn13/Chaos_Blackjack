# AI modes: one dealer per mode

Status: **agreed**, 2026-10-12. Extends `META_PROGRESSION.md` (modes) and
`COSMETICS_ACHIEVEMENTS.md` (rewards). Change this file (in its own commit)
before changing a contract below.

## 1. Decisions

| Topic | Decision |
|---|---|
| Mode = dealer | Every mode is hosted by one Chaos AI (its look and voice) and has its own Chaos rule pool, item pool and goal. Pools are not shared unless a mode lists the same ids. |
| Classic | Kept as the **Classic Table** (the core series). Hosted by Poker Head, who bends no rules there and has his own Classic lines. (The earlier drawn "house" Chaos AI was removed.) |
| Chaos | Becomes **Poker Head's Table**, the first dealer's table (an expansion). The mode id stays `chaos` so saves, history, stats and achievements keep working; only its name, host and text change. |
| Series | Modes belong to a series: the core series (shown as "Classic Table") or an expansion named after its dealer, listed under "Dealers" (`GameMode.series`, `register_series`, `EXPANSIONS_LABEL`). The Collection and the Shop are grouped by series. |
| Player-facing text | The Collection introduces a dealer as a character (profile and signature line from the line library), not how the AI works. New run gives each table a short description and lists its facts (goal, bets, rules, dealer, payout) separately. |
| Upgrades | Meta upgrades stay shared. An upgrade may be tied to one mode (`meta_upgrade.mode`); it then applies, and can be brought, only in that mode, and the Shop lists it under that mode's series. |
| Shop | Three areas (Upgrades, Cosmetics, Starter items), each split by series. A starter item not tied to a mode belongs to the series whose tables sell its item (`item_series`; Shield, only sold at Poker Head's table, is Poker Head's). |
| Host lines | Before the first round of a new run (not a resumed one), the mode's host says a random greeting from its line library, then one line generated from the run's goal and pools. When the run ends it says a random victory or defeat script before the results. Every beat has its own expression. Enter advances, Esc skips. |
| Rewards | The first win against Poker Head (achievement `chaos_conqueror`, renamed "Poker Face") gives the Poker Head deck and table. An achievement can now reward several cosmetics. |
| Decks | The `card_back` cosmetic slot becomes `deck`: card back and card face together. A deck without its own face keeps the default face. |
| Art | Placeholders first; final art replaces them by asset id later. |

## 2. GameMode

```python
@dataclass(frozen=True)
class GameMode:
    id: str
    name: str
    description: str
    icon: str = ""
    overrides: dict[str, Any] = {}           # RunConfig fields (goal: start_money, target_money, objective, ...)
    unlocked_by: str | None = None
    order: int = 0
    host: str = "poker_head"                 # presentation: a bundled host id
    series: str = "core"                     # "core" or an expansion id
    ai_id: str = "default"                   # Chaos AI pipeline (registry id)
    rules: tuple[str, ...] | None = None     # Chaos rule pool; None = every rule the profile enables
    items: tuple[str, ...] | None = None     # shop item pool; None = every item the profile sells
    intro: tuple[str, ...] = ()              # fallback greeting when the host has no line library
```

`mode.apply(config)` applies `overrides`, then sets `config.mode`,
`config.host`, `config.ai_id`, `config.rule_pool` and filters
`config.shop_prices` to the item pool. The controller treats every
registered rule outside `rule_pool` as disabled; the offline Chaos AI's
weights (`chaos_stub`) are filtered the same way.

New `RunConfig` fields (presentation and pools; not part of the balance
fingerprint):

| Field | Default | Meaning |
|---|---|---|
| `mode` | `""` | the mode id the run was started in |
| `host` | `None` | a bundled host id, or `None` for runs from before modes had hosts (shown as Poker Head) |
| `rule_pool` | `None` | allowed Chaos rules; `None` = no restriction |

Bundled hosts: `chaos_blackjack.content.builtin_persona.host_persona(host)`
returns the host's `Persona`; Poker Head is the only one, and unknown or old
host ids fall back to him. A pack AI's own persona still wins when `ai_id` is
a pack AI.

Series: `Series(id, name, expansion, order)`; `register_series`,
`get_series(id)` (an unknown id is an expansion named after it) and
`series_list()` (core first, then expansions that have a mode). Shipped:
`core` "Classic Table" and `poker_head` "Poker Head".

Built-in modes:

| id | name | series | host | rules | items | goal |
|---|---|---|---|---|---|---|
| `normal` | Classic | `core` | `poker_head` | none (Chaos off) | all | profile (100 → 300) |
| `chaos` | Poker Head | `poker_head` | `poker_head` | all | all | profile (100 → 300) |
| `j54` | J-54's Table (demo) | `j54` | `j54` | J-54's 4 deck rules (exclusive) | J-54's 5 contracts (exclusive) | a random protocol (`J54_TABLE.md`) |

`GameMode.exclusive`: the rules and items of an exclusive mode's pools are
removed from modes whose pool is "all" (their stub and shop; the rules are
also disabled), so Poker Head never applies J-54's rules or sells its
contracts. Balance settings `mode.<id>.config.<field>` override a RunConfig
field at that mode only (J-54 restocks every round). A mode's own mechanics
(deck, fee, goal, own shop offers) plug into the controller through
`app/table_mechanics.py` (`register_table(mode_id, factory)`).

Poker Head's mode icon is `mode_poker_head` (his portrait until a dedicated icon
ships); New run's showcase shows the host's welcome portrait.

Item pools start as "all" for both modes; assigning items per mode is one
tuple per mode.

## 3. Host lines

Line libraries are data: `chaos_blackjack/ai/hosts/<host>.json` holds, per
event (`intro`, `victory`, `defeat`), alternative scripts; a script is a list
of `[mood, text]` beats, and one script is picked at random each time. A
mood is one of the host's portrait expressions. A key `<event>.<mode id>`
(e.g. `intro.normal`) replaces the event at one mode's table; Poker Head uses
it for Classic, where he bends no rules. `summary_mood` is the mood of the
generated line.

```python
host_script(host, event, rng=None, *, mode="") -> list[HostLine]   # HostLine(mood, text)
intro_script(mode, config, rng=None) -> list[HostLine]    # greeting (or mode.intro) + rules_summary(config)
rules_summary(config) -> list[str]                         # "Reach 300 chips from 100 ... I may bend ..."
```

`HostDialog` (gui/components/intro.py) shows the beats over the table with
the host's name and the beat's expression; it takes all input until finished
or skipped. `meta_table` shows the introduction when Run setup starts a new
run (`intro=True`), not on Continue. When a run ends, the table shows the
victory or defeat script before opening the results (pack AIs with their own
persona say nothing here yet).

## 4. Mode-specific upgrades (migration 0007)

`meta_upgrade.mode TEXT` (NULL = every mode); balance key
`upgrade.<id>.mode`. `MetaUpgradeBalance.mode`, `UpgradeOffer.mode`.
`build_run_config` skips permanent upgrades of other modes and refuses
consumables of other modes; Run setup lists only consumables usable in the
selected mode; the Shop lists them under their mode's series and tags them
"<mode name> only". The shipped catalog
has none yet.

## 5. Cosmetics changes (migration 0007)

- Slot `card_back` → `deck` (`SLOT_ASSETS["deck"] = ("card_back", "card_front_blank")`);
  `player_loadout` rows are moved. Cosmetic ids are unchanged.
- `achievement_reward.cosmetic_id` → `cosmetic_ids` (comma-separated);
  `AchievementRewardBalance.cosmetic_ids`, `Unlock.cosmetic_ids`,
  `AchievementState.reward_cosmetics` are tuples. Key `reward.<id>.cosmetic_ids`.
- New looks: `deck_poker_head` (`card_back_poker_head`, `card_front_poker_head`)
  and `table_poker_head`, rewarded by `chaos_conqueror` ("Poker Face": win a
  run against Poker Head). Chaos Velvet (`table_chaos`) moves to the shop.

## 6. Adding a mode later

1. A Chaos AI: built in, or a content pack AI (`ai_id`) with a persona.
2. `register_series(Series(...))` for a new expansion, then
   `register_mode(GameMode(...))` with its series, host, pools and goal; a
   bundled host gets a line library `ai/hosts/<host>.json` (intro, victory,
   defeat, and `<event>.<mode id>` overrides).
3. The Collection and the Shop get a tab for the new expansion automatically
   (docs/design/CODEX.md "Sections by series").
4. Optional: a mode icon (`mode_<id>` asset), mode-specific upgrades
   (`meta_upgrade` rows with `mode`), a `victories_<id>` stat and an
   achievement rewarding the mode's cosmetics.
