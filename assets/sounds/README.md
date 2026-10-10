# GUI sound interface and animation timing

The sixteen semantic ids in `chaos_blackjack/gui/assets/sound_manifest.py` are independent of
the source filenames. `scripts/sound_plan.json` records the user-approved CC0
Kenney selection. All sixteen are supplied; missing cues: **none**. There are
24 OGG clips because four families have three random variants each.

## Interface

```python
from chaos_blackjack.gui.audio import SoundManager

audio = SoundManager(asset_dirs, preferences=app.prefs)
audio.play("card_deal")        # bool; immediate, asynchronous, silently skipped if unavailable
audio.set_volume(0.4)          # clamp 0..1, updates current/future owned channels
audio.toggle_mute()            # stop current clips; remember volume
audio.set_muted(True)
audio.refresh()                # F5: stop old clips, clear caches, rescan directories
audio.close()                  # stop/release owned audio resources
```

`Preferences.master_volume` defaults to 0.4, `Preferences.muted` to False.
Preferences are in memory and last for the current App process. The GUI exposes
M mute and +/- volume globally and displays state in the menu footer. Per-cue
gains multiply the master volume. Updating volume while muted keeps mute active.

`paths(id)` returns the selected file/variant paths for inspection. The first
asset directory with any member of the cue wins; an exact `id.ogg`/`.wav` there
overrides variants. SoundManager ignores hidden directories and files outside
`sounds/` subfolders. It caches decoded sounds and never retries loading during
a single play call. Missing/corrupt files or mixer errors return False; SDL's
dummy audio driver is explicitly silent. The mixer adapter uses eight added
channels and drops a cue if all are busy. Other channels are not stopped.
Cooldown is 50 ms per semantic id, shared with numbered variants. Only a
successful playback consumes it. Variants use a private RNG, not game RNG.

`App.audio` is also bound to `App.assets.audio` so every widget receives the same
service without global state. `Button.click()` plays `button_click` before its
callback when enabled; `sound=False` opts out, disabled buttons are silent.
Tests can replace audio with an object implementing `play(id)`; for whole-App
lifecycle tests also provide `close`, `refresh` and mute/volume methods.

## Cues

| id | Trigger | Source |
| --- | --- | --- |
| card_deal | Each card's flight Tween starts; initial four cards follow DEAL_GAP | Casino card-place-1..3 |
| card_flip | Revealing or dealing a face-up card reaches the visual flip midpoint | Casino card-fan-1 |
| chip_place | Left/right click on an enabled betting chip | Casino chip-lay-1..3 |
| chip_stack | Wager drop Tween completes | Casino chips-stack-1 |
| chips_win | Positive-delta settlement Tween starts | Casino chips-stack-4 |
| chips_lose | Negative-delta settlement Tween starts | Casino chips-handle-4 |
| round_win | Normal win banner starts | Interface confirmation_002 |
| round_lose | Normal loss/surrender banner starts | Interface error_002 |
| blackjack | Natural-blackjack banner starts, replaces round_win | Interface confirmation_004 |
| bust | Player-bust result banner starts, replaces round_lose | Interface error_004 |
| push | Push banner starts; no moving-chip cue | Interface tick_001 |
| chaos_glitch | Rule glitch Tween starts | Interface glitch_001..003 |
| item_use | Successful plugin item_used notice | Interface select_002 |
| button_click | Enabled Button.click() | Interface click_001..003 |
| ending_victory | Victory scene enters | Interface confirmation_003 |
| ending_bankrupt | Defeat scene enters | Interface error_007 |

Casino supplies foley, not dedicated result/ending music. Interface confirmation
and error clips serve as the approved prompts. The filenames are semantic
mappings of existing audio, not synthesized jingles. For duration and size,
see [REPORT.md](REPORT.md); provenance and hashes are in [manifest.json](manifest.json).
Original licenses are under [licenses/](licenses/).

## Timing contract

Sound does not change controllers, rules, game state, animation durations or
input acceptance. `TableFx` owns table sound decisions; `table.py` only injects
the manager. Do not also subscribe audio to DRAW_CARD or ROUND_SETTLED or it
will play early and duplicate the animation cues. Existing notice fan-out is
unchanged. Unknown/rejected notices and narration have no cue.

`Tween.on_start` fires once when the existing delay expires; a zero-delay Tween
fires when added, matching its immediately visible first frame. Flip sound is
checked during `TableFx.update()` at raw progress 0.5 for a reveal, or
`FLY_SHARE + (1 - FLY_SHARE) * 0.5` for a dealt face-up card. Face-down deals have
no flip cue. Large frame deltas still detect midpoint crossings once.

The wager cue follows CHIP_DROP completion. Moving-chip cues follow SettleFx
start after its existing wait. Prompt cues follow the banner's existing start
at `wait + SETTLE_TIME * 0.8`; the banner already begins when chips have mostly
left, before the movement fully ends. These timings and all blocking flags are
unchanged. The glitch cue starts with its zero-delay visual Tween. Never use
wall-clock sleeps or add blocking sound tweens to pace the game.
Returning to betting invalidates old-round sound callbacks without canceling
or changing the original animation tweens, so rapid Next Round input cannot
replay a result prompt from a banner that is no longer shown.

## Export and check

Only stdlib + pygame are needed; raw downloads belong in the separate art repo
under `source/sounds/` in new folders. Download metadata and each source choice
must be approved first. The current choices were confirmed on 2026-10-10.

```bash
python scripts/export_sounds.py --source-root "../Black_jack/black-jack-assets/source/sounds" --dry-run
python scripts/export_sounds.py --source-root "../Black_jack/black-jack-assets/source/sounds"
python scripts/export_sounds.py --verify
python -m pytest tests/test_gui_sound.py tests/test_sound_export.py
python -m pytest
```

The exporter refuses existing outputs and original-source destinations. To
inspect another approved plan, supply `--plan` and a new `--out` directory.
Optional `--normalize 0.8` converts the original into peak-normalized WAV; the
default simply copies original bytes. Shipped audio uses no normalization.
`--verify` checks SHA-256, byte count, original-byte preservation and decoding
without raw sources or writes. Tests use fake mixers and SDL dummy, never
speakers or billed model calls, and retain all 137 animation baseline tests.

This task is on `feat/sound`, stacked on `feat/animations` commit `c9f0b6a`.
The PR must target `feat/animations`, not main. Raw source archives stay out of
the game commit; shipped clips, licenses, hashes, report and credits go with it.
