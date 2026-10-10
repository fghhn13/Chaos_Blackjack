# One live memory-enabled round — 2026-10-10

Result: **passed** after fixing compatibility with plain-text advice responses.
Tested implementation: `02ca3bd` on `codex/chaos-poke`. This test enabled
`chaos_memory_enabled=True` with a 32-event limit; the application default
remains disabled. The configured backend was `gpt-6-luna` at
`https://api2.gptsapi.net/v1`, with a 45-second timeout.

## Scenario and evidence

A new synthetic seed-7 run bought `danger_radar` for 10 chips in the shop.
The first portrait request received a real suggestion mentioning the 90-chip
bankroll and the radar. Its accepted reply was stored in memory. The test saved
to disk, reloaded, then played one round with a 5-chip bet and a real Chaos turn.
Chaos applied `modify_card_value` with `delta=1`. The player drew a Queen and
busted at 24; the bankroll ended at 85. A final real portrait request followed
the result screen, then memory was saved and reloaded again.

All six checks passed:

- Identical memory history after both pre-round and post-round disk reloads.
- The previous portrait reply was present in the actual outgoing payload for
  the subsequent Chaos turn and final portrait request.
- Shop purchase history was present in every real request.
- The round-settlement event was present in the final portrait request.
- All real requests ran off the GUI thread.

Seven memory entries remained: item purchase, first advice, round start, Chaos
narration, player draw, settlement, and final advice. The final response referred
to keeping the 10-chip radar and the previous round's +1-per-card rule. These
facts also appear in the current context, so this establishes correct history
delivery and coherent output, not proof that memory alone caused the response.

## Real response-format issue and fix

The first two attempts returned HTTP 200 with useful prose instead of the
requested `{"reply":"..."}` JSON. The original strict parser rejected them.
The second response was recorded; the first response text was not retained.

The advice parser now accepts either that exact JSON object or plain prose,
with the same non-empty 320-character limit. Structured gameplay-action JSON
and malformed structured responses remain rejected. Replies cannot execute
actions. This change makes no additional repair request.

To stay within the four-call ceiling, the final successful scenario reused the
second already-paid response for the initial portrait step. The harness checked
that memory, shop, inventory, bankroll, model and intent matched the recorded
initial context. The Chaos turn and result-screen portrait step were fresh real
requests. The replay step is not a measurement of live API latency.

| Actual paid call | Purpose | HTTP | API time | Total tokens |
| --- | --- | --- | --- | --- |
| 1 | Initial shop advice; strict parser rejected prose | 200 | 4.5611 s | 943 |
| 2 | Captured shop advice; reused after parser fix | 200 | 0.7890 s | 943 |
| 3 | Memory-enabled Chaos rule turn | 200 | 37.2615 s | 1,605 |
| 4 | Advice after settlement, with prior history | 200 | 4.2451 s | 1,581 |

Across all four calls: **4,561 prompt tokens + 511 completion tokens = 5,072
tokens**. The API did not return a currency charge, so no monetary amount is
estimated. Each request sent `max_tokens=256`; usage above is the actual
provider-reported usage.

## GUI and offline checks

The final scenario rendered 2,555 headless frames at a target of 60 FPS. Maximum
update time was 0.682 ms, maximum render time 61.265 ms, and maximum frame interval
61 ms; there were no intervals above 100 ms. During the final live portrait call,
259 frames rendered and the thinking dots changed state. Eight portrait clicks
queued in one frame produced a single request. The reused initial reply rendered
one frame and provides no live waiting-animation measurement.

The complete offline suite passed: **188 tests in 8.49 seconds**. The added
regression covers accepting real-style prose without another billed request.
This was headless SDL validation, not a native-window manual playtest or a
statistical evaluation of the 50/50 intent distribution. Both sampled portrait
intents were `guide`.

## Artifacts and reproduction

- [Successful scenario JSON](chaos-memory-live-2026-10-10.json): three verified
  scenario steps, including one explicitly marked reused paid response.
- [Attempt 1](chaos-memory-live-2026-10-10-attempt1.json) and
  [attempt 2](chaos-memory-live-2026-10-10-attempt2.json): preserved format failures.
- `scripts/measure_live_chaos_memory.py`: opt-in harness; refused in CI and bounded
  to at most four recorded requests. Fresh invocation performs three calls if
  the Chaos action does not need repair.

```powershell
python scripts/measure_live_chaos_memory.py --paid --env-file "<original repository>/.env" --output "<new report>.json"
```

Credentials were read only in memory from the existing ignored `.env`; artifacts
were checked for the real key before writing. No personal save or conversation
history was loaded. An initial automatic approval rejection was resolved after
a read-only audit verified the existing API destination and synthetic payload.
