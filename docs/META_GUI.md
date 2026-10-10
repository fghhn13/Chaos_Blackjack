# Player progression GUI

The main menu separates **Quick play** (the existing **New Game** button) from
**Players**. Quick play uses the ordinary table and ending screen without changing
player tokens or history. The developer Asset Gallery remains available.

## Player screens

- **Player select:** three named slots. Create an empty slot, continue to its hub,
  rename an occupied slot, or delete it after confirmation. Name errors are shown
  in the dialog; Enter saves and Esc cancels.
- **Hub:** tokens and run statistics, Classic/Chaos mode selection, consumables to
  bring, Meta shop, History, Codex, Settings and player selection. Each selected
  consumable contributes one copy to the next run. Changing a selection consumes
  nothing; `start_run` performs the actual consumption. Replacing a saved run
  requires confirmation. Continuing that run consumes no additional items.
- **Meta shop:** permanent upgrades display level pips and the next price;
  consumables display the owned count. Every price, limit, description and purchase
  restriction comes from `meta_shop`; the GUI does not calculate upgrade effects.
  Purchases refresh the offers and token balance. Sections and pages accommodate
  additional catalog entries.
- **Run result:** victory/defeat, final bankroll, rounds, token breakdown and the
  updated token balance. Settlement is performed once; repeated input cannot award
  tokens twice. API errors retain the screen and offer a retry.
- **History:** recent runs and their results, with mode, dates, bankroll, tokens,
  upgrades and the run summary. Long details scroll with the wheel or Up/Down.
- **Settings:** mute, master volume and fullscreen. Global GUI shortcuts continue
  to work as before.

Player runs checkpoint at the start and after commands whenever the controller
permits saving. Closing the application leaves the latest checkpoint available
through **Continue saved run**. Esc at the table confirms abandonment and returns
to the player's hub; an abandoned run earns no tokens. Background Chaos calls and
portrait banners retain the existing responsive table behaviour.

## API and agent handoff

Implementation uses the public `chaos_blackjack.meta` functions in section 5.1 of
`docs/design/META_PROGRESSION.md`, including A's added `resume_run`. The GUI
receives `RunStart.controller` and never constructs upgrade effects or writes
player data itself. The GUI validates its backend choice before `start_run` so a
missing real-model configuration cannot spend consumables or create a run.

`gui/components/meta_run.py` registers `meta_table` as a subclass of the existing
table scene. It supplies checkpoints, abandonment and the transition to
`run_result` without changing the shared table file. The normal table still opens
the ordinary ending. `meta_screen.py` supplies common drawing, name entry and a
settings overlay; the five main screens retain their own modules.

C's Codex handoff is `app.scenes.push("codex", player_id=..., config=...)`.
The integrated build registers both codex scenes. `CodexScene.on_enter(config=None,
**params)` accepts this handoff and opens the real gallery with the selected
balance configuration. CI exercises the hub-to-codex-to-detail return path.

Implementation changes are confined to the B-owned scenes, new components,
`tests/test_gui_meta_*`, append-only scene imports and documentation. A's core
dependency is a separate merge commit; step 0 integration fixes are also separate
commits already fast-forwarded into local `main`.

## Preview and verification

For development without touching player saves on disk:

```bash
python -c "from chaos_blackjack.meta.fake import install_fake; install_fake(); from chaos_blackjack.gui.app import App; from chaos_blackjack.app.config import RunConfig; App(run_config=RunConfig(use_llm=False)).run('player_select')"
```

The fake uses A's real service on an in-memory database: Ace in slot 1 has tokens,
upgrades and history, Rookie occupies slot 2, and slot 3 is empty. Normal launch
uses the SQLite-backed service. Tests always disable billed calls and install a
throwaway service.

```bash
python -m pytest tests/test_gui_meta_screens.py
python -m pytest
```

Run `python -m bjsim check` in the separate `black-jack-sim/` repository, explicitly
pointing `PYTHONPATH` and `CHAOS_BLACKJACK_ROOT` at the checkout under test.
