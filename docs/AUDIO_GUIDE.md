# Casino audio: agent implementation and handoff guide

The GUI has five semantic sound cues backed by the original Kenney Casino Audio
OGG files. The game controller emits notices; `AudioManager` observes those
notices and delegates playback through `AudioBackend`. Game rules, the text CLI,
agent commands and saved runs do not depend on pygame or an audio device.

## Start here

Run from this checkout's repository root:

```bash
python -m chaos_blackjack.audio validate
python -m chaos_blackjack.audio list
pip install -e ".[gui]"
python -m chaos_blackjack.gui --volume 0.4
python -m chaos_blackjack.gui --mute
```

`validate` and `list` are JSON, offline, standard-library-only commands. They do
not open a window or sound device. `validate` checks OGG headers, byte counts,
SHA-256 hashes, source references and the original CC0 license. A failure exits
with code 1. Pygame is required only for playback and the GUI.

To **audibly** preview a cue, explicitly run:

```bash
python -m chaos_blackjack.audio preview deal --volume 0.4
python -m chaos_blackjack.audio preview chips
python -m chaos_blackjack.audio preview win
python -m chaos_blackjack.audio preview lose
python -m chaos_blackjack.audio preview chaos
```

Preview opens no window. Device or clip failures return a JSON error and exit
code 1. Volume zero succeeds without playing a clip.

## Files and ownership

| File | Responsibility |
| --- | --- |
| `chaos_blackjack/contracts/audio.py` | Small output protocol; replacement backends implement it |
| `chaos_blackjack/audio/catalog.py` | Manifest loading, strict volume checks, offline provenance validation |
| `chaos_blackjack/audio/manager.py` | Cue selection, delays, master volume, notice mapping; no pygame import |
| `chaos_blackjack/audio/pygame_backend.py` | Optional asynchronous mixer adapter; caches decoded clips |
| `chaos_blackjack/audio/assets/cues.json` | Stable cue ids, source filenames, individual gains |
| `chaos_blackjack/audio/assets/kenney/` | 54 original OGG files, original `License.txt`, `source.json` |
| `chaos_blackjack/gui/app.py` | Owns one manager and advances it once per frame |
| `chaos_blackjack/gui/scenes/table.py` | Subscribes the manager to the existing notice fan-out |
| `tests/test_audio.py`, `tests/test_audio_gui.py` | Offline policy and SDL dummy-device integration tests |

Source: [Kenney Casino Audio](https://kenney.nl/assets/casino-audio), version 1.1,
[CC0](https://creativecommons.org/publicdomain/zero/1.0/). Kenney permits
commercial use and does not require attribution; see [Kenney support](https://kenney.nl/support).
The downloaded archive's `Audio/` directory contains 54 OGG files, all preserved
byte-for-byte. The archive hash, URL, retrieval date and every file hash are in
`source.json`. The source ZIP and its preview are not runtime dependencies.

This package is casino **foley**, with no dedicated musical win/loss stingers.
The mappings below use chip stacking for winnings and card sweeping for losses.
No generated audio or additional sound library is included.

## Stable cues and notice mapping

| Cue | Original clips | Gain | Trigger |
| --- | --- | --- | --- |
| `deal` | `card-place-1..4.ogg` | 0.70 | `draw_card`; four delayed clips for the initial deal |
| `chips` | `chip-lay-1..3.ogg` | 0.80 | `round_started`, `doubled` |
| `win` | `chips-stack-4.ogg`, `chips-stack-6.ogg` | 0.90 | `round_settled`, outcome `player` or `blackjack` |
| `lose` | `card-shove-1.ogg`, `card-shove-4.ogg` | 0.70 | `round_settled`, outcome `dealer` or `surrender` |
| `chaos` | `card-shuffle.ogg` | 0.65 | `rule_modifier_applied`; `item_used` during the `chaos` phase |

`round_started` plays the wager and schedules initial cards at 80, 160, 240 and
320 ms. The controller currently does not emit `draw_card` for these four cards.
If that behavior changes, remove the synthetic deal schedule to avoid duplicates.
`phase_changed.data["to"]` tracks whether an item use belongs to Chaos AI.
Starting a new round stops old clips and clears delayed cues. Leaving the table
stops them as well. A modal overlay does not destroy the table subscription.

A push, rejected Chaos action, narration, successful player item use and unknown
notices are silent. Bust, surrender and natural-blackjack announcements do not
play result sounds themselves; the subsequent settlement owns that sound.
Send each notice once, in its original order. The adapter does not deduplicate
replayed streams; notices have no unique delivery ids.

## Public interface

```python
from chaos_blackjack.audio import AudioManager
from chaos_blackjack.audio.pygame_backend import PygameAudioBackend

audio = AudioManager(PygameAudioBackend(), volume=0.4, muted=False)
audio.play("deal")                  # bool: played, scheduled, or skipped
audio.play("chaos", delay=0.1)      # seconds; no sleep in the game loop
audio.set_volume(0.3)               # finite 0..1; invalid input raises ValueError
audio.set_muted(True)               # stops current clips and clears queued clips
audio.toggle_mute()                 # restores the remembered volume
audio.handle_notice(notice)         # existing app.notices.Notice, in order
audio.update(dt)                    # seconds; call once per frame
audio.close()                       # stop and release backend resources on exit
```

Read `audio.volume`, `audio.muted`, `audio.effective_volume` and
`audio.available` to display state. `AudioManager()` without a backend is silent
and requires no pygame. Inject a fake `AudioBackend` for deterministic tests or
another implementation for a different client.

The backend protocol exposes `available`, `play(path, gain) -> bool`,
`set_volume(volume)`, `stop()` and `close()`. `play` must return without waiting
for the clip to finish. The manager supplies a per-cue gain; the backend applies
the effective master volume as well. Playback failures are handled by the
backend; invalid cue ids and timing arguments are programmer errors and raise
`ValueError` in the manager.

The pygame adapter owns eight channels added after existing mixer channels.
If all eight are busy, the next clip is dropped. It does not preempt another
cue or alter music volume. Mixer/device and missing-clip errors degrade to
silence; `backend.last_error` is available for diagnosis. Only an adapter that
initialized the mixer itself shuts it down on close. Pygame channel volume is
applied after starting a clip because playback resets that value; see the
[official mixer documentation](https://www.pygame.org/docs/ref/mixer.html#pygame.mixer.Channel.set_volume).

Cue variants rotate in a fixed order. The manager never uses the controller's
random generator, changes a game state, reads a saved deck or makes an LLM call.

## Integration recipe for another GUI agent

1. Create one manager in the application, after frontend initialization.
2. Register `audio.handle_notice` on the existing notice fan-out. In this GUI,
   use `table.subscribe("*", app.audio.handle_notice)` once in `on_enter`.
3. Advance `app.audio.update(dt)` once per frame, even when an overlay is open.
4. Wire controls to `set_volume` / `set_muted`, stop on table exit, close on app exit.
5. Run the tests and validate the packaged assets before handing off.

`GameController.drain_notices()` is destructive. Keep the table's existing
single drain and fan-out so sound, feed and future animations all receive the
same stream. Do not create another audio drain, emit extra core events or play
the same cue both in a button handler and its notice subscriber.

The minimal GUI hooks already follow this recipe. The Sound button and `-` / `+`
buttons live on the main menu; `M` and `+/-` work in all scenes. They adjust
remembered master volume by 10 percentage points, clamped to 0..100%. Changing
volume while muted keeps mute active. The default is 40%, further reduced by
each cue's gain. Startup flags are `--volume 0..1` and `--mute`.
Preferences last for the current app process; they are not saved in a game run
or persisted between launches. No settings storage or background music is added.

For new clips, preserve their license/provenance, update the manifest and its
checksums, and use semantic cue ids at call sites. New notice mappings belong
in `handle_notice`; replacement UI layouts only need the public controls above.
Assets are included in wheels through `tool.setuptools.package-data`.

## Verification and branch handoff

```bash
python -m chaos_blackjack.audio validate
python -m pytest tests/test_audio.py tests/test_audio_gui.py
python -m pytest tests extensions/example/test_example.py
```

GUI tests set SDL audio/video drivers to `dummy`; they decode all 54 source
clips, test live gain/mute, exercise GUI controls, check graceful device failure
and check that notice subscription does not consume feed events. Tests never
make billed model calls. Without pygame, GUI tests skip; install `.[dev,gui]`
to exercise the full checks. A dummy device cannot verify subjective loudness;
use the explicit preview commands for listening.

The source task was prepared on `codex/casino-audio` (commit `1f73c12`), based
on `codex/content-workflow` commit `57fab60`. Both are now integrated into
`feat/table-ui`, the branch used by PR #3. The combined table retains its Chaos
panel, item panel, generic inventory overlay and one audio subscription; item
tooltips read descriptions supplied by content packs. This integration does
not update `main`, and PR #3 was already merged before these additions.
For future UI changes, review the shared GUI files (`app.py`, `scenes/menu.py`,
`scenes/table.py`) and retain one application manager and one subscription.
