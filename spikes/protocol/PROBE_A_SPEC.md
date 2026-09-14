# PROBE_A_SPEC — Single-Session (Option A) Cheap Probes

Pre-registered BEFORE any live run. No AssemblyAI API calls were made writing
this spec. All turn_detection field names/types/ranges are quoted verbatim
from `PROTOCOL.md` ("Reply-control doc check", 2026-09-13). Baseline: Q2
live run 2026-09-13, 24kHz, `audio/pcm`, N=1 (`spike_voice_agent.py
test_silence`).

## Ranges used, per field (source: PROTOCOL.md §1 table)
- `vad_threshold`: documented range 0.0–1.0, "Lower is more sensitive" →
  extreme for least-sensitive-to-speech = **1.0**.
- `interrupt_response`: documented boolean, "Set false to disable barge-in
  entirely" → **false**.
- `interruption_delay`: documented range 0–1000 ms → extreme = **1000**.
- `min_silence` / `max_silence`: **NOT DOCUMENTED as a numeric range** for
  the Voice Agent API (PROTOCOL.md only quotes their *purpose*, no
  min/max). No invented number is used. The only numeric examples found
  anywhere in PROTOCOL.md are Streaming v3's *different* fields
  `min_turn_silence: 700` / `max_turn_silence: 1600` (UpdateConfiguration
  example) — used here as the most-extreme-documented placeholder,
  **flagged UNVERIFIED for applicability to Voice Agent's `min_silence`/
  `max_silence`**. Value used: **1600** for both.

## P1 — silence_only
~12s digital silence, PCM16 mono 24kHz (no speech), baseline prompt, default turn_detection.
```json
{"type":"session.update","session":{
  "system_prompt":"You are ClauseCatcher. Stay completely silent and do not respond to anything unless the speaker directly addresses you by name, 'ClauseCatcher'. Ordinary conversation not directed at you gets no reply at all.",
  "input":{"format":{"encoding":"audio/pcm","sample_rate":24000}}
}}
```
Max duration: 12s audio + 10s drain = HARD_CAP ~30s session-open.
Est. cost: ~30s @ $4.50/hr ≈ **$0.0375**.
Record: reply.started count, reply.audio chunk count, transcript.agent texts, transcript.user texts, session.updated payload, error_events, event_log.
PASS: 0 reply.started.
INVALID: no session.ready, or session.error before ready → rerun once; still invalid → record, don't count.

## P2 — turn_extreme
rep_pitch.wav (24kHz), baseline prompt, turn_detection at documented extremes.
```json
{"type":"session.update","session":{
  "system_prompt":"You are ClauseCatcher. Stay completely silent and do not respond to anything unless the speaker directly addresses you by name, 'ClauseCatcher'. Ordinary conversation not directed at you gets no reply at all.",
  "input":{
    "format":{"encoding":"audio/pcm","sample_rate":24000},
    "turn_detection":{
      "vad_threshold":1.0,
      "min_silence":1600,
      "max_silence":1600,
      "interrupt_response":false,
      "interruption_delay":1000
    }
  }
}}
```
Audio: rep_pitch.wav, all 4 lines, same as baseline. Max duration: wav length (~15-20s, unmeasured) + 10s drain, capped at HARD_CAP_S.
Est. cost: ~30s @ $4.50/hr ≈ **$0.0375**.
Record: same fields as P1, plus input_evidence (transcript.user/.delta, input.speech.started counts).
PASS: 0 reply.started AND ≥1 transcript.user.
INVALID: no session.ready, session.error before ready, or 0 transcript.user → rerun once; still invalid → record, don't count.

## P3 — strong_prompt
rep_pitch.wav (24kHz), default turn_detection (no override — same as baseline), much stronger imperative prompt, name-exception REMOVED.
```json
{"type":"session.update","session":{
  "system_prompt":"You are a silent note-taking system, not a conversational participant. You must never produce any audio or text reply to anything the speaker says, under any circumstances — this includes if the speaker addresses you by name or asks you a direct question. Your only permitted output is when the system sends you an explicit instruction via a separate channel. If you are ever unsure whether to speak, the answer is: do not speak.",
  "input":{"format":{"encoding":"audio/pcm","sample_rate":24000}}
}}
```
Audio: rep_pitch.wav, all 4 lines, same as baseline. Max duration: wav length + 10s drain, capped at HARD_CAP_S.
Est. cost: ~30s @ $4.50/hr ≈ **$0.0375**.
Record: same fields as P2.
PASS: 0 reply.started AND ≥1 transcript.user.
INVALID: same as P2.

## Decision rules
1. If P2 or P3 PASS → rerun that exact config N=2 more times before believing it (3/3 required).
2. Single-session Option A is viable **only if**: P2 or P3 reaches 3/3 PASS, **and** a separate follow-up Q1-style injected-alert test (`conversation.message` + `reply.create`) still produces real speech in that same passing config. This follow-up is out of scope for these 3 probes — record as a required next step, do not run it here.
3. If all valid probes (P1, P2, P3) FAIL → adopt Option B (two-connection architecture, per ADR-0001).
4. If a probe is INVALID (setup error, no session.ready, or no transcript.user for P2/P3) → rerun once with identical config. Still invalid on rerun → record as INVALID, do not count toward PASS/FAIL tallies, do not treat as evidence either way.
5. P1's 0 reply.started result, if PASS, is necessary but not sufficient for Option A — P1 has no speech in it at all, so it cannot show whether the agent stays silent *while hearing real speech*. Only P2/P3 PASS results bear on the actual viability question.

## Total estimated cost, all 3 probes single run: ~$0.11. With P2/P3 confirmation reruns (worst case both 3/3): ~$0.34 total.

## Addendum 2026-09-14: P2 corrected rerun (pre-registered)

**1. Why original P2 was INVALID, and why an identical rerun is not meaningful.**
Live run 2026-09-14: server rejected the session at setup, before session.ready:
`session.error invalid_value 'input.turn_detection.min_silence' must be
strictly less than 'max_silence'` (sent `min_silence` 1600 = `max_silence`
1600). Per this spec's own INVALID definition (line 59: "no session.ready,
session.error before ready... → INVALID"), P2 is INVALID, not FAIL — the
harness's printed FAIL label is wrong (see §5). This is a deterministic
validation error: rule 4's literal "rerun once with identical config" cannot
resolve it — the identical config will always be rejected identically. By
user decision (2026-09-14), this rerun uses a corrected config instead,
deviating from rule 4's literal wording.

**2. Corrected config (Candidate A).** Same baseline `system_prompt` as
original P2 (verbatim, line 42). Field-by-field, cited to
`voice-agent-api.yaml` `TurnDetection` (lines ~742-767) except where noted:
```json
{"type":"session.update","session":{
  "system_prompt":"You are ClauseCatcher. Stay completely silent and do not respond to anything unless the speaker directly addresses you by name, 'ClauseCatcher'. Ordinary conversation not directed at you gets no reply at all.",
  "input":{
    "format":{"encoding":"audio/pcm","sample_rate":24000},
    "turn_detection":{
      "vad_threshold":1.0,
      "min_silence":1000,
      "max_silence":10000,
      "interrupt_response":false,
      "interruption_delay":1000
    }
  }
}}
```
- `vad_threshold` 1.0: YAML `number` 0–1, default 0.5, "lower is more
  sensitive" → 1.0 is the least-sensitive extreme, within range.
- `min_silence` 1000: YAML `int` ms 50–10000, default 1000, "Must be less
  than max_silence" → set to schema default, satisfies constraint against
  the new max_silence.
- `max_silence` 10000: YAML `int` ms 50–10000, default 3000, "Must be
  greater than min_silence" → set to the schema max, satisfies constraint.
- `interrupt_response` false: YAML `bool`, default true → unchanged from
  original P2.
- `interruption_delay` 1000: **prose-only**, not in the YAML schema; prose
  docs give 0–1000 ms (default inconsistent) → unchanged from original P2.

**3. Pre-registered risk.** `vad_threshold` 1.0 may suppress speech
detection entirely → 0 `transcript.user` → INVALID per line 59's own
"0 transcript.user" clause. If P2r comes back INVALID again: record as
INVALID, no further reruns, do not count it toward any PASS/FAIL tally.

**4. Outcome → next step (pre-registered, replaces the unfireable rule 3 for
this decision).** Rule 3 ("all valid probes FAIL → adopt Option B") can
never fire because P1 always passes (no speech, nothing to trigger a reply).
Per rule 5, P1 is excluded from the "all fail" condition here since it
contains no speech and cannot test staying silent *while hearing speech*.
- **P2r valid FAIL** (≥1 transcript.user, ≥1 reply.started) → both
  speech-bearing probes (P2r, P3) are valid FAIL → adopt Option B
  (ADR-0001 → Accepted).
- **P2r INVALID** (setup error or 0 transcript.user) → only P3 is valid;
  single-session behavior under extreme turn_detection remains unshown →
  adopt Option B on P3 + documented PROTOCOL.md reply-control evidence,
  noting P2 untested.
- **P2r PASS** (0 reply.started, ≥1 transcript.user) → run this exact config
  2 more times; only 3/3 PASS plus a Q1-style injected alert still
  producing real speech in this config (rule 2) keeps Option A alive;
  anything less → adopt Option B.

**5. Grading note.** The harness prints FAIL for setup errors that occur
before session.ready; graders must classify these as INVALID per this
spec's own definitions (line 59), not FAIL. The implementer is adding an
evidence field `spec_grade` (PASS/FAIL/INVALID) to disambiguate the
harness's raw label from the spec-correct classification.

**6. Cost.** ~30s session ≈ $0.0375 at $4.50/hr; harness worst case (3 runs:
INVALID rerun attempt + 2 confirmation reruns under §4's PASS branch)
≈ $0.1475.
