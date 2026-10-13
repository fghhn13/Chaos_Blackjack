# Table UI: parts, widgets and layouts

Status: **implemented**, 2026-10-13. The contract for how a table's
information reaches the screen, so that dealers with very different
mechanics (J-54's deck today, others later) need no GUI code. Change this
file before changing a contract below.

## 1. Decisions

| Topic | Decision |
|---|---|
| Play area | The middle of the table (hands, bet, action buttons, banners) is the same at every table and is not configurable. |
| Side columns | Built from the mode's layout: an ordered list of parts per column, stacked top to bottom. A part that does not fit is left out and the column says "More in the panel (Tab)". The right column shows compact, visual summaries only. |
| Run panel | An overlay with one tab per group of parts (Tab opens it, Esc / Tab close, Left / Right switch, a tab's letter jumps to it). Read-only except for the actions widgets offer. |
| Run log | The controller keeps the whole run's log (capped at 400 lines, counters kept beyond) and saves it with the run (`RunSaveData.log`). The live feed in the left column stays for recent events and error messages. |
| Items | Quick slots in the right column (click, or keys 1–9 on your turn) and the Bag tab replace the old item list and the `items` scene. |
| Agents | Widgets are GUI-only; agent observations are unchanged. |

## 2. Layers

```
mechanics (TableMechanics) --read--> parts --return--> widgets --drawn by--> renderers
        ^                              |                                    (gui/components/widget_view.py)
        +---- perform(action) <--------+ (a widget's Act, sent back when clicked)
layouts (app/layout.py) name which parts go in which column / tab
```

- **Widgets** (`app/widgets.py`): frozen data, one renderer each — `stat`,
  `badges`, `bars`, `progress`, `list`, `rows`, `slots`, `log`. A clickable
  element carries an `Act(id, arg, enabled)`. `tone` is a colour hint.
  A new kind is a dataclass plus a renderer in `RENDERERS`; prefer combining
  existing kinds.
- **Parts** (`app/parts.py`): `register_part(id, build, available=...)`;
  `build(ctx, variant)` reads `ctx.controller` / `ctx.view` (never changes
  them) and returns widgets. Variants: `compact` (side columns), `full` (the
  panel), `tail` (recent lines). Core parts: `core.items`, `core.rules`,
  `core.log`, `core.run_stats`. J-54: `j54.deck`, `j54.badges`,
  `j54.contracts`, `j54.goal` (`j54/parts.py`).
- **Native blocks** (`gui/components/side_column.py`): parts that need the
  GUI itself — `core.host` (portrait, speech, poke), `core.deck_pile` (the
  shoe cards fly from; opens the Deck tab when the layout has one),
  `core.buttons` (Shop, Panel; pinned to the bottom), `core.feed` (live
  feed; takes the space left; its heading opens the Log tab).
- **Actions**: `GameController.perform(action, arg)` runs `use_item`, or
  hands any other action to the table's `perform(action, arg, controller)`.
  `gui:` actions are handled by the GUI (`gui:panel <tab>`, `gui:log_filter`).
- **Layouts** (`app/layout.py`): `Layout(left, right, panel)`; entries are
  `"part"` or `"part:variant"`; `PanelTab(id, label, parts, hotkey)`.
  `GameMode.layout` (None = `DEFAULT_LAYOUT`).

## 3. Shipped layouts

| | Left | Right | Panel tabs |
|---|---|---|---|
| Default (Classic, Poker Head) | host, rules (compact), feed | deck pile, item slots, buttons | Bag (I), Rules, Log (L), Run |
| J-54 | same | deck pile, deck strip, badges, item slots, buttons | Bag (I), Deck (K), Contracts, Rules, Log (L), Run (goal + stats) |

## 4. Adding a table with its own mechanics

1. Mechanics: a `TableMechanics` subclass (`app/table_mechanics.py`),
   registered for the mode id; optional `perform(action, arg, controller)`
   for new interactions.
2. Parts: `register_part("<table>.<name>", build, available=...)`, returning
   existing widget kinds; put clickable things behind an `Act`.
3. Layout: `GameMode(..., layout=Layout(...))`, usually the default columns
   with the table's parts inserted and a few extra tabs.
4. Placeholder icons for any new asset ids (`gui/assets/manifest.py`).

No change to the table scene, the side columns or the run panel is needed.
