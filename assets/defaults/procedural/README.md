# Casino Green and the flat starter Chaos AI

Original procedural art from scripts/generate_house_assets.py.

The four house portraits are simple geometric half-body figures: purple rounded
heads, triangle horns, a muted green uniform and folded white gloves. Calm, smug,
laugh and angry expressions use short strokes, dots and arcs. All portraits are
512 x 512 transparent PNGs with identical framing. Casino Green remains the same
1920 x 1080 opaque table from the previous revision.

Installed in assets/defaults/procedural/. Restart the game to reload portraits.
Poker Head now hosts every table, so these portraits are no longer a table host; they
are the fallback portrait for content-pack Chaos AIs that ship no persona of their own.

Regenerate from the game repository root with a new output directory:

```powershell
python scripts/generate_house_assets.py --out output/house_starter_next
```

All five PNGs pass the repository validator. portraits_200px.png shows the actual
in-game portrait scale. No layout, rules, loadout or saved profile is changed.
