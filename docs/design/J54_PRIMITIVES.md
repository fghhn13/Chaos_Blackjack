# J-54: game primitives

Status: **framework agreed**, 2026-10-15; **v2 decisions taken**, 2026-10-16
(section 0b, from the rule lab's Round 5; verdicts from Round 6 the same
day); **direction widened after Round 7** the same evening (section 0c: the
goal is a build space, judged by strategy diversity, not a single tuned
run). Nothing here is implemented beyond
what `J54_TABLE.md` section 0 lists. This file replaces "design a level" with
"design the parts levels are made of"; levels (math problems) come later and
are picked with the problem validator (section 9).

## 0. Core idea

- **J-54 (the robot dealer) acts by a fixed algorithm.** It never learns or
  adapts mid-run; everything it does is a primitive with parameters.
- **The player changes the deck** with a limited set of operations (a budget).
- **Each side follows its own effect rules**: the same card can be worth
  something different to the player and to J-54.
- A small set of composable primitives yields many different math problems.
  The deck-shaping *direction* a problem asks for is the player's main goal.

Decisions so far:

| Topic | Decision |
|---|---|
| Base game | Each round is still **one blackjack hand** (bust above 21, dealer algorithm, settle). Effect rules change card values inside the hand. Bust is what makes drawing cost something; without it the player would just draw everything. |
| Global sub-mode | Shuffle × replacement is a **global setting of the table**, fixed for the whole run. It is not an item and not a Chaos rule. |
| Chaos rules | Extra, on top of the sub-mode. They create **asymmetry** between the two sides (different effect rules, a different draw method), which is what makes changing a shared deck shift the advantage. |
| Player perturbation | First batch: effect rules on J-54's side only. Player-side rules come later; the one candidate so far is a run-long **firmware** the player picks at the start (section 0b, decision 6). |
| Effect rules | First batch: **stateless** rules only (section 4); all values are integers. |
| Information | Inspect is a primitive with a cost and a range, not an always-on view (section 3). The win-rate bar and the hand's EV are always shown as a meter; they are a betting signal, not a goal (section 0b). |

## 0b. Decisions for v2 (2026-10-16)

Taken after Round 5 of the rule lab (`j54-lab/FINDINGS.md`, reports
`2026-10-16-e1` to `-e4`), then tested in Round 6 (reports `-r6-e1` to
`-r6-e5`). The lab's model: one hand per round, shuffled + replaced, J-54
drawing to 17, operations paid from a separate budget of 2 per round banked
up to 8, 100 starting chips, 2000 seeds per cell. Each decision names the
evidence it rests on, Round 6's verdict, and what is still unverified.

| # | Decision (as it stands after Round 6) | Evidence | Verdict and what changed | Not yet verified |
|---|---|---|---|---|
| 1 | **The protocol is a chip target**, won the first time chips reach it, over a fixed run of 16 rounds; the target only counts from round 9 (insurance against lucky early wins). Bets scale with the bankroll under the existing 5 to half-bankroll rule, with no tighter cap. The bar and EV are a meter for bet sizing, shown in **bands** (bar below 50 %: minimum bet; 50–55 %: 10 % of the bankroll; 55–60 %: 20 %; 60 % and up: 30 %); they are never the goal. The target is tuned with the pool: **2.0× on a neutral pool**, 2.5× on a generous one. Capture (the Joker) stays as the second protocol. | Round 5: shaping beats idling on "final chips ≥ 1.5×" by 19–50 pp; a bar read at one round only measures the schedule's phase. Round 6: stopping at the target *widens* the gap (+60 vs +50 pp at 2.5×); idle reaches 2.5× in 4.9 % of runs on the generous pool and 0.0 % on the neutral one, a fifth of those wins early; "counts from round 9" removes every early win for 1.2 pp, "hold two round ends" costs 10 pp; a bands bettor keeps 76–90 % of the oracle Kelly bettor's gap and can never over-bet a negative-EV deck (bar ≥ 50 % implies EV ≥ 0); a bet cap cuts skill, not luck. On the neutral pool with bands betting shapers reach 2.0× in 48 % of runs (idle 0 %), 2.5× in 35 %. | **Stands**, with the target coupled to the pool, the round-9 rule and the bands meter added. | How much of the gap a *human-feasible shaping policy* keeps (every gap so far is between beam-search optimisers); the effect of double and surrender, which the lab does not model, on the bands and the target. |
| 2 | **Insertion is J-54's move, removal is the player's**, but J-54's injections must be small and announced. The player's menu holds Cut, Purge and the Joker; Inject and Refine are dropped. J-54 injects at most 1 card per rule switch (or 3 cards once or twice a run), or pairs an injection with a budget bonus. Injections are never "thematic" (the rank a rule favours for J-54 is a ten, which helps the player). The Joker is a late-run purchase priced at most 2. | Round 5: 0 insertion steps in 43 single-deck screens; the Joker is worth +0.5–0.8 pp against +1–4 pp for removal. Round 6 corrected the first half: over multi-round runs the player's Inject *was* used (47 steps in 16 of 21 shaped runs, re-inserting aces and tens after an anti-camp phase), though dropping it costs only ~0.5 pp of wins. J-54 injecting 3 cards at every switch is a **flattener**: idle loses nothing, shapers lose 24.5 pp of wins (43.7 → 19.2 %) and the saver's lead over greedy disappears, because 3 cards dilute a 20–30-card shaped deck and cost budget to remove again. | **Needs a change**: the size and frequency of J-54's injections (as specified they halve the shapers' win rate); the player's Inject is dropped for simplicity, not because it was useless. | The safe injection size (1 per switch; 3 twice a run; with a budget bonus) and whether the saver's lead survives it. |
| 3 | **The deck strip is a heat map computed exactly for the active rule set**, never summed from per-rule colours. Rule names stay neutral, so the map, not the name, tells the player which way a rule points. | Summing two rules' colours gets the sign wrong in 18–20 % of readable groups, up to 18 of 26 where rules pull apart. Most "J-54 bonuses" raise the player's bar under draw-to-17, which a human reads backwards. Round 6: a "ties go to J-54" tax is invisible on the bar and the map (0 flips), so the pool can be taxed without moving the colours. | **Stands.** | Whether humans read the two sign maps (classic / anti) in play; playtest only. |
| 4 | **Difficulty is information.** Easy: the whole schedule is shown. Normal: at each switch J-54 announces the next rule's camp, not the rule. Hard: no warning. A second dial is the number of classic ↔ anti switches per run. | Announcing the camp keeps 60–94 % of a one-round warning's value; lead 2 adds nothing over lead 1; the full schedule is a different game (+20–27 pp). Round 6: on the neutral pool greedy play collapses in cross-camp schedules (0.1 %) while lookahead / saving reach ~40 %, so reading the schedule is necessary, not optional; but J-54's injections at 3 per switch erase the saver's lead, so decision 2's size also decides how much of this dial is left. | **Stands**, coupled to decision 2. | Win-rate distributions over *random* schedules by number of cross-camp switches (all runs so far used seven hand-made schedules with a 3-round period), to set the dials. |
| 5 | **The rule pool is classified by sign pattern** and **tuned rule by rule** to a starting EV near zero. Classes: classic (black +1, even +2, hearts ×2, stands on 19), anti-A (stands on 15), anti-B (low cards +3), loner (faces count 5); "+1 advantage per black card" used the advantage primitive that v2 drops and needs a replacement. Each rule's own parameter is tuned into the band [−0.04, +0.01] bets per hand on the starting deck; "ties go to J-54" is the only shared tax. No amplification. Inert rules (aces hard 1, 7–9 count 10) are cut. | Clustering the removal signs reproduces exactly two camps. Doubling parameters raises the per-card direction only ×1.2, degenerates 3 of 8 rules and leaves the skill gap unchanged. Round 6: a shared handicap ladder cannot make the pool neutral (two rules already at −0.13 / −0.19, two still positive at the top step); **base advantage rotates the anti rules** (cosine 0.56–0.65, the 9s flip) and **breaks "stands on 19" at +2** (J-54 totals 21–23, the player wins only on its bust and card values stop mattering); "stands on 15" and "low +3" degenerate at cap 2 once Jokers are in the deck (92 / 90.5 %). On the roughly neutral pool the gap is all skill: idle 0.0 %, best 45 % at 2.5× and 57 % at 2.0×. | **Needs a change**: per-rule tuning instead of a shared handicap; a check that no tuning removes the player's hand from the comparison; the Joker's effect on the anti rules. | The tuned pool itself and whether every direction survives the tuning. |
| 6 | **Adopted with a price: a player firmware.** At the start the player may pick one run-long player-side rule that changes which cards are good for them. Reference build: **"your 5s and 6s count 10"** at 80 starting chips (instead of 100). **"Your 4–6 count 10"** is too strong as it stands (it needs 80 chips plus half income for 8 rounds, or a weaker form such as "count 9"). "5s count 10" and "tens count 9" are not builds (neutral on average, ±25–40 pp by schedule). | Round 5: "4–6 count 10" is the one new direction among 8 candidates. Round 6: every firmware is a distinct plan (25–48 % of moved cards in common with the plain plan); "4–6 count 10" lifts the 2.5× win rate from 34 to 69 % (+63 pp in cross-camp) because keeping 4–6 serves both camps, i.e. it dissolves the cross-camp tension rather than playing it; "5s and 6s count 10" gives +14 pp and is evened by 80 starting chips (+3 pp after). Firmwares gain most under the anti rules and the loner. | **Needs a change**: from candidate to adopted with a price; the reference build is the milder rule. | A weakened "4–6" variant; firmware × difficulty tier and × injections; more clean candidates for a menu of three. |

Also kept from the lab's setup, without a separate test: operations are paid
from a **compute budget** (income per round, bankable with a cap), not from
chips; chips are life and the goal. The per-group **cap stays 2** (cap 3 lifts
ideal decks by 4–26 pp and collapses them onto "aces, 2s, 3s" under player
rules). Entropy stays as background pressure. Sub-mode: shuffled + replaced.
J-54's advantage `A` (section 5) is dropped from v2: it added a difficulty
scalar, never a new direction, and as a handicap it rotates or breaks rules.

The v2 configuration these decisions add up to, pending section 12's
verification: shuffled + replaced; 16 rounds; the run ends the first time
chips reach the target, counted from round 9; menu Cut / Purge / Joker; a
rule pool tuned rule by rule to a neutral starting EV with ties as the only
shared tax; target 2.0× on that pool; the meter shows the bar in betting
bands; the next rule's camp is announced at each switch (normal tier); J-54
injects at most 1 card per switch or compensates with budget; an optional
firmware priced in starting chips.

## 0c. Direction after Round 7: a build space, judged by strategy diversity (2026-10-16)

Round 7 (section 10) tested the inputs of that configuration and found a
contradiction inside it: **tuning every rule to a neutral starting EV pulls
every rule towards plain blackjack**, and with the anti camp gone the saving
decision, the information tiers and the "read J-54's program" layer all lose
their value (strict sign flips between any two tuned rules 0–3; saving within
±1 pp of spending; the three tiers 1–3 pp apart). The Round 5–6 game was a
property of strong, non-neutral rules. Round 7 also showed that the
*opening* rule, not the number of switches, drives a run on the neutral pool,
and that no J-54 injection is a fair pressure without a budget bonus (with
one it is a wash: a flavour event, not pressure).

The owner's conclusion: do not hang the table on one tuned configuration.
What has to exist is a **build space**: the player's operations must be worth
different things in different runs, so the player chooses rather than solves.

**Three axes, each owning one thing.**

| Axis | Owns | Set by |
|---|---|---|
| **Goal** (the run's protocol; section 6) | the *direction*: which deck shape the player wants | J-54 draws one per run; an optional secondary goal may be added |
| **Perturbation** (J-54's rules; section 4) | how that direction *rotates* during the run | J-54's schedule |
| **Sub-mode** (shuffle × replacement; section 2a) | the *tools*: which operations can move the deck there | **J-54 announces it at the start** (decided 2026-10-16); the player adapts |

Hypotheses on goals and deck shapes, to be measured: Score / Capital wants
aces and tens in a thin deck; Capture (draw the Joker yourself) wants a thin
deck of *low* cards so the player can keep hitting; "J-54 busts N times"
wants low cards too; "N naturals" wants aces and tens to the extreme; "N
five-card hands" wants 2–4s; Collection (hold a given set of cards over the
run) wants those cards abundant and is the first goal that would make
Insert and Duplicate worth buying; Eradication wants targeted removal;
Survival wants low variance. If these split into a few families (high deck,
low deck, specific cards, variance), a protocol places the player in a
family, J-54's camps make a segment head- or tailwind, and a firmware can
move the player between families. If every goal wants the same deck, there
is no build and the axis is dead.

**The criterion is strategy diversity, not difficulty.** The evidence so
far fails it: every Round 1–3 screen carried the flag "one-op plan: Purge";
in the first cell under the Score goal one operation wins every context.
The lab measures, per context (goal × rule × sub-mode) and in aggregate:

| Metric | What it measures | Pass line (first draft) |
|---|---|---|
| Operation dominance | each operation's share of the best plan's budget across contexts | no operation above half the budget in more than half the contexts |
| Plan overlap across contexts | step overlap between best plans of different goals / rules | below 30 % between goals of different families |
| Near-optimal set within a context | number of *distinct* plans within 2 pp of the best | two or more in at least half the contexts |
| Character of near-optimal plans | do they differ in variance, in when they pay off, in robustness to the next rule? | plans equal in mean but different in character are a choice; equal in both are the same solution |
| Ban test | loss of the best plan when the most-used operation is forbidden | a small loss means real alternatives exist |
| Synergy | value of two operations together above either alone | at least a few positive pairs, otherwise the kit is a ranking, not a build |

Consequences for the display: the heat map shows *direction* (which cards
help whom), never the plan; mean, variance and robustness are the player's
to weigh. Levers if dominance persists, least intrusive first: goals that
make other operations worth buying; sub-modes that make position operations
live; prices that rise with use; per-run caps on an operation.

**Working rule (owner, 2026-10-16): the rules are not fixed; expand
vertically where the measurements say so.** For each context the screen
gives a verdict, and the response follows from it: a context that already
has several good plans gets nothing added; a context with one dominant plan
gets a mechanism whose only job is to raise the payoff of the alternatives
the player is not choosing (a goal that values them, a perturbation that
turns them on, a price or cap on the dominant one), and the same screen is
rerun to confirm the alternative is now taken. Nothing is added to a context
that passes.

**Round 8's reading of the first cell (2026-10-16; section 10 has the
numbers): the goal axis works, the operation axis does not.** Goals do
create different deck directions, four families by removal direction: {Score,
Survival} (cut 5s and 4s), {Capture} (cut tens), {J-54 busts} (cut aces and
7s), {Collection} (cut tens, keep the collected rank); plans of different
families overlap 0.19. Score's build is *which cards* to cut, and it is the
rule that decides it (plans under different rules overlap 0.19), so in this
cell the rule pool, not the menu, carries the diversity. The menu has one
verb: removal takes 86 % of all budget, and Purge is only Cut at another
price (4 of a rank for 2 = two Cuts of 2 for 1), so "ban Purge, lose nothing"
is an alias, not an alternative. Real two-plan contexts are 20 % of all
(mostly Score on the standard deck), and where they exist they do differ in
variance or robustness (15 of 18). Insertion lives only through a goal about
a card (Collection: Duplicate in every plan) or on a thinned deck (Score
mid-run 78 %); Inject and Refine cannot act on a full deck at cap 2 by
construction. Capture is degenerate (it ignores J-54; one plan per deck, a
deck-size score). Survival is Score's twin (cosine 0.86).

The per-context list that follows from the working rule:

| Context | Verdict | Action |
|---|---|---|
| Score: which cards to cut | several good plans, rule-driven | add nothing |
| Removal as the only verb | one dominant plan | make Cut and Purge two verbs: Purge cheap but coarse (its rank drawn from the hottest few, or named by J-54), Cut precise and dear |
| Inject and Refine on a full deck | dead by construction | give insertion room under the cap (Inject 1 card up to a third copy, or a per-run allowance of extra copies), Refine likewise |
| Capture | degenerate | make it depend on J-54: the Joker counts only if the hand is not lost, or J-54 drawing it costs the player |
| Survival | duplicates Score | drop it, or redefine as a variance goal (pushes) and test for a direction of its own |
| J-54 busts | own direction, one solution per context | add nothing; its value is as a secondary goal pulling against Score |
| Collection | one solution, but it wakes Duplicate | add nothing alone; test it as a **secondary goal** beside Score (Score keeps tens and cuts 5s, Collection cuts tens and keeps 7s) for a real trade-off |

Round 9 reran the Round 8 screen with these changes (light, exact
evaluation only). **Result (2026-10-16): one of five mechanisms worked.**

| Context | After Round 9 | Evidence |
|---|---|---|
| Score: which cards to cut | unchanged by design; improved as a side effect | merged near-optimal 28 → 33 % (44 % with every fix; standard deck 78 %); between-rule overlap 0.19 → 0.07 |
| Removal as the only verb | **fixed** by a cheap, coarse Purge ("Hot Purge": 4 of a rank for 1 budget, the rank drawn from the three hottest ranks of the current map) | Hot Purge above half the budget in 49 % of contexts (77 % before); Cut and Hot Purge both appear in 87 % / 96 %; banning the most-used verb costs 2.1 points (7.0); Cut + Hot Purge has positive synergy under every goal. The new choice reads "precision or volume": cut the exact aces and 7s, or take four cheap coarse purges. A cheap Purge whose rank J-54 names (the rank that hurts J-54 least) **fails**: the player declines it. |
| Inject and Refine on a full deck | improved for Refine, unchanged for Inject | an allowance of 4 extra copies lets Refine enter 56 % / 33 % of Survival's / Score's standard-deck contexts; Inject of a card the deck already holds *is* Duplicate and stays mid-run only; both allowances push "stands on 15"'s ideal deck to 97.7 % (degenerate), so insertion room has to come from cards the deck does not hold |
| Capture | improved, not fixed | "the Joker counts only if the hand is not lost" makes the score rule-dependent (2.6–3.5 % by rule) and rotates its direction by up to ~25°; between-rule overlap 1.00 → 0.78 (0.58 with every fix), still one standard-deck plan |
| Survival | **dropped**; Push (probability of a push) is a new direction but degenerate (16 ten-cards push every hand) and is dropped too | pass lines unchanged without Survival |
| J-54 busts as a secondary goal | improved with Hot Purge | Score + J-54 busts: 6 % → 33 % merged near-optimal, every set a choice |
| Collection as a secondary goal | unchanged | Score + Collection is Score's plan plus cheap Duplicate 7s (0 → 11 %); Collection alone keeps one plan everywhere |

With every surviving fix together the first cell passes 5 of the 7 lines
(3 before): dominance 40 %, synergy 3 pairs, insertion, overlap and choice
pass; near-optimal 32 % (standard deck 52 %, mid-run 13 %) and ban 3.9 fail.
The remaining gap is the **thinned deck**: a 16–21-card deck leaves few
cards to choose between, whatever the menu. That is the sub-mode question
(Round 10): the counting and ordered cells give a thin deck other things to
do (what is left in the shoe, where the cards sit) than be cut further.

Model caveats of Rounds 8–9: single hands, not runs; the Hot Purge is scored
on the expected deck (realised outcomes beat the plan without it in 98 % of
standard-deck contexts but 41 % of mid-run ones); beam misses up to 7.9
points; an exact map, not a human.

**Phase from 2026-10-17: add mechanisms where strategy is thin ("水多加面").**
The owner's call after Round 9: the shape is right and does not change; from
here each measured gap gets one mechanism, with one metric and one pass line
set before testing, at most two forms tried, and a mechanism that fails is
removed, not tuned. The first batch (Round 10) and the gap each item answers:

| Gap (evidence) | Mechanism | Metric |
|---|---|---|
| The thinned deck has nothing left to choose (near-optimal 13 % mid-run) and Capture is degenerate as a goal | **Two phases**, back from v1: the Joker is sealed; the player pays to release it and the run turns into a Capture finish; a thinner deck makes release more attractive, so the decision is *when* to switch | the best release round differs between schedules; releasing early or late costs win rate |
| Insertion is Duplicate by another name | insertion only of cards the deck does not hold: a **sample card** with a value per side (e.g. 10 for the player, 2 for J-54), few and dear | appears in standard-deck plans; ideal deck stays below 90 % |
| Collection has one plan | the collected rank is **re-designated by J-54** at rule switches, or Collection becomes a bounty beside Score | between-rule plan overlap falls from 0.91 |
| Two clean firmwares only | a sweep of the player-side rule family (a rank counts 11, 2–4 count 10, the player busts above 22, symmetric bonuses) | new direction, non-degenerate (Round 5's screen) |
| Reading J-54's program is worth up to 20 pp but is free or absent | **purchasable information** ("decompile": the next two conditions, for budget) competing with removal for the same budget | the best policy sometimes buys information instead of cards; win-rate difference buy vs never |
| One price for precision vs volume | Hot Purge's price, size and number of candidate ranks, two steps each | both verbs stay above a third of contexts |
| Idle's luck under strong rules | **schedule balancing**: mean EV of the run near zero, no rule more than two segments, classic opening | idle's first-passage win rate under 5 %, shapers 40–70 % |

Sub-modes (section 2a) are set aside until this batch shows whether the
thinned deck is still empty.

**Round 10 result (2026-10-17): four kept, four dropped.** Chips in the run
model are now exact (a dynamic programme over the chip count), about 2 pp
below the sampled numbers of Round 7.

| Mechanism | Result | Keep / drop |
|---|---|---|
| Two phases: Joker release (4 or 6 budget) | Passes its lines (best release rule differs by schedule, mistiming costs 5–6 pp, never releasing is worst: 42 → 71 %), but the oracle release is round 2–4 in 84 % of schedules, "release as soon as affordable" is within 1–2 pp of the best, and **capture is a luck route: idle goes from 8 to 42 %**, 87 % of it by capture (3.7–6 % per hand, no shaped deck needed) | **keep the structure, change the numbers**: capture counts only from round 9 (like chips) or only for a Joker drawn as a third card or later; new pass line idle under 15 % |
| Purchasable information ("decompile" the next two conditions for 2 or 3 budget) | A heat-map reader gains nothing (never / always / choose 44.0 / 43.9 / 44.2 %); only the beam optimiser gains (+3 to +4 pp, buying 0.6 times a run); at 3 budget every buyer loses | **drop** |
| Sample card (10 for the player, 2 or 0 for J-54; 2 budget, at most 3) | Enters 22 % of Score's standard-deck contexts as a late alternative step, nowhere else; sits in Score's ideal deck but never earns its price within budget 6 (removing J-54's good cards is cheaper than adding a ten J-54 reads low) | **drop** both forms |
| Schedule balancing (EV band, two segments max, classic opening) | The EV band is the only constraint that moves idle, and it moves the shapers as much (idle −4.5 pp, strip-all −7.1): 1.75× idle 3.3 % / shapers 36 %, 1.5× 9.9 % / 48 %; a quarter of random schedules are balanced as generated | **drop as a mechanism**; keep the EV band and re-test at an in-between target (1.6×) together with the capture rule |
| Collection: J-54 designates the rank it values most under each rule | Between-rule plan overlap 0.74 → 0.43; the plan is still "duplicate that rank, purge the tens" | **keep** (the bounty form equals Score's own numbers and is dropped) |
| Firmware sweep | Two more clean candidates: **"your 2–4 count 10"** (largest cosine 0.46, ideal 83 %, start bar 51 %) and **"you bust only above 22"** (0.33, 84 %, 49.8 %; the first firmware orthogonal to plain blackjack). With "4–6 count 10" the family has three distinct members (pairwise cosines −0.55 to +0.23). Rank-11 / aces / tens variants and symmetric rules are plain blackjack again | **keep** both |
| Hot Purge pricing | Every setting keeps both verbs; **size 3** raises the merged near-optimal share 38 → 46 % and halves Hot Purge's dominance (46 → 28 %); price 2 gives the most even split; size 6 changes nothing | **keep, size 3** (price 2 as the alternative) |

Lesson of the two routes: what the player buys must depend on the deck they
built. The capture pays idle as much as the shaper (too strong for the gap);
information pays the optimiser, not the reader of the map (too weak). The
next batch re-tests the release with a late-capture rule, the balanced
schedules at 1.6× with it, Hot Purge at size 3 on the dual goals, and prices
for a firmware menu of three.

**What this does to section 0b.** Decision 5 ("tune every rule to neutral")
is withdrawn: strong rules stay, and whether a run is balanced by its
*schedule* (the mean EV over the run near zero) is tested in the build-space
rounds. Decision 1's target moves to 1.5–1.75× for a human player and is
re-set once the goal axis exists. Decision 2's injection becomes a flavour
event (3 cards plus 2 budget, a wash) or is dropped. Decisions 3 and 6 stand.
Decision 4 is re-tested once strong rules are back. The verification roadmap
(section 12) is replaced accordingly: **Round 8 is a light diversity screen
in the first cell (goals × rules × operations, exact evaluation, no run
simulations)**; Round 9 adds the counting and ordered sub-modes as the tool
axis; the whole-configuration run comes after the build space exists.

## 1. Game state

Standard 52-card deck; Jokers are special cards that can be added.

| Variable | Meaning | Example |
|---|---|---|
| `D` | The deck: its cards, and their order when the sub-mode keeps one | 52 cards |
| `N` | Number of cards in `D` | 52 |
| `t` | Draws so far (in the round, or in the run for non-resetting sub-modes) | 12 |
| `S_P`, `S_R` | Hand totals (or run scores, for score goals) of player and J-54 | 20, 25 |
| `A` | J-54's extra advantage (section 5) | 10 |
| `J_P`, `J_R` | Jokers each side has collected | 1, 0 |
| `H_P`, `H_R` | Each side's draw history | A♥, 7♠, … |
| `B` | The player's remaining operation budget | 5 |
| `K_P` | Order information the player holds | top 3 cards |

A card is `c = (s, r, q)`: suit `s`, rank `r`, kind `q` (normal or Joker).
Colour (red / black), parity and face / number are derived from `s` and `r`.

## 2. Group 0: table structure

### 2a. Global sub-mode

| | **Shuffled** | **Unshuffled (order kept)** |
|---|---|---|
| **Replaced** (cards return after each round) | **Distribution**: every round deals from the same composition; only counts matter. v1 is this cell. | **Cycle**: cards return to a fixed place; the deck is a loop the player can learn. Modular arithmetic: the deck size `N` and cards used per round set the phase. |
| **Not replaced** (cards are used up until the deck runs out) | **Counting**: the remaining composition drifts; seen cards are information. | **Ordering**: a fixed sequence consumed card by card; a puzzle. Hitting takes a card away from the dealer. |

Joker roles that suit each cell (candidates, not decisions): wild card
(distribution), reshuffle trigger (counting), position marker (cycle), hand
swap (ordering).

The win-rate bar (see `J54_TABLE.md`) fits the shuffled cells. In the
unshuffled cells outcomes are close to deterministic, so the bar should show
something else (predicted results of the next hands, steps to the goal).

### 2b. Draw policies

The dealer's algorithm is a primitive; the player is free but may be capped.

| Side | Policy | Parameters |
|---|---|---|
| J-54 | Draw to a threshold (default: 17) | `threshold`, soft-17 behaviour |
| J-54 | Fixed number of cards | `k` |
| J-54 | Stop on a card condition | `filter` |
| J-54 | Draw method: from top / bottom / every second card / two and keep the better | `method` |
| J-54 | Draw source: the deck, or the removed pile | `source` |
| Player | Free (hit / stand / double / surrender) | — |
| Player | Card cap per round | `max_cards` |

A draw method that only changes *position* (top vs bottom) does nothing in a
shuffled sub-mode; it only matters in the unshuffled cells. In shuffled cells
use methods that change *what* is taken (keep the better of two) or *where
from* (the removed pile).

## 3. Group 1: deck operations (player items, also usable by J-54)

Define the operation type, not a hard-coded item.

| # | Operation | Parameters | Example | v1 `deck_ops` |
|---|---|---|---|---|
| 1 | **Insert** | `card, k, position` | add 2 Jokers; add 5 red cards | `add` (no position yet) |
| 2 | **Remove** | `filter, k, selection` | remove 3 random black cards; remove every rank below 4 | `remove` (rank filters only) |
| 3 | **Duplicate** | `target, k` | copy the Joker 3 times | `copy` |
| 4 | **Transform** | `source, destination, k` | turn 4 clubs into hearts (count unchanged) | — |
| 5 | **Swap** | `i, j` | swap the 3rd and 8th card | — |
| 6 | **Reorder** | `range, method` | reverse the top 5; shuffle the top 10 | — |
| 7 | **Relocate** | `target, position` | move the Joker to the top | `move_top`, `move_bottom` |
| 8 | **Inspect** | `range, detail` | see the next 3 cards; see how many Jokers are left | (the always-on deck view, `peek`) |

Filters needed beyond v1's rank selectors: `suit:<s>`, `color:red|black`,
`parity:odd|even`, `face`, `number`, rank ranges, `joker`.

**Every operation also carries four limits:**

| Limit | Meaning |
|---|---|
| Cost | Budget or chips |
| Scope | Which cards or positions it can reach |
| Target visibility | Does the player see what they pick (copy *the Joker*) or not (copy *a random unknown card*)? |
| Timing | When it can be used (betting, own turn, between rounds), and when it takes effect (now, on a trigger) |

The same operation with different limits has a very different value: "copy
the Joker" and "copy a random unknown card" are both Duplicate.

**Inspect is the multiplier of position operations.** In a deck whose order
the player does not know, swapping two unknown cards has an expected value of
zero. Swap, Reorder and Relocate are only worth something together with
Inspect, so Inspect stays a basic primitive, priced and range-limited, rather
than an optional module.

Operations by sub-mode:

| Operation | Shuffled cells | Unshuffled cells |
|---|---|---|
| Insert, Remove, Duplicate, Transform | change the composition | change composition and positions |
| Swap, Reorder, Relocate | only between the shuffle and the deal, and only with Inspect | the main tools |
| Inspect | counts | order |

## 4. Group 2: effect rules (where the asymmetry lives)

Two value functions, one per side:

```
f_P(c, θ_P)      f_R(c, θ_R)
```

The player and J-54 can draw the same card and get different results. Every
rule below is one primitive with parameters, applied to either side; there
are not two sets of logic.

**Stateless** (depend only on the card; first batch):

| Rule | Parameters | Example |
|---|---|---|
| Flat bonus by filter | `filter, a` | J-54's black cards +1 |
| Suit weight | `w_s` | hearts ×2, spades ×−1 |
| Rank function | `g(r)` | J-54 scores `r²/10` (rounded) |
| Threshold bonus | `k, b` | rank ≥ 10 gives +5 |
| Parity preference | `w_even, w_odd` | player likes even, J-54 odd |
| Joker trigger | `j, e` | a Joker ends the hand, or adds points |

**Stateful** (depend on draw history; later):

| Rule | Parameters | Example |
|---|---|---|
| Streak bonus | `m, λ` | consecutive same-suit draws grow the bonus |
| Running multiplier | `α` | each ace multiplies later gains |
| Diminishing returns | `β` | each repeat of a kind is worth less |
| Periodic bonus | `p, b` | every `p`-th draw +`b` |
| Risk penalty | `h, L` | total above `h` costs `L` |
| Set bonus | `C, b` | all four suits in a hand +`b` |

Why stateless first: the win-rate bar stays exactly computable, and the
player can reason about the direction by hand. Stateful rules multiply the
state space and hide the direction.

**Integers only.** Totals are compared against 21 and other borders, so every
rule must give integers (`r²/10` and multipliers need a stated rounding).

**The sign of a bonus depends on the dealer's algorithm.** "J-54's black cards
+1" makes a 2-card dealer stronger but a draw-to-17 dealer bust more often.
That is intended: it is J-54's "calculation" theme, and the bar resolves it
for the player.

## 5. Group 3: J-54's advantage

J-54 does not learn, but its advantage can still move:

```
A_{t+1} = F(A_t, c_t, t; θ_R)
```

| Formula | Definition | Character |
|---|---|---|
| Fixed | `A_t = A_0` | unequal start |
| Linear | `A_{t+1} = A_t + a` | steady growth |
| Proportional | `A_{t+1} = λ·A_t` | exponential growth or decay |
| Conditional | `A_{t+1} = A_t + a·1[c_t ∈ C]` | follows the deck's make-up |
| Streak | `A_{t+1} = A_t + a·k_t` | grows with the current hit streak `k_t` |
| Saturating | `A_{t+1} = min(M, A_t + a)` | capped |

**Conditional is the one to keep**: e.g. J-54 gains +3 per black card it draws,
and the player slows that growth by removing black cards. It ties the
advantage directly to deck shaping.

Open: where `A` applies in a blackjack hand. Proposal: added to J-54's total
**at comparison only**, so its draw algorithm stays unchanged; or spent as a
run-level score for score goals.

## 6. Group 4: goals

The same operations and rules with another goal make a different problem.

| Goal | Win when |
|---|---|
| Score | final score above J-54's |
| Capture | the player draws a Joker first |
| Survival | still alive at round N |
| Exact | score exactly `T` |
| Collection | a given set of cards collected |
| Resource | done at minimum operation cost |
| Probability | the win rate (the bar) above `p` |
| Time | done in the fewest rounds |

v1's protocols map onto these: Single Capture = Capture, Capital = Score
(chips).

## 7. Composing a problem

A problem is one choice from each group:

```
problem = (sub-mode, draw policies, operations + limits + budget,
           f_P, f_R, A, goal)
```

What makes a combination a good problem:

1. **Relevance**: every chosen primitive changes the outcome. A primitive
   that cannot affect the goal is removed or the goal is changed.
2. **No degenerate solution**: the best deck is not one trivial shape (e.g.
   "keep only 5–7"), and the best plan is not "spend everything on one
   operation".
3. **A clear direction**: the player can tell which way to shape the deck,
   and different rule sets point in noticeably different directions.
4. **Reachable**: the goal can be met within the budget with good play, and
   not without effort.
5. **Legible**: the rules can be explained in a line each.

## 8. Worked example: Joker race (degenerate as written)

| Part | Choice |
|---|---|
| Sub-mode | shuffled, not replaced |
| J-54 policy | draws 1 card per turn |
| J-54 advantage | +2 at start, +1 per red card |
| Goal | the player draws a Joker first |
| Operations | add a Joker (cost 2); remove 5 normal cards (cost 3); swap the top two (cost 1) |

Assume the sides alternate single draws, the player first, one Joker at a
random position.

- **The advantage does nothing**: the goal is capture, so scores never matter
  (fails relevance).
- The player draws first with probability ⌈N/2⌉ / N: 50 % at 52 cards, 51.1 %
  at 47. Removing 5 cards for 3 budget buys 1.1 %.
- Swapping the top two unknown cards has an expected value of 0.

Two one-part fixes make it a real problem:

- **Add Inspect** (cost 1: see the top 2). The swap becomes valuable; the
  problem becomes "buy information, then reorder".
- **Price drawing** (each draw adds `f_P` to the hand; over 21 is out). The
  race now trades Joker odds against bust risk, and the advantage matters
  if the goal becomes "capture or outscore".

## 9. Problem validator (next tool)

An offline tool (prototype outside the game, later in `black-jack-sim/`):

- input: one problem (section 7);
- output: the win-rate bar (exact for 2–3-card hands and stateless rules,
  Monte Carlo otherwise), the best use of the budget, each primitive's effect
  on the result (relevance), and a degenerate-solution check.

It mines good problems from the combinations; the first batch of levels, and
which primitives the game implements first, follow from what it finds.

## 10. Earlier findings

Exact numbers from the discussion (2026-10-15), with a model where J-54 takes
exactly 2 cards and the player 2 cards plus an optimal third, both from the
same deck, ties not counted as wins, deletions only:

| Deck | Player win rate |
|---|---|
| Standard 52 | 65.5 % |
| Standard + 24 cards of 2–5 | 68.8 % |
| Only 2–7 (24 cards) | 84.0 % |
| Only 6s or only 7s (12 cards) | 100 % |
| No 2–6 (32 cards) | 44.4 % |
| Only 10s and aces (20 cards) | 38.9 % |

Lessons:

- A 2-card dealer flips the usual direction: low cards hurt the dealer, so
  J-54's entropy (adding low cards) would help the player.
- "Keep only mid cards" wins outright, because a fixed 2-card dealer against a
  player who may take a third card is a large structural edge. Changing only
  the dealer's draw *position* does not fix it; changing *what* the dealer
  gets (removed pile, keep the better of two), capping the deck's make-up, or
  using the real draw-to-17 dealer does.
- Replacement barely matters while the deck resets every round (65.2 % vs
  65.3 %); shuffled vs unshuffled is the strong lever (a standard deck drops
  to 12.4 % when J-54 takes the two highest cards).
- Compute the bar exactly; a 100-hand simulation is ±4–5 %, which makes a
  90 % target flicker.

Screening in the rule lab (`j54-lab/`, a separate git-ignored repo; details
in its `FINDINGS.md`), single rules and two-rule pairs on J-54's side,
J-54 drawing to 17, shuffled + replaced:

- **A cap per rank+colour is a core constraint.** Extra copies let almost
  every rule reach a one-shape solution near 100 %; at the standard 2 per
  rank+colour most rules stop being degenerate. The cap value itself decides
  it (cap 3 brings several back).
- **Rules mostly add up.** Pairs behave close to the sum of their rules
  (within ±4 pp for 11 of 15), so players can reason rule by rule.
- **Most rules keep the plain-blackjack direction** (cut low, add tens).
  New directions come from rules that change what J-54's high cards are worth
  (faces count 5, hearts ×2) or that make low cards worthless. Tension (rules
  pulling the deck opposite ways) needs more of the second kind.
- **Zero values need a draw limit.** "Low cards count 0" lets a deck of low
  cards keep J-54 drawing up to the hand cap; the limit must be a stated rule
  and priced as an exploit.
- **Removal beats insertion** at equal price; insertion needs its own value
  (Jokers, cards J-54 values badly). Colour rules push the ideal deck to one
  colour, so colour operations need a small `k` or a high price.
- **A budget of 6 moves the bar 5–10 pp.** High targets (90 %) are only
  reachable over many rounds of operations, not within one budget.
- **J-54's rules fall into two camps.** Most rules keep the plain direction
  (the "classic" camp); "J-54 stands on 15" and "J-54's low cards +3" point
  against it. Shaping for one camp hurts under the other (regret up to 15 pp)
  and 2 extra budget buys back only 1–5 pp, while switches inside a camp are
  almost free. So the rule pool needs both camps, and how far ahead J-54
  announces a switch is the main difficulty lever. "7–9 count 10" and
  "stands on 19" are orthogonal; zero-value rules stay degenerate even with a
  draw limit; some rules ("aces hard 1") change nothing at budget scale.
- **Over a 12-round run, shaping is worth ~10 pp** (never spending vs
  spending for the current rule), and the best strategy depends on J-54's
  schedule: spend for the current rule when it stays or rotates within a camp,
  look ahead or save when it crosses camps (up to +6 pp). Choices only matter
  when J-54 crosses camps or plays orthogonal rules; warning 1–2 rounds ahead
  is enough (more adds nothing); banking budget (with a cap) is part of the
  strategy; entropy of 1 low card per round is a ~3 pp tax.

Round 5 (2026-10-16; chips, insertion, legibility; one sampled hand per
round from the shaped deck, EV-optimal play, 100 starting chips, 2000 seeds
per cell). The decisions it led to are in section 0b.

- **Chip goals separate shaping from idling.** Best policy − idle on "final
  chips ≥ 1.5×": +19 pp (12 rounds, flat bets of 10) to +50 pp (16 rounds,
  bets a Kelly fraction of the bankroll from the exact EV). The reason is EV,
  not win rate: shaped decks under the P0 rules have a median EV of +0.24
  bets per hand, so 12 hands separate shaped from idle runs by 1–3.5 bets
  against a standard deviation of 3.3. "≥ 2.5×" is unreachable with flat bets
  and needs proportional ones; then idle reaches it 0–3 % of the time (13–17 %
  when J-54 keeps one generous rule all run) and shapers 21–81 %. Longer runs
  widen the gap (12 → 16 rounds: +8 to +14 pp). Bankruptcy stays ≤ 1.3 %.
- **A bar read at the last round is not a goal.** With a deterministic deck
  path it is 0 or 100 % per schedule and flips with the schedule's phase
  (16-round runs end one round after a switch and lose it for everyone in
  two schedules).
- **Amplifying rules does not help.** Doubling parameters raises the per-card
  direction only ×1.2; three of eight doubled rules (and two half steps)
  degenerate at cap 2; "low +6" is a different rule from "low +3" (cosine
  −0.01, 14 sign flips); the chip-goal gap is unchanged or smaller because
  idle gains as much as the shapers.
- **Insertion stays dead.** 0 insertion steps in 43 screens. On a full deck
  at cap 2 insertion is illegal by construction (every group is at the cap),
  so only the mid-run test (28 cards after 12 budget of removals) counts: there
  Inject and Refine still never enter, Insert Joker enters 4 of 29 plans with
  a price ceiling of 2–3. A Joker is worth +0.49 / +0.46 pp (first / second)
  on 52 cards, +0.80 / +0.68 on 28, against +1–4 pp for the same 2 budget
  spent on removal. Jokers hurt under "hearts ×2" (J-54 counting 0 spoils a
  bust deck) and lift "stands on 15" towards degeneracy (89 → 92 %).
- **Player-side rules mostly echo plain blackjack.** "7s / 9s count 10", "red
  +1", "even +1" point the classic way (cosine 0.77–0.94). "Faces count 5" on
  the player's side *raises* the bar (+3.8 pp: the player can hit freely).
  **"Player's 4–6 count 10"** is the one new direction (largest |cosine| 0.30),
  non-degenerate at cap 2 (ideal 68 %), start bar 52.5 %. Player × J-54 pairs
  add up (13 of 18 within ±1 pp).
- **Cap 3 is safe for budget plans and unsafe long-run**: plans unchanged,
  ideals +4 to +26 pp and 9 → 5.6–7.5 effective groups; two unrelated player
  rules converge on the same "aces, 2s, 3s" deck.
- **Two sign maps, not eight.** Between two rules 11.8 of 26 rank+colour
  groups flip removal sign on average (8.0 when both must be readable): ~7
  inside a camp (0–1 strict among the classic rules), ~18 across the classic /
  anti line. Clustering by sign reproduces classic vs anti exactly; "stands on
  19" is classic by sign; "faces count 5" is a loner; "stands on 15" and "low
  +3" are two different antis (12 flips apart). The "orthogonal camp" of
  Round 3 was an artefact of the cosine measure (magnitudes), not of signs.
- **The heat map cannot be summed from per-rule colours**: 18–20 % of readable
  groups get the wrong sign, up to 18 of 26 in one pair. Classic pairs add
  cleanly; pairs with the loner or an anti rule do not. Bigger effects keep the
  signs (P1 flips 11.8 vs P0 11.9) with 21 % larger magnitudes.
- **A camp-level announcement keeps most of a one-round warning's value in
  chips** (60–94 % of lookahead-1's gain), lead 2 ≈ lead 1, and **the full
  schedule is worth a lot** (+20–27 pp on the chip goal over greedy in three
  of four cells), which corrects Round 4's "warning beyond 1–2 rounds adds
  little": true for leads of 1–3, not for full knowledge. Proportional bets
  turn a mean-bar gap into a 5–8× larger chip-goal gap.
- Model limits of the round: the deck path is the expected composition (only
  hands are random); i.i.d. evaluation under-reads small decks by ~0.02 bets;
  no double, split or surrender; heuristic bar-optimising spending policies;
  the Kelly bettor is an oracle; Jokers were tested in two deck states only.

Round 6 (2026-10-16; the v2 decisions under a real run: the run ends the
first time chips reach the target, 16 rounds, menu Cut / Purge / Joker). The
verdicts are in section 0b.

- **First passage has no luck problem at 2.5×.** Idle reaches it in 4.9 % of
  runs with Kelly bets on the generous pool (19.6 % of those wins before
  round 8, i.e. 1.0 % of its runs), 2.4 % at 3.0×; only 2.0× (11.3 %, a third
  early) and the one-rule "hearts ×2 all run" schedule (25 %) show v1's
  problem. Flat bets reach no target. **Stopping at the target widens the
  skill gap** (+59.9 vs +50.0 pp at 2.5×): the stop locks in shaped runs that
  would have given chips back. "Counts from round 9" removes every early win
  for 1.2 pp; "hold two round ends" costs 10.4 pp and still leaves early wins.
- **Round 5's multi-round runs did use Inject** (47 steps in 16 of 21 shaped
  16-round runs, re-inserting aces and tens after an anti-camp phase; Refine
  never). "Insertion is dead" was a single-deck result. Dropping Inject moves
  a run's mean bar by −3.5 to +4.1 pp but the 2.5× win rate by only 0.5 pp;
  with the v2 menu two Jokers enter in 16 of 21 shaped runs, mostly after
  round 10.
- **A shared handicap ladder cannot neutralise the pool.** Starting EVs
  before: faces-count-5 −0.127 and +1-per-black-card −0.187 (already harsh),
  hearts ×2 +0.212 and stands-on-19 +0.159 (still positive at "base +2 and
  ties"); stands-on-15 and low +3 are degenerate at cap 2 once Jokers exist
  (92.0 / 90.5 %) and take base +1. Pool mean EV +0.020 → −0.064. On that
  pool idle wins 0.0 %, the best policy 45.3 % at 2.5× and 57.2 % at 2.0×
  (Kelly), and greedy collapses where J-54 crosses camps (0.1 %) while
  lookahead / saving reach ~40 %.
- **"Ties to J-54" is invisible on the bar and the heat map** (0 flips, same
  ideal deck); it only taxes EV by 0.04–0.09 bets. **Base advantage rotates
  the anti rules** (base +2: cosine 0.56 / 0.65) and **breaks stands-on-19 at
  +2**: J-54 totals 21–23, the player wins only on its bust and no firmware
  moves the bar under it.
- **Betting from the meter keeps most of the oracle's gap**: bands 76–90 %,
  capped Kelly 25 % 60–84 %, half Kelly 36–91 %, flat 0–15 %. Bands bet more
  than Kelly on small edges (10 % vs 6 % at a 50–55 % bar), which a 16-round
  run rewards. **A bet cap does not cut luck**: idle's lucky decks have Kelly
  fractions of 13–21 %, under a 25 % cap; caps of 15 % or less touch idle at a
  cost of 31–54 pp to the shapers. Bankruptcy ≤ 0.7 % for every rule; a bar
  ≥ 50 % implies EV ≥ 0, so bands cannot over-bet a losing deck.
- **The firmware is a build, and "4–6 count 10" is far too strong.** Every
  firmware is distinct (25–48 % of moved cards in common with the plain plan;
  over a whole run 78–87 %, i.e. it changes which ranks are kept, not how much
  is cut). "4–6 count 10" lifts the 2.5× win rate from 33.8 to 69.4 % (+63 pp
  in cross-camp, because keeping 4–6 serves both camps); "5s and 6s count 10"
  +14 pp, evened by 80 starting chips (+3 pp after). "5s count 10" and "tens
  count 9" are neutral on average and swing ±25–40 pp by schedule. Firmwares
  gain most under the anti rules and the loner, least under hearts ×2.
- **J-54's injections at 3 cards per switch are a flattener.** Adversarial
  injections (the rank whose addition lowers the bar most) cost idle 1.5 pp of
  bar and no wins, the shapers 3.0–3.2 pp of bar and 24.5 pp of wins (43.7 →
  19.2 %); random ones −17.7 pp of wins for the shapers, nothing for idle.
  "Thematic" injections (the rank the rule favours for J-54, almost always a
  ten) are a gift (+5.8 pp). Injections erase the saver's lead over greedy
  (38.5 / 33.8 % → 17.2 / 17.1 %) and keep shaped decks at 27–30 cards instead
  of 17–18; every shaper still spends its whole 32 budget, so the bottleneck
  is budget, not targets.
- Model limits of the round: deck path still the expected composition (random
  injections modelled as 16 discrete rank sequences); spending policies
  optimise the bar, bets optimise chips, nobody spends for chips or reacts to
  the bankroll; the bands bettor reads the exact bar; the "neutral" pool is
  harsh on average and holds one broken rule; firmware × injection, firmware ×
  tier and the Joker under injections were not run; injection size and timing
  were fixed by the brief.

Round 7 (2026-10-16; the inputs of the v2 configuration: a tuned pool, a
human-feasible shaping policy, random schedules, injection size, double and
surrender, random operations; the run ends the first time chips reach the
target from round 9). Its consequence is section 0c.

- **Neutral EV pulls every rule towards plain blackjack.** Plain blackjack's
  own starting EV is −0.024 (hit/stand). Rules that pass the band [−0.04,
  +0.01] by their own parameter become small perturbations of it (black +1,
  even +1, hearts +1, spades +1, low +1: cosine 0.58–0.97 with plain
  blackjack, a quarter to two thirds of their former magnitude); rules keep
  their identity only by paying "ties go to J-54". The tuned pool P0t (black
  +1 · even +2 & ties · hearts +4 & ties · spades +1 replacing the advantage
  rule · stands on 16 · low +1 · stands on 18 & ties; mean −0.017) has **one
  faint anti rule** (stands on 16 at 36 % of its former magnitude), "low +1"
  as a new loner, and no "faces count 5" (no neutral value). Strict sign
  flips between any two P0t rules: 0–3.
- **A heat-map reader keeps 66–73 % of the beam gap** ("spend the bank each
  round on the hottest cell": 73 % at 2.0× with bands betting, 66 % at 2.5×,
  63–69 % on random schedules, 76 % of the mean bar); one move a round costs
  3 pp more. **Saving is not a human decision** at income 2 / cap 8 on P0t
  (strip-saver within ±1 pp of strip-all; even beam saver-2 loses to greedy at
  every number of switches).
- **On the neutral pool the opening rule drives the run, not the switches.**
  Runs opening on "stands on 16" give the human 56 %, classic openers 24–30 %:
  that rule's map strips the tens and the resulting deck (aces and 2–6) is
  strong under every P0t rule, so "shaping for anti" helps the classic rules
  that follow. With a classic opening the number of switches is a 16 pp dial;
  the information tiers are 1–3 pp apart. **2.0× is too far for a human on
  P0t** (35 %); 1.5× gives 48–54 %, and with a classic opening the tiers land
  at 60 / 47–49 / 39 %.
- **Every injection without a budget bonus flattens** (shapers lose 2.4–6.5×
  idle's bar, and all of the lost wins): 1 card per switch −6.5 / −9.4 pp of
  wins, 3 cards twice a run −5.3 / −6.9, a random card −3.9 / −5.2, 3 per
  switch −16.5. **3 per switch with +2 budget** is the only non-flattener
  (shapers −0.8 to +2.2 pp, idle −0.7 to −1.1 pp of bar): Purge of 4 costs 2,
  so the bonus exactly undoes the injection; it is a flavour event.
- **Double and surrender** raise every starting EV by 0.008–0.023 (pool
  −0.017 → 0.000, two rules leave the band) and **widen the gap** (shaped
  decks gain 2.5–3.4× idle's EV; +2.7 / +4.3 pp of wins with bands); the
  bands bettor needs no change. **Random operations** (real random entropy
  per seed) add a bar spread of 3.1–3.5 pp by round 16 and +5 pp of wins for
  the human policy over the expected path.
- Model limits of the round: the human is a heuristic reading an exact map;
  100 schedules per switch count; the opening effect rests on one anti rule;
  double / surrender / random operations were not run with the tiers; the
  firmware was not re-run on P0t.

Round 8 (2026-10-16; a light screen of the first cell: 5 goals × 9 rules ×
2 decks, exact evaluation, budget 6, menu Cut / Purge / Inject / Duplicate /
Insert Joker / Refine; reading in section 0c).

- **Removal is the only verb**: Cut + Purge take more than half the budget in
  89 % of contexts (100 % on the standard deck), 86 % of all budget; Purge is
  Cut at another price (banning it costs 0.00, banning both a median 6.99
  points). Inject and Refine enter no plan on a full deck (every group is at
  the cap); Refine enters no plan anywhere.
- **Goals form four families by removal direction**: {Score, Survival}
  (+0.86), {Capture}, {J-54 busts}, {Collection}; cross-family plan overlap
  0.19. J-54 busts most when its aces and 7s go (+0.85 / +0.23 per card),
  not its tens. Rules move the plan for Score (overlap between rules 0.19),
  J-54 busts (0.34) and Survival (0.35), not for Collection (0.91) or Capture
  (1.00).
- **Real two-plan contexts are 20 %** once aliases (Purge = two Cuts,
  interchangeable ten-ranks) are merged; 15 of those 18 differ in variance or
  carry-over (e.g. "faces count 5": cut the lows 5, 4, 6 or the faces J, K, Q;
  +6.6 / +5.4 points, carry-over +0.9 / −2.0). Only 8 % of near-optimal sets
  mix operations.
- **Insertion lives only through Collection** (Duplicate 7s in 18 of 18
  contexts) **and on the thinned deck** (Score 78 %, J-54 busts 67 % of
  mid-run contexts; 11 % / 0 % on the standard deck). Insert Joker is in
  three best plans, all Score mid-run. Synergy exists only for Collection's
  removal + Duplicate (+5.0 / +7.1) and a trace for Duplicate + Insert Joker.
- **Capture is rule-blind** (its policy ignores J-54; one plan per deck, 4.85
  → 8.0 % on 52 cards, mostly 1 / deck size). **Survival is Score's twin.**
- Pass lines as drafted: Dominance fail (Purge > half in 77 %), Synergy fail
  (two pairs), the other five pass but Near-optimal and Ban pass only through
  the Purge alias.
- Model limits: single hands, not runs; two decks; beam misses up to 1.8
  points; Capture's second Joker counted as non-target; J-54 busts computed
  as if J-54 always plays out; the step-overlap measure counts relabellings.

Round 9 (2026-10-16; the Round 8 screen rerun with one mechanism at a time,
then all together; the alias-free reading is primary from here). Summary
table in section 0c.

- **A cheap coarse removal is the one mechanism that changed the plans.**
  Hot Purge (4 of a rank for 1, rank drawn from the hottest three) above half
  the budget in 49 % of contexts; Cut in 87 %, Hot Purge in 96 %; ban 7.0 →
  2.1; synergy in every goal; merged near-optimal 20 → 29 %, J-54 busts 0 →
  50 %. Enumerating its random outcomes: realised gain above the expected
  plan on the standard deck (median +1.8), below it mid-run (−1.0); the plan
  still beats the best plan without it in 98 % / 41 % of contexts.
- **A cheap removal of the rank J-54 names fails** (the least helpful
  positive rank: taken in 20 % of contexts; near-optimal falls to 12 %).
- **Insertion room wakes Refine, not Inject**: Inject 1 of a held card is
  Duplicate; an allowance of 4 extra copies brings Refine into 56 % / 33 % of
  Survival / Score standard contexts but lifts "stands on 15"'s ideal deck to
  97.7 % (92 % even at cap 2 once Jokers exist).
- **Capture tied to not losing becomes rule-dependent but keeps its plan**:
  2.6–3.5 % by rule, lowest direction cosine between rules 0.90, between-rule
  overlap 0.78 (0.58 with every fix).
- **Dual goals are compromises**: Score + Collection is Score's plan plus
  Duplicate 7s (0 % near-optimal); Score + J-54 busts is the union of two
  agreeing plans (6 %), 33 % once Hot Purge exists.
- **Survival dropped without effect on the lines; Push degenerate** (16
  ten-cards push every hand under 4 of 9 rules).
- **Everything together: 5 of 7 merged lines** (dominance 40 %, synergy 3,
  overlap 0.26, choice 57 %, insertion 100 %; near-optimal 32 % with standard
  52 % / mid-run 13 %; ban 3.9).
- Model limits: Hot Purge scored on the expected deck with the plan fixed;
  beam width 12 misses up to 7.9 points with Hot Purge; two decks; single
  hands; Hot Purge's price, size and rank count not varied.

Round 10 (2026-10-17; the first "add a mechanism" batch; expected deck
path with exact chips by dynamic programme, strip-all as the reference
player, bands betting, first passage from round 9 at 1.75×; light screens on
the Round 9 machinery). Summary table in section 0c.

- **The Joker release is a decision, but a thin one, and the capture is a
  luck route**: best release rule differs by schedule (switch rule best in
  69 / 51 % at 4 / 6 budget), mistiming one segment costs 5.2 / 5.8 pp, never
  releasing is worst (42.3 vs 71.1 %); yet the oracle release is round 2–4 in
  84 % of schedules, one rule for all is within 1.3 / 1.9 pp, captures are
  60–65 % of wins and **idle rises from 8.0 to 41.5 %** (87 % by capture).
  The hitting policy after release changes nothing (the Joker is a soft ace;
  EV-optimal play already draws it).
- **Information bought with budget pays the optimiser, not the map reader**:
  strip-all 44.0 / 43.9 / 44.2 % never / always / choose at 2 budget; beam
  greedy +4.1 / +2.7 pp buying 0.6 times a run; at 3 budget every buyer loses.
- **The EV band flattens**: it takes 4.5 pp from idle and 7.1 from the shapers
  (all constraints: 1.75× idle 3.3 % / strip-all 36.2 %; 1.5× 9.9 / 47.8 %);
  "two segments max" changes 6 % of segments and nothing else; the classic
  opening helps at k = 1 (+5.6) and hurts at k = 3 (−4.2).
- **A held-out card is not wanted**: the Sample (10 / 2) enters 22 % of
  Score's standard-deck contexts as a late step, (10 / 0) none; removing
  J-54's good cards is cheaper than adding a ten J-54 reads low.
- **Collection by J-54's designated rank**: overlap 0.74 → 0.43, plan
  unchanged in kind (duplicate the rank, purge tens); the bounty form equals
  Score (44 % near-optimal, 88 % choices) and changes no plan.
- **Three clean firmwares**: "4–6 count 10" (0.30), "2–4 count 10" (0.46,
  ideal 83 %, start bar 51.0 %), "bust only above 22" (0.33, 84 %, 49.8 %,
  cosine −0.01 with plain blackjack); pairwise −0.55 to +0.23. Rank-11, aces,
  tens and symmetric candidates are plain blackjack (0.67–0.95).
- **Hot Purge size 3** beats size 4: merged near-optimal 38 → 46 % on the
  single goals, dominance 46 → 28 %; price 2 gives the evenest split (29 % /
  22 %) and most choices (70 %); size 6 changes nothing; five candidate ranks
  tie size 3 on sets, lose on choices.
- Model limits: exact chips on the expected path read ~2 pp low; 25 schedules
  per k for the run experiments, beam players on the named seven only; the
  reference player keeps reading the bar after a release (no capture-minded
  shaping); the information test is myopic; Hot Purge pricing on single goals
  without bans; 1.6× untested.

## 11. Open questions

Settled on 2026-10-16 (section 0b): the goal (a chip target, first passage,
counted from round 9), the sub-mode (shuffled + replaced), the budget (a
separate compute budget), where `A` applies (dropped), how rules are
announced (camp at each switch; the whole schedule as the easy tier), the
betting meter (bands, no extra cap), the firmware (adopted with a price).
Still open, in the order section 12 verifies them:

- **A human-feasible shaping policy**: how much of the skill gap a player who
  reads the heat map and makes one or two obvious moves a round keeps. Every
  gap so far is between beam-search optimisers.
- **Random schedules**: the win-rate distribution by number of classic ↔ anti
  switches, to set the difficulty dials.
- **The tuned pool**: each rule's own parameter brought into the neutral band,
  with its direction intact and the Joker's degeneracy on the anti rules fixed;
  a replacement for "+1 advantage per black card".
- **Injection size**: 1 card per switch, 3 cards twice a run, or 3 per switch
  with a budget bonus; where flattening stops and the saver's lead survives.
- **Double and surrender**, which the game has and the lab does not: their
  effect on starting EVs, the bands and the target.
- **Budget economy sensitivity**: income 1–3, bank cap, a bonus on wins,
  minimum deck 12 vs 16 (every shaper so far spends everything and cuts to
  the floor, so "how much to cut" is not a decision; "which and when" are).
- A weakened "4–6" firmware and more clean candidates; firmware × tier and
  × injections.
- The default J-54 algorithm: draw to 17 (bar matches real play, targets lower
  than 90 %) or a fixed 2 cards (needs a cap on the deck's make-up)?
- How many Chaos rules are active at once (one, as in every lab run, or up to
  two persistent ones as at Poker Head's table), and whether the switch
  period (3 rounds in the lab) should be fixed or part of the schedule.
- What the bar shows in the unshuffled sub-modes.

## 12. Verification roadmap before building v2

Three kinds of question remain, and only the first kind belongs in the lab.

**Lab, before any code in the game.** Round 7 is done (section 10); the
plan after it follows section 0c: light screens first, run simulations only
once a build space exists.

| Round | Question | Why it gates building |
|---|---|---|
| 8 (light, done) | Strategy diversity in the first cell: goals × rules × operations, exact evaluation only | Done: the goal axis works, the operation axis does not (section 0c) |
| 9 (light, done) | The first cell's vertical fixes, one at a time | Done: the cheap coarse Purge works; insertion, Capture and dual goals do not (section 0c); the thinned deck is the remaining gap |
| 10 (done) | The first "add a mechanism" batch | Done: kept the Joker release (numbers to change), Collection by J-54's rank, two firmwares, Hot Purge size 3; dropped information, the Sample card, schedule balancing as a mechanism (section 0c) |
| 11 | The second batch: the release with a late-capture rule (idle under 15 %), balanced schedules at 1.6× with it, Hot Purge size 3 on the dual goals with bans, prices for a firmware menu of three with the reference player | Whether the two-phase structure survives with the luck taken out |
| 12 | The counting sub-mode (shuffled, not replaced) and the ordered sub-modes as the tool axis, if the thinned deck is still empty | The sub-mode is the axis that makes position operations and Inspect worth anything |
| 13 | The whole configuration at once with strong rules, the human policy, bands betting, double / surrender and random operations, by tier; budget economy sensitivity | The go / no-go for implementation; also re-sets the target and the firmware prices |

**Only a playable prototype can answer** (plan a minimal text or GUI
prototype as soon as Round 8 passes; two or three people, ten runs):
whether humans read the two sign maps on the strip; whether "watch the bar,
bet by bands" plays as a game rather than a spreadsheet; whether the firmware
pick at the start means anything when only the tier is known; whether the
camp announcement is understood; whether players discover on their own that
most of J-54's "bonuses" help them; the pace of 16 rounds of shop, bet and
hand.

**At integration time**: the in-game bar / EV per round (the lab's i.i.d.
model under-reads small decks by 1–4 pp; decide whether the meter switches to
an exact without-replacement count below ~30 cards); replay determinism with
random operations (v1's counter-seeded RNG); the agent observation (bar, heat
map, camp announcement, firmware); the simulator adapter.
