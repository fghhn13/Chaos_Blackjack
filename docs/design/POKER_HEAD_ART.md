# Poker Head art specification

Date: 2026-10-13. Status: selections approved by the user and all 41 PNGs exported.

Runtime product IDs come from [the Poker Head catalog](../../chaos_blackjack/poker_head/catalog.py). The [delivery manifest](../../assets/poker_head/manifest.json) records each selected source, variant, author, dimensions and SHA-256 hash. The original candidate review is historical; this specification and the delivery manifest define the adopted selections.

## Visual language

Use flat old-gold (#B7A477) silhouettes on transparent backgrounds. Identify each item through its outer shape and a small number of transparent cutouts. Keep visual detail low enough to recognize the subject at 32 pixels. Avoid gradients, texture, shadows, glow, metallic reflections and decorative borders. Card frames and labels belong to the UI rather than to these transparent assets.

Core, permanent, consumable and financial categories use the same color. Preserve category labels when presenting the icons, particularly the shared card-exchange silhouette for Spare Sleeve and Sleeve Clip. Decorative card suits do not restrict an effect to that suit.

The code-drawn A, 21, +2 and x4 glyphs are deliberate identity marks approved in the selected review. They are geometric vector paths, not rasterized UI text, and do not replace the effect descriptions.

## Selected original studies

| Product ID | Study | Composition | Why this version |
|---|---|---|---|
| ph_borrow | Borrowed Blossom B | A 21 card passes a crown through a one-way arrow to a receiving hand. | Connects the dealer natural to transferred victory; the crown emphasizes the outcome rather than exchanging cards. |
| ph_risk | Risk Sharing B | A disk leaves its upper-right quarter open, with a protection shield beside that quarter. | Shows partial coverage and the remaining exposed stake rather than implying complete immunity. |
| ph_buffer | Grace Approval A | A folded approval sheet carries +2 beneath a ceiling bar and upward arrow. | Connects the permission-slip identity with the temporary ceiling increase. |
| ph_aces | Aces to Top B | Several A cards are lifted above deck layers beside an upward arrow. | Shows plural aces and their destination; differs from the single opening-ace icon. |
| ph_quad | Quadruple Bet Ticket A | A perforated ticket carries x4. | Communicates a prepared betting multiplier and the consumable ticket identity without suggesting a random die roll. |

Original SVGs: `black-jack-assets/source/code-icons/poker-head-v2/`. The reproducible source is [draw_poker_head_icons.py](../../scripts/draw_poker_head_icons.py). The selected paths and glyphs are original; none is copied from the API silhouettes. Unselected A/B studies remain available in the art repository.

## Complete artwork descriptions

| Asset / file | Product | Kind / build | Selected source | Visible subject | Intended reading |
|---|---|---|---|---|---|
| [ph_margin.png](../../assets/poker_head/ph_margin.png) | Room to Breathe | core / multi-card | expand | Four outward arrows | Extra room around the bust ceiling. |
| [ph_retreat.png](../../assets/poker_head/ph_retreat.png) | Graceful Retreat | core / surrender | wallet | Wallet containing notes | Preserving chips when surrendering. |
| [ph_approx.png](../../assets/poker_head/ph_approx.png) | Almost Perfect | core / precision | on-target | Arrow landing on a target | Bringing nearby totals to the target 21. |
| [ph_stakes.png](../../assets/poker_head/ph_stakes.png) | High Stakes | core / double | crown-coin | Crowned coin | Privileged winnings after doubling. |
| [ph_account.png](../../assets/poker_head/ph_account.png) | Private Account | core / finance | bank | Bank facade | Access to investments, borrowing and an extra shop slot. |
| [ph_long_reward.png](../../assets/poker_head/ph_long_reward.png) | Long Hand Dividend | permanent / multi-card | card-draw | Deck and draw arrow | Building a longer hand for additional reward. |
| [ph_court.png](../../assets/poker_head/ph_court.png) | Court Discount | permanent / multi-card | card-king-hearts | King playing card | Discounted values for the J/Q/K family; the suit is decorative. |
| [ph_five_reward.png](../../assets/poker_head/ph_five_reward.png) | Five Card Feast | permanent / multi-card | poker-hand | Fan of playing cards | A large-hand reward triggered at five cards. |
| [ph_mark.png](../../assets/poker_head/ph_mark.png) | Sleeve Mark | permanent / multi-card | semi-closed-eye | Discreet eye | Automatic next-rank information at the beginning of the turn. |
| [ph_late_retreat.png](../../assets/poker_head/ph_late_retreat.png) | Exit Clause | permanent / surrender | exit-door | Exit door | Surrender remains available after drawing. |
| [ph_loss_discount.png](../../assets/poker_head/ph_loss_discount.png) | Retreat Discount | permanent / surrender | shaking-hands | Handshake | A negotiated reduction in surrender cost. |
| [ph_claim.png](../../assets/poker_head/ph_claim.png) | Recovery Receipt | permanent / surrender | receive-money | Hand receiving coins | Conditional compensation after the next win. |
| [ph_ace.png](../../assets/poker_head/ph_ace.png) | Comeback Ace | permanent / surrender | card-ace-hearts | Ace playing card | A guaranteed first opening ace after surrender; suit is decorative. |
| [ph_jackpot.png](../../assets/poker_head/ph_jackpot.png) | Perfect Payout | permanent / precision | coins-pile | Sparkling coin pile | A large payout tied to a winning total of 21. |
| [ph_sleeve.png](../../assets/poker_head/ph_sleeve.png) | Spare Sleeve | permanent / precision | card-exchange | Two cards and exchange arrows | A free permanent card replacement each round. |
| [ph_borrow.png](../../assets/poker_head/ph_borrow.png) | Borrowed Glory | permanent / precision | Original SVG B | 21 card, one-way arrow, crown and receiving hand | The dealer starting natural transfers its victory outcome to the player; no actual hand exchange. |
| [ph_late_double.png](../../assets/poker_head/ph_late_double.png) | Raise Permission | permanent / double | buy-card | Money bag, card and transaction arrows | Permission to commit additional chips after hitting. |
| [ph_risk.png](../../assets/poker_head/ph_risk.png) | Shared Risk | permanent / double | Original SVG B | Three-quarter disk and a quarter protection shield | 25% of a doubled loss is covered; the player still pays the exposed 75%. |
| [ph_audit.png](../../assets/poker_head/ph_audit.png) | Open Audit | permanent / double | eye-target | Eye with an inspection reticle | Automatic inspection of a dealer hole card worth at least ten. |
| [ph_discount.png](../../assets/poker_head/ph_discount.png) | Purchasing Privilege | permanent / finance | price-tag | Price tag | Reduced prices for ordinary shop purchases. |
| [ph_yield.png](../../assets/poker_head/ph_yield.png) | Yield Privilege | permanent / finance | profit | Money bag and incoming arrows | Additional positive investment proceeds. |
| [ph_refresh.png](../../assets/poker_head/ph_refresh.png) | Priority Exchange | permanent / finance | anticlockwise-rotation | Circular refresh arrow | An extra free refresh of the shop stock. |
| [ph_gift.png](../../assets/poker_head/ph_gift.png) | The Dealer's Invitation | management / general | present | Wrapped present | The free opening core-or-cash choice. |
| [ph_change.png](../../assets/poker_head/ph_change.png) | Amendment Letter | management / general | envelope | Envelope | A letter amending the run core. |
| [ph_peek.png](../../assets/poker_head/ph_peek.png) | Card Lens | consumable / general | magnifying-glass | Magnifying glass | One active inspection of the next rank. |
| [ph_swap.png](../../assets/poker_head/ph_swap.png) | Sleeve Clip | consumable / general | card-exchange | Two cards and exchange arrows | A consumable replacement of the first card. |
| [ph_hole.png](../../assets/poker_head/ph_hole.png) | Hole Probe | consumable / general | cyber-eye | Circuit-pattern eye | Active revelation of the dealer hole card. |
| [ph_radar.png](../../assets/poker_head/ph_radar.png) | Risk Pointer | consumable / general | radar-sweep | Radar sweep | A next-hit danger check. |
| [ph_oracle.png](../../assets/poker_head/ph_oracle.png) | Fate Forecast | consumable / general | crystal-ball | Crystal ball | A pre-bet forecast of two post-deal cards. |
| [ph_remove.png](../../assets/poker_head/ph_remove.png) | Clause Removal | consumable / general | scissors | Scissors | Removing an existing persistent clause permanently. |
| [ph_silence.png](../../assets/poker_head/ph_silence.png) | Silence Seal | consumable / general | wax-seal | Wax seal | Suppressing rules temporarily for one round. |
| [ph_buffer.png](../../assets/poker_head/ph_buffer.png) | Temporary Allowance | consumable / multi-card | Original SVG A | +2 approval paper, ceiling bar and upward arrow | Permission to raise the player bust ceiling by two for this round. |
| [ph_waiver.png](../../assets/poker_head/ph_waiver.png) | Loss Waiver | consumable / surrender | ticket | Perforated ticket | A single surrender without loss. |
| [ph_aces.png](../../assets/poker_head/ph_aces.png) | Aces to the Top | consumable / precision | Original SVG B | Multiple A cards, deck layers and upward arrow | Move all remaining aces to the deck top without creating cards or guaranteeing 21. |
| [ph_undo.png](../../assets/poker_head/ph_undo.png) | Card Recall | consumable / precision | card-discard | Card bearing a removal mark | Discard the last player card while retaining at least two. |
| [ph_quad.png](../../assets/poker_head/ph_quad.png) | Fourfold Ticket | consumable / double | Original SVG A | Perforated ticket with x4 lettering | Prepare the next legal double to stake four times the original bet; no randomness. |
| [ph_buyback.png](../../assets/poker_head/ph_buyback.png) | Original Price Receipt | consumable / double | return-arrow | Returning arrow | Reverse another consumable purchase at its actual paid price. |
| [ph_deposit.png](../../assets/poker_head/ph_deposit.png) | Fixed Deposit | financial / finance | locked-chest | Locked chest | Principal remains locked until maturity. |
| [ph_bond.png](../../assets/poker_head/ph_bond.png) | Performance Bond | financial / finance | trophy | Trophy | The financial product depends on actual wins. |
| [ph_stock.png](../../assets/poker_head/ph_stock.png) | Risk Stock | financial / finance | chart | Zigzag market chart | An uncertain investment outcome, not guaranteed profit. |
| [ph_loan.png](../../assets/poker_head/ph_loan.png) | Short Loan | financial / finance | scroll-quill | Scroll and quill | Written borrowing terms with a repayment obligation. |

## Delivery and maintenance

- Final location: `assets/poker_head/<product ID>.png`, one file per catalog entry.
- File format: 256x256 RGBA PNG with real alpha transparency; transparent corner pixels and zero RGB under fully transparent pixels.
- Processing: trim to the visible subject, contain without stretching, center and preserve 12% transparent margin. The longest visible subject side is approximately 195 pixels.
- Masters: retained 512-pixel source PNGs in `black-jack-assets/exports/poker-head-approved-sources-v1/`; original SVGs remain in their source folders. All exports downscale; none upscale a raster source.
- Runtime registration: every product ID is registered as a 256x256 item asset in [the GUI manifest](../../chaos_blackjack/gui/assets/manifest.py). The normal asset manager resolves these files when the UI requests the corresponding ID.
- Licensing: preserve the 36 API attribution rows and five original-art records in [assets/CREDITS.md](../../assets/CREDITS.md). API icons remain CC BY 3.0. Recoloring, rasterization, trimming and centering are recorded there.

Re-export from the retained art repository:

```powershell
python scripts/asset_tools.py plan black-jack-assets/docs/poker-head-approved-export-plan.json --dry-run
python scripts/asset_tools.py plan black-jack-assets/docs/poker-head-approved-export-plan.json --force
python scripts/validate_assets.py --dir assets/poker_head
```

Use `--force` only when deliberately replacing the approved PNGs; the normal exporter refuses existing outputs. The five SVG study previews can be rebuilt with `python scripts/draw_poker_head_icons.py`. The export plan and raw artwork belong to the separate, git-ignored art repository. Delivery verification uses the shipped PNGs and manifest without raw sources or network requests.

## Review evidence

- All 41 product IDs match the current runtime catalog; all shipped files match GUI manifest sizes.
- All 41 staged and delivered icons pass the asset validator; delivered SHA-256 hashes match the manifest.
- The runtime asset manager resolves all 41 files at native 256px and preview 32px sizes.
- The six existing asset-pipeline tests pass.
- The full suite was retried against the latest workspace with `--maxfail=1`. It stops at `tests/test_balance_data.py::test_shipped_values_are_unchanged`: the ongoing build implementation adds 35 `ph_*` shop prices while that test asserts the old exact price dictionary. This artwork change does not edit balance data, and a full-suite pass is not claimed. Details: `output/poker_head_icons/full-suite-result.txt`.
- The normalized 32px, 48px and 128px originals were inspected on dark, felt-green and light backgrounds.
- [Final complete overview](../../output/poker_head_icons/approved_preview/overview.png) and [selected original studies on three backgrounds](../../output/poker_head_icons/approved_preview/custom_selected.png) are local review artifacts.

The stock preview command uses an outdated tooltip helper that refers to `TableScene.item_panel`. Reusing its existing scene and matte rendering functions separately produced the Poker Head table, its live shop offers and all five original-icon mattes successfully; [the live shop preview](../../output/poker_head_icons/game_preview/poker_head_shop.png) was visually inspected.

Artwork does not change game rules or the effect descriptions. Runtime GUI behavior beyond requesting the registered product ID remains the responsibility of the build-table implementation.
