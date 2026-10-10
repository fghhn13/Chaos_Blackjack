The background Chaos AI integration passed a live, billed API measurement on
2026-10-10. Eight consecutive rounds settled correctly, and rendering continued
during an 18.03-second real LLM response. No sampled asynchronous frame interval
exceeded 18 ms. The synchronous control blocked the render/event thread for
16.18 seconds.

The test ran from 21:20:37 to 21:21:27 (Asia/Shanghai), against game-code commit
`ba779d5` (see the full revision in the [recorded JSON](llm-gui-live-2026-10-10.json)).
The branch is `codex/llm-table-responsiveness`, based on `origin/main`.

| Configuration | Value |
| --- | --- |
| Backend | Real GPTsAPI `/chat/completions`, HTTPS |
| Environment | Windows 11, Python 3.12.7, Pygame 2.6.1 |
| Configured model | `gpt-6-luna` |
| Request timeout / output limit | 45 seconds / 256 tokens |
| Request cap / actual requests | 16 / 11 |
| GUI | Pygame, SDL dummy video/audio drivers, 1280 x 720, target 60 FPS |
| Game | Standard controller/pipeline, chaos enabled, seed 7, bet 5 |
| Bankroll / target | 100 / 10,000; the higher target keeps this measurement running |

The driver used real deals, the existing chaos prompt, permission checks and
rule application, then legal hit/stand commands and normal timed dealer steps.
It read player-visible snapshots rather than inspecting hidden cards or deck
order. Credentials were loaded from the existing ignored `.env` into process
memory. The artifacts contain timing, actions, token usage and results only.

| Async round | API time (s) | Frames sampled | Update max (ms) | Render max (ms) | Frame interval max (ms) | Result | Bankroll |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 1 | 0.6630 | 40 | 0.118 | 7.828 | 18 | Dealer win | 95 |
| 2 | 0.7641 | 47 | 0.142 | 6.376 | 17 | Player win | 100 |
| 3 | 0.6627 | 35 | 0.115 | 7.757 | 17 | Push | 100 |
| 4 | 0.5210 | 31 | 0.122 | 7.683 | 17 | Dealer win | 95 |
| 5 | 0.6779 | 41 | 0.150 | 7.683 | 17 | Player win | 100 |
| 6 | 0.4474 | 27 | 0.143 | 6.549 | 17 | Player win | 105 |
| 7 | 18.0329 | 1,094 | 0.277 | 8.013 | 18 | Dealer win | 100 |
| 8 | 0.7008 | 42 | 0.109 | 8.971 | 18 | Dealer win | 95 |

Across 1,357 samples, the maximum controller-update time was 0.277 ms and the
maximum render time was 8.971 ms. Each round's 95th-percentile frame interval was
17 ms. There were zero sampled intervals above the 100 ms stall threshold.
Sampling covers the active request and its completion frame; it excludes the
initial 0.4-second chaos delay. The five modal-only frames in round 3 are also
excluded from these per-table timing samples.

The thinking-dot pixels changed in every round. Each round recorded four pixel
signatures: the three cycling dot states plus the completion transition. H, S,
D, R and Enter were dispatched while the cached table was still in the chaos
phase; the snapshot stayed unchanged and all player buttons remained disabled.
All ten asynchronous API requests ran outside the main thread, and every
delivered notice callback ran on the main thread. Each completed round made
exactly one request; no JSON repair request or rejected chaos action occurred.
The ordinary two-win streak reward also occurred in round 6.

| Interaction probe | Measured handler time | Observed behavior |
| --- | ---: | --- |
| Cancel return-to-menu dialog, round 3 | Open 0.034 ms; cancel 0.025 ms | Returned to the table and completed the same request |
| Confirm return to menu during request | Confirm/reset 0.044 ms | Reached menu before response; a replacement table stayed unchanged after the old response |
| Dispatch window `QUIT` during request | 0.007 ms | Cleared `app.running` before response; no network wait inside the handler |

Both exit probes saw an unfinished request at exit. The harness let those
already-paid requests finish afterward to check for late-result effects; it
did not send cancellation or replacement requests. The window-quit probe
explicitly invoked the scene's exit hook afterward to check result disposal.

The synchronous control reproduced the old table command by calling
`resolve_chaos` on the main thread. Its API request took 16.1786 seconds and the
whole blocking command took approximately 16.18 seconds, during which the
harness could not render or dispatch events. The asynchronous 18.0329-second
request maintained 16-18 ms frame intervals. These are different requests;
the finding is separation of network latency from GUI work, not faster model
generation.

All 11 requests returned HTTP 200 with `finish_reason=stop`. The gateway reported
2,941 prompt tokens and 1,198 completion tokens: **4,139 total tokens**. This
includes the synchronous control and both exit requests. The API did not return
a monetary charge, so the actual billed amount is not inferred here.

This run used real network/model responses with headless rendering. It supports
the conclusion that real LLM latency no longer blocks this scene's render/event
loop. It does not measure an on-screen compositor, fullscreen switching, manual
play experience or long-session resource growth. All live responses selected
`odd_even_chaos`; other rule paths, network timeouts and malformed responses were
covered by offline regression tests rather than encountered in this live run.
The existing dialog stack pauses updates to the covered table while its modal
is open; that behavior remains unchanged.

The complete offline regression suite also passed after adding the measurement
driver and report: **132 passed**. That run forced `CHAOS_USE_LLM=0` and made no
additional billed requests.

The repeatable driver is [measure_live_llm_gui.py](../../scripts/measure_live_llm_gui.py).
Run it manually from the feature worktree, with the path to the original `.env`:

```powershell
python scripts/measure_live_llm_gui.py --paid --env-file "F:\fghn's AI\games\Black_jack\.env" --output docs/reports/llm-gui-live-new.json --rounds 8 --max-requests 16
```

`--paid` is mandatory, CI execution is rejected, and this script is outside
pytest discovery. Repeating the command makes new billed requests. Raw metadata
for this run is in [llm-gui-live-2026-10-10.json](llm-gui-live-2026-10-10.json).
