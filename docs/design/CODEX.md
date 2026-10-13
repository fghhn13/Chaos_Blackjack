# Headless codex and controller demonstrations (M4a)

The public API lives in `chaos_blackjack.codex` and follows section 5.4 of
`META_PROGRESSION.md`. It requires neither Pygame nor a player save. The GUI
scene (M4b) consumes the entries and frames after step 0 is integrated.

```python
from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex import codex_entries, codex_kinds, run_demo

config = RunConfig()  # or RunConfig.from_balance(the_selected_balance)
tabs = codex_kinds()
entries = codex_entries("rule", config)
entry = next(e for e in entries if e.id == "great_crash")
text = entry.detail(config)
frames = run_demo(entry.demo, config)
```

`CodexKind(id, label, order)` defines a tab. `codex_entries(kind=None,
config=None)` returns entries sorted by tab order, entry order, name, and id.
Each entry has a kind, id, name, icon asset id, summary, live detail callable,
optional `DemoScript`, and order. Nothing is locked or hidden, including
rules disabled for AI selection and items absent from the current shop.

Detail callables read the supplied `RunConfig` each time. They describe
effective rule modifiers using the existing rule-description function, and
use live prices, shop restocking, Fate Oracle count, mode overrides, bankroll,
bet limits, payouts, dealer policy and Chaos advice settings. Static summaries
and demo captions avoid tunable numeric claims. Rule parameters combine a
configured offline proposal with fixed rule parameters; fixed values win.
When no proposal exists, the registered plugin's defaults apply. In particular,
the shipped profile does not include zero-weight rules in `chaos_stub`, so a
Tiebreaker Shift preview uses its plugin default unless fixed parameters or a
configured proposal select the other side.

## Providers and content packs

`register_codex_provider(kind, fn)` appends a callable receiving `RunConfig`
and returning a list of `CodexEntry`. Registering the same callable twice is
idempotent. Later providers override an existing `(kind, id)` and can also
add entries. A new kind gets a tab with a human-readable label. Returning an
entry with a different kind is an error.

Rule and item providers inspect the live plugin registries on each query;
newly registered plugins appear automatically, with readable fallback names
and no demo. The base registry has no public enumeration API, so private
dictionary access is isolated in `codex/providers.py`. Plugins can optionally
define `codex_name`, `codex_icon`, `codex_summary`, `codex_detail` (a callable
accepting config), `codex_demo`, and `codex_order` on their factory/class.
For item classes, make `codex_detail` a static method. Providers can override
all of this metadata without modifying the underlying plugin.

The mode provider calls agent A's `chaos_blackjack.modes.modes()` at query
time. Until that package lands, it lists the two built-in modes, `normal` and
`chaos`. Once the package exists, it is authoritative; the codex does not keep
an extra mode catalog. The base has one Chaos AI pipeline and no separate AI
registry; its provider exposes `ai/default` and reads policy and run tuning.
Content packs can register additional providers for the `ai` kind.

## Replay behavior

`DemoScript(player, dealer, deck, chaos, steps)` specifies two initial cards
per hand and the remaining deck in draw order. Card strings include rank and
suit, for example `"K♠"`. `DemoStep(action, arg=None, caption="")` supports:

| Action | Argument | Effect |
| --- | --- | --- |
| `deal` | optional integer bet | Rig the initial deal and place a real bet; default is the profile minimum. Exactly one deal is required. |
| `apply_rule` | rule id, or `{"rule_id": id, "params": {...}}` | Explicitly preview a registered rule using live tuning. Fixed profile parameters override script parameters. Requires a chaos script. |
| `use_item` | item id | Use a real item and consume it on success. One copy per scripted use is supplied before dealing. |
| `hit`, `stand`, `double`, `surrender` | none | Call the controller action, respecting live permissions. |
| `dealer` | none | Play the dealer to settlement, capturing a separate frame for every draw and final decision. |
| `caption`, `pause` | none | Capture the current snapshot; these steps never sleep. |

`run_demo(script, config)` returns a list of `DemoFrame(view, caption,
notices)`, where `view` is a real `GameView` and `notices` is a tuple drained
for that frame. Empty captions retain the previous caption. The GUI chooses
playback timing; pauses are repeated snapshots. Dealer hole cards stay hidden
until the controller or an item reveals them.

A dedicated `GameLoop` rigs only the deal. A real `GameController` handles
item effects, actions, natural blackjack, dealer decisions and settlement.
Explicit rule application injects a registered modifier and emits its normal
event; the first rule resolves the waiting Chaos phase through an offline
noop pipeline so the controller checks naturals under that rule. Subsequent
explicit rules check for bust through the controller's existing helper.
Preview selection bypasses AI eligibility, including disabled rules, so every
visible reference entry can demonstrate its effect. This does not change the
AI policy or the caller's config.

The demo copies the config with a fixed local seed and the script's Chaos
switch. It does not alter balance numbers, the caller's config, a player save,
history, or meta currency. Its pipeline is explicitly offline: it never calls
the default backend factory or loads credentials, even with
`CHAOS_USE_LLM=1`. When tuning produces an early natural or terminal result,
remaining gameplay steps stop. Malformed cards, unknown actions/rules, failed
items and illegal actions raise errors instead of faking an effect.

All seven built-in Chaos rules and six items have demos in `codex/scripts.py`.
Reverse Bust demonstrates the current controller behavior: a player bust
ends the hand immediately and settles as a push.
Modes, the Chaos AI, and plugins without demo metadata show text and an icon.

## Validation

Run `python -m pytest tests/test_codex_registry.py tests/test_codex_demo.py`,
then `python -m pytest`. Feature checks cover each built-in effect, live
tuning, mode/provider extensions, dealer frames, natural payouts, double and
surrender, invalid scripts, deterministic snapshots, and a subprocess that
forbids GUI imports while billed-model settings are enabled. Run the separate
simulator's `python -m bjsim check` with `CHAOS_BLACKJACK_ROOT` pointing at
this checkout to confirm that the existing balance bands stay unchanged.

## Integrated content packs (step 0 / M4b)

On the integrated base, providers load the packs selected by
`RunConfig.content_packs` into the same scoped registry as the controller.
Their items (including registered help text) and AI profiles appear without
being added to a codex catalog or leaking into other configurations. The AI
provider uses `Registry.ai_ids()` and `resolve_ai()` when available, retaining
the default-only behavior on the earlier M4a base. Rule previews use the
controller's scoped registry so content-pack rules can be demonstrated too.

## GUI scenes (M4b)

The collection browser uses three columns: a compact character/category sidebar,
a filtered card grid, and the selected entry's scrollable reference. Series tabs
remain at the top. Poker Head additionally offers multi-card, surrender,
precision, double, finance and general build filters, combined with item type.
Selection, filters and scroll positions survive opening a full detail/demo and
returning, and switching series. Every entry remains visible without unlocks.

Poker Head's build table changes the rules through its offline director, so its
page lists the `environment` kind (one entry per environment rule type, with
an example, how it goes away and the director's stages from the balance
profile) instead of registry Chaos rules. The registry rules no dealer's table
uses any more (they still play in the mode-less `--chaos` run) appear on the
Classic Table page.

`CodexEntry` has optional `category`, `style`, `timing`, `price` strings and a
`related` tuple of entry IDs within the same kind. Existing providers may omit
these fields. Build entries supply live effect text and readable prices from the
selected balance profile; raw tuning JSON is not player-facing content. Financial
cards distinguish invested principal from loan advances and repayment. The 41
Poker Head entries request their product ID directly, resolving the adopted
transparent PNGs under `assets/poker_head/` through the normal asset manager.

Clicking a card selects it inline. The reference offers a full-detail or demo
button and links to related entries. Its mouse wheel scroll is independent of
the card grid. Entries without demos use a compact icon/summary column beside a
wide text panel, with playback controls hidden. Existing animated demos retain
their playback and seeking controls.

Open the gallery with `app.scenes.push("codex", config=config)`; `config` is
optional and defaults to `app.run_config`. An optional `kind` selects the
initial tab. The home screen uses this entry point without importing the
scene class. For development, launch `python -m chaos_blackjack.gui --scene
codex`. The existing scene package imports register both `codex` and
`codex_detail`.

The gallery has series tabs and a scrollable card grid. Every entry is available.
Click a card to select its inline reference; the reference button or Enter opens
its full detail/demo. Tab changes series (Shift-Tab goes back), arrows select
cards, and the wheel or Page Up/Page Down scrolls the grid. The wheel over the
reference scrolls that text independently. Back/Escape returns to the caller;
returning from a detail preserves filters, selection and both scroll positions.

The detail scene accepts `entry=CodexEntry` and the same optional config.
It evaluates the detail and demo using that configuration, then retains only
the resulting frames for playback. Existing `CardRenderer` and `TableFx`
handle card movement, hole-card flips, rule glitches and bankroll animation;
no controller action is executed during playback. Demos stop on their last
frame. Space pauses/plays, R replays, Left/Right steps through snapshots.
Seeking pauses and shows the selected frame immediately. The right-hand
description wraps and scrolls with the wheel or Page Up/Page Down. Entries
without a demo show a compact icon/summary column and a wide text panel, hiding
playback controls. A demo incompatible with the selected settings falls back to
readable text and hides playback.

Mode icon specs live in the manifest. The final transparent PNGs were fetched
through `scripts/fetch_icons.py` and exported with `scripts/asset_tools.py`:
`mode_normal.png` (Classic Table) uses game-icons' `card-ace-spades`, and `mode_chaos.png`
uses `card-joker`. Both are 256 by 256 RGBA and pass asset validation.
Attribution is appended to `assets/CREDITS.md`. Poker Head's Table now uses `mode_poker_head` (his portrait until a dedicated icon ships), so `mode_chaos.png` is no longer shown. Procedural fallbacks remain
available when art is not installed. No existing source art was changed.

## Sections by series

The gallery is grouped by series (docs/design/AI_MODES.md): the **Core
series** (labelled "Classic Table"), then a **Dealers** group with one tab per expansion (currently
Poker Head). `codex_sections(config) -> list[CodexSection]` returns:

- **Classic Table**: its tables, the items sold at every table (or at
  none), Chaos rules no expansion uses, and guest Chaos AIs from content packs;
- one section per dealer: the character's portrait, name, profile and
  signature line (`profile` and `signature` in the host's line library;
  system details stay on detail pages), its table (the mode entry, behind
  "About this table"), then **Chaos rules** (the union of its tables' rule pools) and
  **Table items** (items only its tables sell; Classic never sells Shield, so
  Shield belongs to Poker Head).

`CodexSection(id, label, groups, expansion, host, mode, portrait, summary, quote,
entries)` and `CodexGroup(id, label, entries, empty)` are headless. Every
rule, item and mode appears in some section, so nothing is hidden; a new
expansion gets its own tab automatically. The GUI displays a compact identity
panel (with "Table rules"), category navigation, cards and an inline reference.
Long grids scroll with the wheel or Page Up/Page Down, and Tab cycles sections.
`codex_kinds` and `codex_entries` remain available for tools
and tests.

`tests/test_codex_gui.py` verifies gallery/detail navigation, sections, scrolling, pause,
single stepping, replay, the final-frame stop, live numbers in text and
frames, scroll boundaries, icon fallbacks, text-only entries, content-pack
isolation, and rendering of every built-in frame. The art pipeline's missing
background/card/character files continue to use their existing placeholders.
