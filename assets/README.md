# assets/

Drop final art here as `<asset id>.png` (subfolders are fine). Any file whose
name matches an id in `chaos_blackjack/gui/assets/manifest.py` replaces the
built-in placeholder; press F5 in the game to rescan.

Also searched: `black-jack-assets/exports/` and any dirs in `CHAOS_ASSETS_DIR`.

Fonts live in `assets/fonts/`, named by role: `ui`, `ui-bold`, `display`
(titles and headlines), optionally `display-bold`. Shipped: Barlow (ui) and
Playfair Display SC Bold (display), both SIL OFL 1.1; licences in
`fonts/licenses/`. A single font file with another name is used for every role.

`CREDITS.md` lists third-party art (stand-in icons from game-icons.net,
CC BY 3.0, which requires the attribution to ship with the game).

Tooling (see `.claude/skills/art-asset-pipeline/SKILL.md`):

- `python scripts/asset_tools.py inventory|process|plan`: crop and scale raw art
  into `<id>.png` (needs `pip install -e ".[art]"`)
- `python scripts/validate_assets.py`: size, alpha and naming table
- `python scripts/preview_assets.py`: headless screenshots and check sheets
- `python scripts/fetch_icons.py sheet|export`: stand-in icons from game-icons.net

## Sounds

Final audio lives in `sounds/<sound id>.ogg` or `.wav`; numbered variants use
`<sound id>_1..3.ogg`. Semantic ids, descriptions, variants and gains are defined
in `chaos_blackjack/gui/assets/sound_manifest.py`. Audio scans the same ordered
asset directories as images, looking inside `sounds/` subfolders. The first
directory with a cue wins; an exact id there overrides its variants. F5 rescans
both images and sounds. Missing/corrupt clips, mixer failure and the SDL dummy
audio driver are silent.

The default master volume is 40%. **M** toggles mute and **+/-** changes volume
by 10 percentage points. These values live in `App.prefs` for this process only;
they are not persisted. Each cue has a 50 ms cooldown shared by its variants.

Raw packages live in the separate art repository under
`black-jack-assets/source/sounds/`, in new folders for each approved download.
Download metadata (filename, URL, size and license) and the candidate per id
must be confirmed by the user before downloading and exporting respectively.
`scripts/sound_plan.json` records the approved Kenney Casino Audio / Interface
Sounds selection; both are CC0. No generated audio is used.

```bash
# In a worktree, point to the existing art repo; never copy or overwrite its originals.
python scripts/export_sounds.py --source-root "../Black_jack/black-jack-assets/source/sounds" --dry-run
python scripts/export_sounds.py --source-root "../Black_jack/black-jack-assets/source/sounds"
python scripts/export_sounds.py --verify
```

Alternatively set `CHAOS_ART_REPO` to the art repository. The exporter needs
only the standard library and pygame, decodes without playing, refuses existing
outputs and raw-source output directories, and prints `id -> source -> duration
-> size`. Default exports preserve the original bytes. Optional `--normalize
0.8` converts an existing clip to signed 16-bit WAV with a normalized peak; use
a new `--out` directory to inspect that candidate first. Shipped clips use the
original OGG, with per-cue playback gains; no normalization was applied.
Individual files should stay below 200 KiB. `sounds/manifest.json` preserves
hashes and source links, `sounds/licenses/` preserves the licenses, and
[sounds/REPORT.md](sounds/REPORT.md) is the delivery table. [Sound interface guide](sounds/README.md)
documents animation hooks, cue timing and tests. Attribution is in `CREDITS.md`.
