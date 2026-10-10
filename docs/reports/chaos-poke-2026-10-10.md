# Chaos portrait interaction verification — 2026-10-10

Branch: `codex/chaos-poke`, based on local `main` at `445d596` (shop and
background LLM integration). Other developers' branches and uncommitted art
were left untouched.

## Implemented behavior

- Click the Chaos portrait in Chaos Mode while betting, taking a player turn,
  or reviewing a settled round. It also works from the shop overlay.
- A modal banner starts one daemon worker from an immutable private snapshot.
  It blocks repeated clicks, including events queued in the same frame, and
  prevents gameplay and purchases while waiting. Three procedural dots animate.
- Continue/Enter dismisses a completed reply. Esc while waiting opens the menu
  confirmation; cancellation keeps the same request. Leaving discards a late
  reply without waiting for the network request to finish.
- Guidance and misdirection are selected independently with 50% probability
  each using a separate random generator, leaving deal randomness untouched.
  This controls the model's requested intent, not factual advice accuracy.
- Private context includes hands and hidden dealer cards, ordered deck, effective
  totals and rules, next-hit outcome, bankroll, inventory, item descriptions, and
  shop offers, sold state, prices and restocking. Public observations retain their
  visibility rules. Ordinary controller-driven Chaos turns share this context.
- Advice has a separate text-only JSON contract, at most 320 characters; it never
  executes card, item, shop or rule actions. Failed or malformed responses show a
  dismissible fallback and do not retry. The real backend makes one completion
  per accepted poke; the offline backend provides local contextual suggestions.
- Run-local memory records selected game events and replies only when explicitly
  enabled through Python configuration. It is bounded (default 32), save/load
  ready, and disabled by default. Disabled memory collects nothing and appears
  in neither prompts nor save data. No player-facing enable switch was added.

## Validation

Full offline suite: **187 passed in 9.35 seconds**, using Python 3.12.7 and
Pygame 2.6.1. Tests force `CHAOS_USE_LLM=0`. No billed API requests were made
for this feature verification; the earlier live latency report covers the
background-call baseline, not this new advice prompt.

```powershell
python -m pytest -o addopts="" -q --basetemp="<external writable temporary directory>"
```

Regression coverage includes the probability boundary, unchanged deal RNG,
private versus public visibility, shop purchase snapshots, effective rule totals,
regular Chaos prompt context, invalid reply rejection without retries, stale
reply rejection, dormant memory, bounded opt-in history and save/load.

Headless GUI coverage exercises repeated clicks before the scene push applies,
animated rendering during a blocked backend call, main-thread notice delivery,
blocked gameplay/purchases, shop resumption, player-turn and result controls,
cancelled exit confirmation, abandoned requests, failures, and window quit.

Offline shop, thinking-banner and completed-reply previews were rendered and
visually inspected at 1280×720. The title, reply text and Continue button fit
without overlap. This is a headless layout check, not a native-window manual
playtest or an assessment of real-model guidance quality.

`git diff --check` passed. English documentation and the Chinese player guide
were updated together.
