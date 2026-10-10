# Final main integration, 2026-10-10

The assembled version includes the completed table/content/audio/animation
integration, player progression, progression screens and the codex. Merge
work used `integration/main`; the verified result is fast-forwarded into local
`main` after the documentation and CI commit.

## Included work

| Branch | Included tip | Delivery |
| --- | --- | --- |
| `codex/chaos-poke` | `3e240e1` | Background LLM table turns, portrait advice, optional run memory, SQLite profile integration |
| `feat/table-ui` | `579302a` | Table panels, content packs, item tooltips, casino audio |
| `feat/animations` | `c9f0b6a` | Card, chip, banner and rule animations |
| `feat/sound` | `66962cd` | Sound cues aligned with animation timing |
| `origin/feat/animations` | `3f6b7cf` | Completed animation/sound PR ancestry |
| `feat/meta-gui` | `bcc329f` | Player select, hub, meta shop, results, history, checkpoints |
| `feat/meta-core` | `460ca53` | Players, upgrades, rewards, modes, tracking and simulator helpers |
| `feat/codex-gui` | `edbdaf3` | Reference gallery, live descriptions, animated details; includes `feat/codex-core` at `1926f2c` |

The only merge conflict was the append-only scene registration file. Both
progression and codex imports are retained. The earlier shop fix remains:
unloaded plugin items are filtered when rolling stock, without rewriting the
configuration or its fingerprint. Content-pack items use balance-profile
shop prices; win streaks do not grant them.

README now documents the assembled player flow, codex controls, separate token
and bankroll shops, background model calls, memory opt-in, storage, extension
points and CI. English and Chinese player guides include the live codex and
correct the older Shield/content reward wording.

## Validation

| Check | Result |
| --- | --- |
| Complete game test suite | **436 passed**, 27.37s |
| Application smoke, source checkout | Passed: agent save round-trip, player upgrade, checkpoint/resume, settlement/history, 16 codex entries, 13 real controller demos, GUI hub/codex/detail return |
| Example content pack | Validation passed; scoped item and AI registered, shop integration present |
| Packaged audio | 54 original clips, checksum and CC0 provenance validation passed |
| GUI sound export | Verification passed, no missing cues |
| CLI checks | Automated text demo, offline pipeline probe, agent new/bet/stand and SQLite save listing passed |
| Distribution build | Source distribution and wheel built with `python -m build --no-isolation` |
| Installed wheel | Installed into an isolated environment and exercised from outside the checkout; same API, resource and GUI smoke passed |
| Simulator self-tests | **27 passed**, 20.98s |
| Simulator balance gate | **6/6 bands passed**, 65.3s; no bands or balance values changed |
| Simulator meta commands | Small `upgrades` and four-policy `career` smoke runs passed; these samples do not establish pricing quality |
| Workflow syntax | YAML parsed; matrix test and installed-package jobs present |

The simulator source is the separate local `black-jack-sim` repository at
`d11d84e`. `PYTHONPATH` and `CHAOS_BLACKJACK_ROOT` targeted this integration
checkout, and `bjsim.adapter.GAME_ROOT` was asserted before the balance gate.
Its worktree revision label is `unknown`; the source path was verified directly.

| Balance metric (`default@2b81a83a89e1`) | Value |
| --- | ---: |
| EV, no chaos | +0.0000 |
| EV, offline chaos | -0.0968 |
| EV, uniform rules | +0.0047 |
| EV, one peek per hand | +0.1309 |
| Run win rate, no chaos, 25% bets | 0.1980 |
| Run win rate, offline chaos, 25% bets | 0.1020 |

The first simulator self-test attempt encountered the machine's inaccessible
default pytest temporary directory. Re-running with an explicit writable
`--basetemp` passed all 27 tests. No game or simulator change was needed.

## CI

The workflow runs on push, pull requests to `main` and manual dispatch.

- Ubuntu Python 3.10/3.12 and Windows Python 3.12 run the full suite with GUI
  and art dependencies, application/GUI smoke, content/audio checks and CLI smoke.
- A separate Ubuntu job builds the source distribution and wheel, installs
  the wheel with Pygame, checks it from the runner temporary directory, and
  uploads both distributions as artifacts.
- Runtime checks force `CHAOS_USE_LLM=0`, use memory/temporary databases and
  SDL dummy drivers. They need no model key and make no billed calls.
- The optional simulator remains a separate repository, checked locally rather
  than downloaded by this workflow.

The integrated version was pushed to `origin/main`. The first hosted run
passed Windows and the installed-wheel job, while both Ubuntu jobs exposed a
font-dependent fixture in the history scrolling test: forty items wrapped
into eighteen lines, without overflowing the viewport. The fixture now uses
one hundred items and checks the actual visible capacity and last visible
item, rather than a Windows-specific line count. The correction is validated
locally and pushed for another complete hosted run.
