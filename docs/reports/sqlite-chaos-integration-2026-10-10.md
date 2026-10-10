# SQLite profiles and Chaos interaction integration

Date: 2026-10-10

## Scope

Integrated `feat/sqlite-data` into `codex/chaos-poke` in its isolated worktree.
The initial merge (`52d025b`) includes the public, profile-aware betting helpers,
parameter-aware rule descriptions and SQLite save/preferences work through
`434b5b4`. The subsequent merge includes profile management through `a4add49`.
Claude's original checkout, uncommitted assets and other branches were left intact.

## Compatibility changes

- Kept the SQLite-backed `RunConfig.from_balance`, `to_dict` and `from_dict`.
  Added the interaction settings to the seed, typed balance mapping and config:
  `chaos.guidance_probability` defaults to 0.5 (range 0..1),
  `chaos.memory_enabled` defaults to false, and `chaos.memory_limit` defaults to
  32 (minimum 1). Config validation remains in `__post_init__`.
- Added migration `0003_chaos_interaction_settings.sql` to populate missing
  interaction settings in existing profiles while retaining their tuning.
  Profile-management commands accept and validate these new settings.
- Removed the agent's hand-maintained config serialization. Run saves retain the
  complete config and enabled memory, so resuming a run preserves its original
  numbers and memory setting even after its database profile changes. Legacy
  saves without a config still use the caller's base config.
- Kept controller restoration via `replace(base, ...)`, both import groups,
  offline Chaos reseeding and the full private context passed to Chaos resolution.
- The model context uses `GameController.bet_limits()` and includes profile name,
  minimum bet and maximum bet fraction. Each shop offer uses the same affordability
  check as the view: the purchase must leave enough money for a legal bet.
  Offline guidance and misleading advice both exclude unaffordable offers.
- Both normal Chaos action prompts and portrait advice receive filtered rule
  permissions, fixed rule parameters and descriptions of their effective values.
  Disabled rules are excluded from the advertised choices. Profile item parameters
  are included in context and applied when Chaos uses an item.
- Updated the README and both player/agent guides. Portrait interaction retains
  its asynchronous worker and click-blocking banner. The default guidance chance
  remains 50%; memory remains an explicit opt-in setting.

## Regression coverage

The non-default profile tests use starting money 40, minimum bet 5 and maximum
bet fraction 0.25. The context exposes a bet range of 5..10. A 30-chip item is
unaffordable: the remaining 10 chips cannot support the minimum 5-chip bet under
that fraction. Neither advice intent recommends it. Buying a 10-chip item leaves
a bet range of 5..7.

Additional tests cover disabled rules, fixed rule parameters overriding model
parameters, descriptions matching actual rules, tuned Chaos item effects,
full-config and memory save/load, migration of existing profiles, and validation
and rollback of profile-setting edits.

## Validation

- Full suite: **254 passed in 10.57s**. Test fixtures force `CHAOS_DB=:memory:`
  except explicit persistence cases using temporary databases, and disable paid
  LLM calls. Command: `python -m pytest -o addopts="" -q --basetemp=<temporary-dir>`.
- Simulator: **all six balance bands passed**, in 56.1 seconds. Executed
  `python -m bjsim check --jobs 4 --out <report-path>` from `black-jack-sim/`, with
  `PYTHONPATH` and `CHAOS_BLACKJACK_ROOT` pointing to the merged worktree,
  `CHAOS_DB=:memory:` and `CHAOS_USE_LLM=0`. Before the run, asserted that the
  adapter's `GAME_ROOT` resolved to this worktree. Its report labels the Git
  revision `unknown` because this checkout uses a worktree `.git` file; the
  imported source location was checked separately. Balance fingerprint:
  `default@6b804269713d`.

| Simulator metric | Result | Allowed band | Status |
| --- | ---: | --- | --- |
| EV, no chaos | +0.0000 | [-0.020, +0.020] | Pass |
| EV, offline stub chaos | -0.0968 | [-0.120, -0.075] | Pass |
| EV, uniform rule mix | +0.0047 | [-0.015, +0.025] | Pass |
| EV, one peek per hand | +0.1309 | [+0.110, +0.150] | Pass |
| Run win rate, no chaos, 25% bets | 0.1980 | [0.165, 0.235] | Pass |
| Run win rate, offline stub, 25% bets | 0.1020 | [0.075, 0.130] | Pass |

No paid API calls were made during this integration. The earlier memory-enabled
live API round remains documented in `chaos-memory-live-2026-10-10.md`; that
historical run predates this SQLite merge.
