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
  panel), `tail` (recent lines). Core parts: `core.items` (each item enabled
  by its own move, with when and why not), `core.actions` (the table's own
  moves), `core.rules`, `core.log`, `core.run_stats`. J-54: `j54.deck`,
  `j54.badges`, `j54.contracts`, `j54.goal` (`j54/parts.py`). Poker Head:
  `poker_head.status`, `.loadout`, `.wallet`, `.finance`, `.preparations`
  (`poker_head/parts.py`, reading only `view.table_public`).
- **Native blocks** (`gui/components/side_column.py`): parts that need the
  GUI itself — `core.host` (portrait, speech, poke), `core.deck_pile` (the
  shoe cards fly from; opens the Deck tab when the layout has one),
  `core.buttons` (Shop, Panel; pinned to the bottom), `core.feed` (live
  feed; takes the space left; its heading opens the Log tab).
- **Actions**: `GameController.perform(action, arg)` runs `use_item`, `buy`,
  `choose` and `cancel`, or one of the table's own moves
  (`TableMechanics.table_moves()` / `perform(action, arg)`). Whether an `Act`
  is enabled comes from `GameController.moves()`, the same list the agent
  reads (docs/design/ITEM_ARCHITECTURE.md §7). `gui:` actions are handled by
  the GUI (`gui:panel <tab>`, `gui:log_filter`).
- **Choices**: a command that asks a question sets `view.choice`; the table
  scene, the shop and the run panel open the generic `choice` scene
  (`gui/scenes/choice.py`), which only sends `choose` / `cancel`.
- **Layouts** (`app/layout.py`): `Layout(left, right, panel)`; entries are
  `"part"` or `"part:variant"`; `PanelTab(id, label, parts, hotkey)`.
  `GameMode.layout` (None = `DEFAULT_LAYOUT`).

## 3. Shipped layouts

| | Left | Right | Panel tabs |
|---|---|---|---|
| Default (Classic, mode-less `--chaos`) | host, rules (compact), feed | deck pile, item slots, buttons | Bag (I), Rules, Log (L), Run |
| Poker Head (builds) | same | status, item slots, table actions, deck pile, buttons | Build (B), Bag (I), Finance (F), Rules, Log (L), Run |
| J-54 | same | deck pile, deck strip, badges, item slots, buttons | Bag (I), Deck (K), Contracts, Rules, Log (L), Run (goal + stats) |

## 4. Adding a table with its own mechanics

1. Mechanics: a `TableMechanics` subclass (`app/table_mechanics.py`),
   registered for the mode id; every hook is declared there with a neutral
   default. New interactions are `table_moves()` + `perform(action, arg)`;
   questions go through `GameController.ask(Choice(...))` +
   `resolve_choice`; goods follow docs/design/ITEM_ARCHITECTURE.md.
2. Parts: `register_part("<table>.<name>", build, available=...)`, returning
   existing widget kinds; put clickable things behind an `Act`.
3. Layout: `GameMode(..., layout=Layout(...))`, usually the default columns
   with the table's parts inserted and a few extra tabs.
4. Placeholder icons for any new asset ids (`gui/assets/manifest.py`).

No change to the table scene, the side columns or the run panel is needed.
