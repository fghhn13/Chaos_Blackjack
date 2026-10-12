# Procedural unlockable cosmetics

Seventeen original PNGs for the ten existing unlockable wardrobe looks.
Generated with scripts/generate_cosmetic_assets.py, using the drawing and PNG
encoding helpers in scripts/generate_casino_assets.py. No third-party images.

Card silhouettes match the current default card face. Tables keep their rails
inside the visible centre column; chip centres reserve space for runtime values.
The avatar_joker asset depicts White Flag, matching its catalog and achievement.

The existing cosmetic catalog selects these files when a look is equipped.
Press F5 to refresh an open game after adding the files. This art does not grant
cosmetics or change their prices, achievements or player saves.

To regenerate without overwriting originals:

```powershell
python scripts/generate_cosmetic_assets.py --out output/cosmetic_redraw_next
```
