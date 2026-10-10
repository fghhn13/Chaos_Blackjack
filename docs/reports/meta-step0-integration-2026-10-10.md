# Meta progression integration, step 0

Integrated on `integration/main`, starting from `codex/chaos-poke` (`3e240e1`):

- `feat/table-ui` (`579302a`), including content packs, casino audio and generic item help.
- `feat/animations` (`c9f0b6a`).
- `feat/sound` (`66962cd`), including approved clips and animation-aligned sound cues.

Retained background Chaos resolution, portrait advice, modal guards, SQLite
balance profiles, complete-config saves and optional memory. Shared item execution
uses the run's registry and profile parameters for both the player and Chaos AI.
Normal Chaos receives the full private context; pack offline examples also accept
this input, while standalone pipeline observations retain their visible-state JSON.

Content manifests now list `shop_items` instead of `reward_items`. Old reward
manifests fail with migration instructions. The example item has a 20-chip
`shop_item` row in the shipped balance profile. Unloaded plugin ids are excluded
before rolling stock, so ordinary runs retain the original shop. Generated packs
include `shop.sql`; `content install-shop <pack> --profile <editable-profile>`
installs and validates prices transactionally. Locked profiles remain protected.
Both guides and the content workflow describe the new acquisition path.

The GUI uses one `SoundManager` and schedules sounds from animation callbacks.
The old notice-based subscription is removed from the table to prevent duplicate
playback. The standalone casino library, original assets, provenance checks and
backend tests remain available. Audio flags, mute/volume controls and asset reload
work with the integrated GUI. Existing async tests now advance through the deal
animation before expecting a worker to start.

Validation:

- Full suite: **326 passed in 16.43s**. Fixtures disable billed calls and use
  in-memory or temporary databases.
- `python -m chaos_blackjack.audio validate`: 54 original clips, five standalone cues, valid CC0 metadata.
- `python scripts/export_sounds.py --verify`: no missing GUI cues.
- `python -m bjsim check --jobs 4`: **all six bands passed**, 87.9s,
  balance `default@2b81a83a89e1`. `PYTHONPATH` and `CHAOS_BLACKJACK_ROOT` explicitly
  targeted the integration worktree and the adapter's `GAME_ROOT` was asserted.
  No bands were changed. The worktree `.git` file makes its revision label
  `unknown`; the imported source path was verified separately.

| Metric | Result |
| --- | ---: |
| EV, no chaos | +0.0000 |
| EV, offline chaos | -0.0968 |
| EV, uniform rules | +0.0047 |
| EV, one peek per hand | +0.1309 |
| Run win rate, no chaos, 25% bets | 0.1980 |
| Run win rate, offline chaos, 25% bets | 0.1020 |

Local `main` can be fast-forwarded to this verified integration. No remote push,
paid model call or change to another agent's uncommitted work is part of step 0.

Follow-up after connecting the meta API: filter unloaded item ids inside
`_roll_shop`, retaining the original immutable config. This preserves the config
fingerprint recorded at run creation and carried by checkpoints. The stock input
and all prices remain identical to the gate above. The full suite passed again:
**326 passed in 14.79s**.
