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
