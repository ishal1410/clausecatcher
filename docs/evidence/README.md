# Evidence

Raw logs behind the numbers in the README, the deck and the lablab submission text.
`.gitignore` excludes `**/out/`, which is where these files are produced, so they are
copied here to be readable without running anything.

| File | What it is | Bytes |
|---|---|---|
| `e2e_mic_run-live.json` | Every websocket message from the automated browser-mic run, 2026-09-17 (`tools/e2e_mic/run_mic_e2e.py`) | 119 KB |
| `demo_take_timeline.json` | Beat timeline of the take that became `docs/submission/demo.mp4` | 1.2 KB |
| `demo_take_events.json` | The same take's websocket log, rep-line timings and agent speech intervals | 5.7 KB |
| `voice_agent_probe_gate_20260915.json` | The Voice Agent probe that decided the architecture: 8 speak variants graded against the source text | 5.6 KB |
| `claim_check_eval_20260918.json` | The 32-claim Gemini accuracy eval, every prediction kept | 17 KB |

## How to check each published number

**Alert latency, 4 to 6.5 s across five alerts.**

- 5.6 s and 4.0 s — `demo_take_timeline.json`. Subtract the end of a `rep_intervals`
  entry from the alert that follows it: `69.05 - 63.46 = 5.59`, `110.07 - 106.08 = 3.99`.
- 6.49 s — `e2e_mic_run-live.json`. The last final transcript before the alert is at
  `t_ms` 6469; the alert is at `t_ms` 12954.
- 6.2 s and 4.3 s — the first live take, on 2026-09-15. Recorded in
  `docs/submission/DEMO_NOTES.md`; that take's log was not kept, so those two are the
  only figures here without a file behind them.

**Alert to first spoken word, 375 ms.** `e2e_mic_run-live.json`: alert at `t_ms` 12954,
first `agent_audio` at `t_ms` 13329.

**Speak request to first audio frame, 78 to 890 ms.** `voice_agent_probe_gate_20260915.json`,
the `first_audio_ms` field on each step: 156, 890, 203, 78, 188, 203, 203, 4890. The 78 is
the fastest of the eight and was the headline number until 2026-09-17; the deck and cover now
lead with 375 ms instead, because that is the boundary a listener experiences. The 4890 is the
tool round trip, which graded INVALID and is why no tools are registered (see `docs/adr/0001-voice-architecture.md`).

**Say-exactly beats message injection.** Same probe file. Injecting the alert as a
conversation message without a say-exactly instruction scored 0.179, 0.258 and 0.27
similarity and graded FAIL; the two say-exactly variants scored 1.0 with `literal_spoken: true`.

**Cost, $0.08 to $0.15 per call.** `e2e_mic_run-live.json`, the `session_ended` report:
`est_cost_usd` 0.0755 for a 55 s call. The $0.1535 figure for the 1:52 demo call comes from
the report on screen at 2:32 of `demo.mp4` and from `DEMO_NOTES.md`; it has no log here.
Both are the app's own estimate, which prices AssemblyAI at list rate by connection time
and does not meter Gemini at all. Neither is a billed amount.

**Similarity 1.0, spoken verbatim.** `demo_take_events.json`, the `agent_speaking` events:
the text the agent reported speaking is the clause's literal text with a one-line frame
("Contract alert: section 3.1 says: ..."). The similarity score grades that transcript
against the contract text. Nobody transcribed the audio that actually played, so this
checks the agent's own report of what it said.

**17 of 17 live-path checks.** `e2e_mic_run-live.json` is the run those checks read.
The checks themselves are the `check()` calls in `tools/e2e_mic/run_mic_e2e.py`. The
microphone was Chromium's fake audio device playing a WAV file, not physical hardware.

## Claim-check accuracy, measured 2026-09-18

`claim_check_eval_20260918.json`, from `python spikes/claim_check/eval_claim_check.py`
against `spikes/claim_check/labeled_claims.json` (32 labeled sentences) on
`gemini-3.5-flash-lite`, the model the server ships with. Free tier, no billing.

| Metric | Value |
|---|---|
| Contradiction recall | 14/14 = 1.0 |
| False alarm rate (consistent or unclear called a contradiction) | 0/18 = 0.0 |
| Clause ID correct on caught contradictions | 14/14 = 1.0 |
| Errors | 0 |
| Latency p50 / p95 | 3461 ms / 3995 ms |

Confusion matrix, expected down, predicted across:

| | contradiction | consistent | unclear |
|---|---|---|---|
| **contradiction** | 14 | 0 | 0 |
| **consistent** | 0 | 11 | 0 |
| **unclear** | 0 | 0 | 7 |

**What this does not show.** All 32 sentences were written by the project's author
against the same four-clause demo contract, so this measures the checker on its own
fixture, not on a contract or a rep it has never seen. A perfect score on 32 in-domain
examples says the prompt, the schema and the clause-ID validation work; it says nothing
about a 40-page MSA or ambiguous sales language. The p50 of 3.5 s is also the largest
single piece of the 4 to 6.5 s alert latency.

Two constants in `spikes/claim_check/claim_check.py` were corrected on 2026-09-17 before
this run: the model default was `gemini-2.5-flash`, which now returns 404 ("no longer
available to new users"), and the client deadline was 8000 ms, which Gemini rejects as
under its 10 s minimum. Both now match `server/claim_check.py`. The first attempt with the
old default produced 32 errors and 32 `unclear` verdicts; that run is not published here
because it measured a dead model id rather than the checker.
