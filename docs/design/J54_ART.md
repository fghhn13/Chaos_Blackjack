# J-54 v2 icon art

Date: 2026-10-17. The 17 icons of J-54's v2 table (conditions, firmwares,
operations, badges; [J54_V2_SPEC.md](J54_V2_SPEC.md) sections 2-4 and 7) are
original code drawings. No source images exist in `black-jack-assets/` for
them, so nothing was processed from raw art.

Source: [scripts/draw_j54_icons.py](../../scripts/draw_j54_icons.py). The script
is deterministic, uses Pillow only and makes no network calls. It draws every
icon at 1024 px from flat shapes and a 5x7 pixel font, then reduces it to
256x256 RGBA with premultiplied alpha, clean alpha edges (at most 8 becomes 0,
at least 250 becomes 255) and transparent corners.

```powershell
python scripts/draw_j54_icons.py                           # review copy + sheet in output/j54_icons/
python scripts/draw_j54_icons.py --out assets/j54 --force  # replace the shipped PNGs
python scripts/validate_assets.py
```

## Visual language

Pixel lettering is J-54's mark: the numbers a calculating machine prints, from
the same pixel grid as its face and the Calculator Deck. Poker Head's icons
use smooth old-gold vector glyphs, so J-54's icons never share a colour group
or a letterform with them.

| Family | Construction | Colour |
|---|---|---|
| Conditions | J-54's dark card stock (`#171719`) with a red rim and a chamfered punch-card corner. A mark at the top shows what the condition reads, and its number sits below. | J-54 red `#C83A3A` |
| Firmwares | The same construction as a cartridge: a notch on top, contact fingers below. The player's rule, so it uses the player's colour. | firmware green `#9CC296` |
| Operations | Solid silhouettes with transparent cutouts, like J-54's v1 icons. Bold enough for the 20 px chips in the right column. | red (Release: gold) |
| Badges | As operations. | gold `#C2AE7E`, Next in amber `#E0B060` |

The colours are the placeholders' own (`_J54_RED`, `_J54_BLACK` and the badge
tones in `chaos_blackjack/gui/assets/manifest.py`), so the table's tones and
tooltips are unchanged.

## The icons

| Asset ID | Mark | Number | Reading |
|---|---|---|---|
| j54_black_plus | hollow spade and club (the black suits) | +1 | J-54's black cards count +1 |
| j54_even_plus | four dots in two pairs | +2 | J-54's even ranks count +2 |
| j54_hearts_scale | solid heart | x2 | J-54's hearts count double |
| j54_stand_19 | marker pointing down at a bar | 19 | J-54 stands on 19 |
| j54_stand_15 | marker pointing down at a bar | 15 | J-54 stands on 15 |
| j54_low_plus | pixel "2-6" | +3 | J-54's low cards count +3 |
| j54_faces_set | crown (the face cards) | =5 | J-54's J, Q, K count 5 |
| fw_mid | pixel "4-6" | =10 | your 4, 5 and 6 count 10 |
| fw_fives | pixel "56" | =10 | your 5s and 6s count 10 |
| fw_low | pixel "2-4" | =10 | your 2, 3 and 4 count 10 |
| fw_margin | arrow lifting a bar | 22 | you bust only above 22 |
| j54_compute | charge meter, three of four cells full | | the compute bank (income in, cap on top) |
| j54_next | skip-to-next arrows against a bar | | the next condition is announced |
| j54_bounty | a card in the crosshairs | | the sample bounty rank |
| j54_cut | a pair of cards sliced cleanly, the top lifted off, a dashed guide | | precise: 2 cards of one rank and colour |
| j54_hot_purge | a fanned hand of three cards beside a hot thermometer | | coarse: 3 cards of one hot rank |
| j54_release | the Joker's card (a jester hat with drooping bells) going down into the deck | | the sealed Joker enters the deck |

The jester hat's outer points hang below its band, so it does not read as Face
Reset's crown. Hot Purge avoids a flame because the v1 Burn Protocol icon
uses one.

## Review

- `python scripts/validate_assets.py`: all 17 OK (256x256 RGBA, real alpha).
- Review sheet: each icon at 128, 64, 36, 30 and 20 px on J-54's card stock,
  the side panel, the felt and ivory (`output/j54_icons/review.png`, git-ignored).
- Headless renders of the J-54 table (right-column badges, operations and the
  active rule) and the Collection's Conditions and Firmware views, in
  `output/j54_icons/preview/`.
- The placeholders stay registered in the manifest as the fallback when a PNG
  is missing; every v2 id now has a final PNG.
