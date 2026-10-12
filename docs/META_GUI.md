# Player progression GUI

Every run belongs to a player. The game opens on **Home**: the title, the
current player and the next step, over the Chaos dealer's table. There is no
quick play and no in-game asset gallery.

## Screen map

```text
Home ──┬─ Continue run ─────────────────────────────► table (restores the saved run)
       ├─ New run ─► Run setup ─► Start run ────────► table ─► Run result ─► Home
       ├─ Upgrades        (Permanent / Consumables / any new kind)
       ├─ Collection      (rules, modes, items, Chaos AI)
       ├─ Run history
       ├─ player badge ─► Profile (Overview / Wardrobe / Achievements) ─► Switch player ─► Players
       │                                                                   (play / create / rename / delete)
       └─ Settings · Quit
```

## Screens

- **Home** (`home`, the start scene): title and a vertical menu on the left, the
  dealer, felt, cards and chips on the right. The menu follows the player's state:
  - no player saves: **Start game** (primary) asks for a name, creates the player
    in the first free slot and opens Run setup. Tokens and upgrades need a player:
    Upgrades and Run history carry a "Needs a player" tag and the badge reads "No
    player yet". Choosing any of them explains this, highlights Start game with a
    pulsing outline and a "Start here" tag, and gives it keyboard focus. Collection
    works without a player;
  - an unfinished run: **Continue run** is primary and shows mode, round and
    chips; **New run** is secondary;
  - otherwise **New run** is primary and Continue is not shown.

  Upgrades, Collection and Run history follow; Settings and Quit are small text
  actions at the bottom (Esc asks before quitting). The badge at the top right shows
  the current player's avatar, name and tokens and opens Profile. If a saved run cannot be
  restored, Home says so, hides Continue for that run and promotes New run.
- **Players** (`player_select`): three compact slot rows. **Play** makes a slot the
  current player and returns home; empty slots offer **Create player**. Rename and
  Delete live only here; Delete names the player and asks for confirmation.
  Deleting the current player falls back to another save.
- **Run setup** (`run_setup`): a scrolling mode list (each with icon and summary;
  locked modes say how to unlock them), a showcase with the selected mode's full
  rules using live numbers (Chaos shows the dealer in grey violet), a summary of
  the permanent upgrades in effect with the numbers they change, and a scrolling
  list of owned consumables with check boxes. Each checked kind brings one copy;
  the number of kinds is capped (2 by default, raised by Bag Space) and the list
  says how many are in use.
  Browsing and checking spend nothing; `start_run` performs the consumption. With
  an unfinished run, only the final **Start run** asks before abandoning it. The
  mode and checked items are remembered per player for the session.
- **Upgrades** (`meta_shop`): one tab per offer kind present in the catalog and a
  scrolling list. Each row is its buy button and states the price, `Max level` or
  the reason it cannot be bought. Permanent rows show level pips; consumables show
  the owned count. Everything comes from `meta_shop`.
- **Collection** (`codex`): tabs per kind, a grid of entries and animated detail
  pages with live tuning (see `docs/design/CODEX.md`).
- **Run history** (`history`): recent runs on the left, the selected run's
  details on the right. Long details scroll with the wheel or Page Up/Page Down.
- **Run result** (`run_result`): victory/defeat, final bankroll, rounds, token
  breakdown and the updated balance. Settlement happens once; API errors keep the
  screen and offer a retry. **Continue** returns home.
- **Settings** (`meta_settings`): mute, master volume and fullscreen.
- **Profile** (`profile`): opened from the player badge, which shows the equipped
  avatar. The title is the player's name. Tabs:
  - **Overview**: avatar, slot, tokens, achievements and looks owned, a record
    panel (runs, victories, rounds, hands won, blackjacks, best win streak, best
    bankroll), **Rename** and **Change avatar** (opens Wardrobe on Avatars);
  - **Wardrobe**: one sub-tab per cosmetic slot (Card backs, Tables, Chips,
    Avatars) and a scrolling list. Each row is its button: **Equip** an owned
    look, or **Buy · N tokens** to buy and equip it; locked rows say how to get
    them (price and/or achievement). Hidden looks appear once owned. The live
    preview on the right shows the hovered (or focused) look on a small table
    with the rest of the loadout. Equipping applies the look everywhere at once;
  - **Achievements**: unlocked first, then by progress; each row shows the
    reward, a progress bar for counted goals, and "???" for hidden ones.
  **Switch player** opens Players; choosing another player (or deleting this
  one) returns to Home. Cosmetics are bought only here, never in Upgrades.
- **Run result** also lists the achievements the run unlocked (up to five
  cards, the rest are in Profile) with an **Equip** button for a rewarded look.

## Current player

`gui/components/lobby.py` chooses the current player: the last choice (kept in
`app.session` and the `gui.player_id` preference) while that player exists,
otherwise the most recently played save, otherwise the lowest slot. Switching
players refreshes Home's run summary, tokens and every screen opened from it.
Choosing a player also applies their equipped cosmetics
(`apply_loadout` → `AssetManager.set_aliases`), so the table, cards, chips and
Home's vignette draw the player's looks.

## Interaction

- Buttons have default, hover, selected (gold or violet edge) and disabled states.
  Screens built with `WidgetGroup(keyboard=True)` add a visible keyboard focus:
  Up/Down/Tab move it (including into scrolling lists), Enter/Space activate it,
  and Esc goes back. Without a focus, Enter still triggers the screen's primary
  hotkey (for example Start run).
- `ScrollColumn` holds any number of rows, scrolls with the wheel and follows
  keyboard focus, so new modes, upgrades and consumables need no layout change.
- Motion is light and never blocks input: a short fade into Home, cards sliding
  onto the felt, a slow dealer bob and an occasional smirk, and menu entries that
  lean toward the pointer or focus.
- Long names are trimmed with an ellipsis; the 1280×720 canvas scales to any
  window size with letterboxing.

## Extension points

- New modes and challenges: `register_mode` → they appear in Run setup's mode list
  and in Collection.
- New permanent upgrades and consumables: `meta_upgrade` rows → they appear in
  Upgrades (a new `kind` gets its own tab) and, when owned, in Run setup.
- New rules, items and Chaos AI: registries / content packs → Collection.
- New cosmetics and achievements: catalog entries plus seed rows → Wardrobe,
  Achievements and Run result (docs/design/COSMETICS_ACHIEVEMENTS.md §2).
- A future dealer choice belongs in Run setup, beside the mode.

## API

The GUI uses the public `chaos_blackjack.meta` functions in section 5.1 of
`docs/design/META_PROGRESSION.md`. `pending_run(player_id)` summarises the
unfinished run for Home and Players without loading it; `resume_run` restores
it. The GUI validates its backend choice before `start_run`, so a missing
real-model configuration cannot spend consumables or create a run.

`gui/components/meta_run.py` registers `meta_table`, a subclass of the table
scene that adds checkpoints, abandonment (Esc, confirmed, back to Home) and the
transition to `run_result`. `gui/components/lobby.py` holds the shared backdrop,
header, player badge, menu items and list rows; `meta_screen.py` the screen base,
name entry and settings.

## Preview and verification

For development without touching player saves on disk:

```bash
python -c "from chaos_blackjack.meta.fake import install_fake; install_fake(); from chaos_blackjack.gui.app import App; from chaos_blackjack.app.config import RunConfig; App(run_config=RunConfig(use_llm=False)).run('home')"
```

The fake uses the real service on an in-memory database: Ace in slot 1 has tokens,
upgrades and history, Rookie occupies slot 2, and slot 3 is empty. Pass
`install_fake(demo=False)` to see the first-launch Home. Tests always disable
billed calls and install a throwaway service.

```bash
python -m pytest tests/test_gui_meta_screens.py
python -m pytest
```

Run `python -m bjsim check` in the separate `black-jack-sim/` repository, explicitly
pointing `PYTHONPATH` and `CHAOS_BLACKJACK_ROOT` at the checkout under test.
