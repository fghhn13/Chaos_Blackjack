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
ends the hand immediately, but settlement can still award a player win.
Modes, the Chaos AI, and plugins without demo metadata show text and an icon.

## Validation

Run `python -m pytest tests/test_codex_registry.py tests/test_codex_demo.py`,
then `python -m pytest`. Feature checks cover each built-in effect, live
tuning, mode/provider extensions, dealer frames, natural payouts, double and
surrender, invalid scripts, deterministic snapshots, and a subprocess that
forbids GUI imports while billed-model settings are enabled. Run the separate
simulator's `python -m bjsim check` with `CHAOS_BLACKJACK_ROOT` pointing at
this checkout to confirm that the existing balance bands stay unchanged.
