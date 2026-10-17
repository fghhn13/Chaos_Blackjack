# Onboarding

How a new player learns blackjack and meets the tables one by one. Code: `chaos_blackjack/meta/onboarding.py`
(milestones), `chaos_blackjack/tutorial/` (practice table and every line Poker Head says),
`chaos_blackjack/content/basic_strategy.py` (the chart), `chaos_blackjack/gui/scenes/tutorial.py`.

## 1. Who is guided

`player.guided` (migration `0010_player_milestones.sql`) is 1 for every player created since onboarding
shipped and 0 for every older player. A player who is not guided counts as having reached every milestone:
all tables are open and no explanation shows. `CHAOS_TUTORIAL=0` creates new players unguided (the tests set
it; onboarding tests turn it back on).

## 2. Milestones

`player_milestone(player_id, milestone, reached_at)`; `meta.milestones(player_id)` and
`meta.reach(player_id, milestone)`.

| Milestone | Reached when | Effect |
|---|---|---|
| `tutorial` | the practice ends, or the player skips it | New run stops offering the practice |
| `classic_max_win` | a Classic Table win with the top stake (`mode.normal.stake` max, 100) | Poker Head's Table opens; J-54's silhouette appears |
| `poker_head_win` | a Poker Head's Table win | J-54's Table opens |
| `ph_intro_build` | the first Poker Head's Table run starts | the build explanation is not repeated |
| `ph_intro_rules` | Poker Head's first rule of that visit | the rules explanation is not repeated |
| `bet_cap_lifted` | 3 settled Classic runs | Classic bets are no longer capped at a quarter of the cash |
| `first_relief` | Poker Head's first relief (the vault topped up for the Classic Table) | later reliefs get the short speech |
| `j54_intro_table`, `j54_intro_firmware`, `j54_intro_condition`, `j54_intro_release` | J-54's first-visit moments (section 8) | each explanation is not repeated |

`RunReward.milestones` lists the milestones a settled run reached; the result screen announces a table it
opened.

## 3. Table unlocks

`GameMode.requires` is the milestone that opens a table, `reveal` the one from which it shows at all (None:
always) and `teaser` how to open it. `meta.modes()` lists a table not open yet as a silhouette (`unlocked`
False, `hint` = teaser); New run draws it as a shadow named "???" with the hint, and `start_run` refuses it.
Tables with `hidden` (the practice table) are never listed.

* Poker Head's Table: requires `classic_max_win`.
* J-54's Table: requires `poker_head_win`, revealed by `classic_max_win`.

## 4. The practice table

On a guided player's first New run a dialog offers the practice ("Practice" / "Skip"). The practice is the
hidden mode `tutorial`: no Chaos AI, no shop, 100 practice chips, bets capped at a quarter of the cash. It is
not a meta run: nothing leaves the vault and no history is recorded.

Six hands (`tutorial/lessons.py`):

| Hand | Deal | Taught |
|---|---|---|
| 1 | K 7 against a 6 | **Stand**: the dealer must draw and busts |
| 2 | 9 5 against a 7 | **Hit** to 20, then stand |
| 3 | 6 5 against a 6 | **Double** to 21; the dealer busts |
| 4 | 10 6 against a 10 | **Surrender**: half the bet back against a 20 |
| 5 | A K against a 9 | **Natural blackjack**: paid 3 to 2 at once; what a dealer natural does |
| 6 | shuffled | free play; Poker Head reads the chart's advice for every decision |

In hands 1-4 only the taught button works on the first decision (`TutorialTable.augment_actions`). Poker Head
speaks before each bet, when the cards are dealt (in a box beside the cards) and after the result. Esc offers
to skip the rest. Afterwards the strategy chart opens with Poker Head's explanation: the best play still
loses a little, blackjack is a game of luck, and the tables' items are what turn luck into an edge. Closing
it reaches `tutorial`. The chart stays in the Collection ("Strategy chart").

## 5. Bets while learning

Until `bet_cap_lifted`, a guided player's Classic runs cap each bet at 25% of the cash (instead of 50%) and
Poker Head says so in the greeting: chips are not endless.

## 6. First visit to Poker Head's Table

Before the core choice Poker Head explains cores (one chosen at the start, they change what you can do) and
build buffs (bought in the shop, three slots, a full build replaces one, one can be discarded before a bet).
When the first rule arrives he explains rules: they last a few rounds or until removed, two at most, light
and heavy tiers, heavy ones from round 9.

## 7. Going broke

When Poker Head tops up a vault that cannot cover the Classic Table (on the result screen of a lost run, or on
New run), he speaks: the first time he explains relief (enough for a Classic seat, a little more each time up
to a limit the membership raises, the count resets on a win); every later time he says the same two short
lines. Players who are not guided always get the short lines.

## 8. First visit to J-54's Table

Agreed 2026-10-17 for the v2 table ([J54_V2_SPEC.md](J54_V2_SPEC.md)). No practice table: the
mechanics are the real run, so J-54 explains them inside the player's first run, once each, in its cold
programmatic voice, through the same host-dialog beats Poker Head uses (section 6). Code:
`chaos_blackjack/j54/onboarding.py` (the beats and when they fire), lines in `ai/hosts/j54.json`.

| Milestone | Reached when | J-54 explains (3-4 beats) | Highlight while it speaks |
|---|---|---|---|
| `j54_intro_table` | the first J-54 run starts, before the firmware choice | the deck lasts the run and only it changes; the heat strip (green = cutting helps, red = keep); compute (+2 a round, 8 at most) and the two removals (Cut: precise, Hot Purge: cheap and coarse); the goal counts from round 9, and the sealed Joker is the other way to win | the deck strip pulses |
| `j54_intro_firmware` | right after, as the firmware choice opens | a firmware changes only the player's cards for the whole run, is paid from the starting chips, and "No firmware" is a fair pick | — |
| `j54_intro_condition` | the first "Next condition" announcement (the last round of the first segment) | a condition changes only J-54's cards; the camps (classic, anti, loner) and that a camp switch turns the strip around; the announcement is there so compute can be saved for the new map | the announcement badge and the rule entry |
| `j54_intro_release` | the first betting phase in which Release is affordable (compute at the release cost) | the sealed Joker enters the deck, a capture (holding it at a non-losing settlement from round 9) wins, and a thin deck makes it likelier; J-54 adds a card when it draws the Joker itself | the Release button |

One hint without a milestone: the first time the meter reaches the second band (55 %) in a run, a single
line beside the meter says what the band suggests ("The meter says two tenths of the bankroll"); it shows
once per run and never for unguided players. Every beat and hint is skippable (Enter advances, Esc skips);
unguided players (`player.guided` 0) get none of them. The milestones are rows of `player_milestone` like
the others; a run that is resumed from a save does not repeat a beat already reached.

How it is built: `J54Table` calls `j54/onboarding.py` at the four moments (`run_started`, `firmware_offered`,
`entered_betting`), which cues each milestone once per run; `TableMechanics.onboarding(guided)` hands the cues
out with their beats (`HostLine`s, the profile's numbers filled into `{braced}` names), and the GUI's meta table
(`gui/components/meta_run.py`) shows those not reached yet, records them as it queues them, and puts the start's
beats after the greeting, before the firmware choice. A beat's `focus` names layout parts (`j54.deck`,
`core.rules`) or one element of a part by its icon id (`j54.ops/j54_release`, `j54.badges/j54_next`); while it
shows, the table scene keeps those areas bright above the dialog's shade with a pulsing gold ring. The meter
hint is a field of J-54's public snapshot (`hint`, None for the agent and for unguided players) that the meter
part draws in gold as the gauge's label in the side column (adding a row would push the Operations out of the column) and as an entry in the run panel; its round is saved with the table, so a resumed run does not show it twice. A
restored run never cues the start again.

Later, after playtests: a fixed first program for guided players (classic opening, one camp switch in
round 7, the next rule named rather than its camp) so the beats land predictably, and an offline "Click to
ask" that answers what the current screen element is in J-54's voice.

## 9. Not covered yet

Shop and bag steps; replaying the practice after it is finished.
