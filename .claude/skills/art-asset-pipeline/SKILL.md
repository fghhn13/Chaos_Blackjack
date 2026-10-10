---
name: art-asset-pipeline
description: Turn raw generated art (black-jack-assets/ source and reference images) into game-ready `<asset id>.png` files for Chaos Blackjack, validate them against the GUI manifest, render headless in-game previews, and ship them in a PR. Use when the user asks to integrate, export, process, crop, resize, validate, preview or replace placeholder art, chips, cards, backgrounds, character portraits or icons.
---

# Art asset pipeline

Raw art lives in the separate, git-ignored repo `black-jack-assets/`. The game
loads `<id>.png` from (first match wins) `$CHAOS_ASSETS_DIR`, `assets/` (subfolders
allowed), then `black-jack-assets/exports/`. Ids, categories and delivery sizes
come from `chaos_blackjack/gui/assets/manifest.py`; it is the only source of truth.

Tools (all run from the repo root):

| Script | Needs | Purpose |
|---|---|---|
| `scripts/asset_tools.py inventory` | Pillow, numpy | Candidate files per id, misnamed files |
| `scripts/asset_tools.py process` / `plan` | Pillow, numpy | Crop, scale, clean alpha, recolour, export |
| `scripts/validate_assets.py` | pygame | Size / alpha / naming / outline table |
| `scripts/preview_assets.py` | pygame | Headless screenshots and check sheets |
| `scripts/fetch_icons.py sheet` / `export` | pygame | Stand-in icons from game-icons.net (Iconify API, no key) and their CREDITS |

Install: `python -m pip install -e ".[art,dev]"`.

## Hard rules

- **Never modify, rename, move or delete original art** (`black-jack-assets/source/`,
  `references/`, untracked files in `assets/` or `output/`) without the user's
  explicit OK. The processor refuses to write into `source/` and `references/` and
  will not overwrite an output without `--force`.
- **Do not generate new images** and do not call billed LLMs (`--llm`,
  `CHAOS_USE_LLM=1`). Missing art stays a placeholder; list it for the user.
- **Ask before choosing** between candidate sources, before upscaling a too-small
  source (`--allow-upscale`), before picking chip colours, and before any change to
  game layout or drawing code (card rank position, chip label, portrait placement).
  Do not change game logic.
- Repo content is English (code, comments, docs, commits, PR). Chat in the user's
  language.
- Do not commit `black-jack-assets/` or `output/`. Only final PNGs in `assets/` plus
  any tooling changes go into the game repo.

## Workflow

### 1. Inventory (read-only) and confirm

```bash
python scripts/asset_tools.py inventory
python scripts/validate_assets.py
```

Also read `black-jack-assets/docs/asset-list.md`, `generation-plan.md` and the
`README.md` files in `source/` and `references/`: they record which candidates the
user approved. Show the user, per id: the candidates, size and mode, whether the
source is smaller than the delivery size, and what is missing. Then **stop and
get answers** to:

- which candidate to use when there are several (e.g. different card backs),
- whether upscaling is acceptable for under-sized sources (backgrounds are often
  1672×941 against a 1920×1080 target; the game shows them at 1280×720),
- chip colour variants: offline recolour of the `chip_1` master (below), keep
  placeholders, or a code change (needs approval),
- anything that looks off (painted checkerboard, visible text in art, wrong subject).

### 2. Write an export plan

Keep the plan in the art repo so exports are reproducible, e.g.
`black-jack-assets/docs/export-plan.json`. Paths are relative to the game repo root.

```json
{
  "defaults": {"out_dir": "assets"},
  "assets": [
    {"id": "table_background", "src": "black-jack-assets/references/table_approved_v1.png", "allow_upscale": true},
    {"id": "card_back", "src": "black-jack-assets/source/card_back_v1.png"},
    {"id": "card_front_blank", "src": "black-jack-assets/source/card_front_v1.png"},
    {"id": "chip_1", "src": "black-jack-assets/source/chip_1_v1.png"},
    {"id": "chip_5", "src": "black-jack-assets/source/chip_1_v1.png", "recolor_to": "#9A5B50"},
    {"id": "peek", "src": "black-jack-assets/references/peek_approved_v1.png"}
  ]
}
```

Per-entry options (same names as the `process` flags, with underscores):
`fit` (`auto` | `contain` | `cover`), `margin`, `anchor` `[x, y]`, `allow_upscale`,
`alpha_floor`, `alpha_snap`, `trim_threshold`, `recolor_to`, `recolor_from`,
`recolor_line`, `ring` `[inner, outer]`, `max_kb`, `out_dir`.

### 3. Dry-run into a scratch folder first

```bash
python scripts/asset_tools.py plan black-jack-assets/docs/export-plan.json --dry-run
```

To iterate without touching `assets/`, copy the plan with `"out_dir"` pointing to a
scratch folder, process it there, then validate and preview with `--dir <scratch>`.

What `process` does:
- **Alpha cleanup**: alpha ≤ 8 → 0 (removes haze), alpha ≥ 250 → 255. Generated
  images often have bodies at alpha 254, which is not truly opaque.
- **`cover`** (default for backgrounds): scale to cover the target and centre-crop
  (move focus with `anchor`), then flatten to opaque RGB.
- **`contain`** (default for everything else): trim to the alpha bounding box,
  scale without distortion into the target minus a uniform transparent `margin`,
  and centre the result. Default margins: card 2%, chip 4%, character 4%, icon 12%.
- Never stretches. Refuses to upscale unless `allow_upscale` is set, and reports
  the scale factor.
- Resizes with Lanczos on premultiplied alpha (no dark fringes) and zeroes the RGB
  of fully transparent pixels.
- Writes an optimized PNG; above `max_kb` (default 2048) it quantizes to 256
  colours, which suits the flat art style, and says so.
- **`recolor_to`**: repaints a chip's outer ring. Each pixel is treated as a blend
  between the fill and the outline colour, so anti-aliased edges, tick marks and
  the outline survive and the centre stays cream. With the default `ring: auto`
  the inner edge is the darkest circle between 0.3 and 0.9 of the radius. If the
  preview shows a leftover light band or a recoloured centre, set `ring`
  explicitly.

### 4. Validate

```bash
python scripts/validate_assets.py              # what the game will load
python scripts/validate_assets.py --dir assets --require-all
```

FAIL: wrong size; background not fully opaque; card, chip or icon without real
transparency or with opaque corners (painted background or checkerboard);
unreadable file. WARN: file over 2 MB, mostly semi-transparent body, transparency
missing on a character, an id shadowed by a second file, card back and card face
outlines differing by more than 2 px (cards jump when flipped). The table goes into
the PR description.

### 5. Preview in the game (headless)

```bash
python scripts/preview_assets.py --out output/asset_previews
python scripts/preview_assets.py --matte card_back card_front_blank peek chip_1 chaos_calm
```

This writes the menu (chaos off and on), table while betting and mid-round, both
endings, one gallery page per category, matte sheets (asset on dark, felt and
white), and `zoom_cards.png` / `zoom_chips.png` (in-game 100×150 cards and 76×76
chips at ×3). Look at every image yourself and show the key ones to the user.
Check:

- card ranks and suits drawn by code are crisp and do not collide with the art's
  border; card back and face share an outline,
- chip values sit on the plain centre and are legible on every colour,
- the menu portrait (drawn at 74% width, fit to 420×420) does not cover the title
  or buttons and matches the background; note that with chaos on the menu shows
  `chaos_smug`, which may still be a placeholder,
- matte sheets show no white or black halos and no leftover background colour,
- background focal points survive the 16:9 crop and code-drawn UI stays readable.

Report problems. If fixing one needs a layout or drawing change, describe it and
wait for approval.

### 6. Ship

1. Write the final PNGs into `assets/` (`plan` with `"out_dir": "assets"`, add
   `--force` only when replacing files the user agreed to replace).
2. `python -m pytest`. All tests must pass. On Windows sandboxes, add
   `--basetemp <scratch dir>` if the default temp dir is not writable.
3. Branch (e.g. `feat/art-assets`), `git add assets/*.png` plus tooling changes only,
   commit in English, push, and open a PR to `main`. Include the validation table,
   a short note per preview screenshot, the missing ids, and any decisions taken
   (chosen candidates, upscales, chip colours).

## Stand-in icons (game-icons.net)

Until AI art exists for an item or rule icon, use a recoloured game-icons
silhouette. Candidates per id live in `scripts/icon_candidates.json` (first =
current pick).

```bash
python scripts/fetch_icons.py sheet --out output/icon_candidates.png   # show the user
python scripts/fetch_icons.py export --pick swap=card-random           # after they choose
python scripts/asset_tools.py process --id swap --src black-jack-assets/source/game-icons/swap_v1.png --force
```

`export` writes `<id>_v1.png` to `black-jack-assets/source/game-icons/` and the
credits to both that folder and `assets/CREDITS.md`. CC BY 3.0 requires the
credits to ship, so commit `assets/CREDITS.md` with the icons. Requests are
throttled; on HTTP 429 wait a minute (downloads are cached). Set
`CHAOS_ART_REPO` when working from a worktree without `black-jack-assets/`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Game ignores a file | Name is not an exact id (`card-back.png` → `card_back.png`) or a file earlier in the search order shadows it. The validator lists both. |
| "no transparent pixels" | Source has a painted background or checkerboard. Do not fake it; ask for a transparent source. |
| Halo on dark or white mattes | Source edge colour contamination. Try a higher `alpha_floor`; otherwise report it. |
| Card flips jump | Back and face outlines differ. Ask whether to re-export a matching source; never stretch one to fit. |
| PNG over 2 MB | `max_kb` quantization kicks in. If banding shows in a gradient, report it. |
