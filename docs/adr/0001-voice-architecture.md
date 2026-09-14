# ADR-0001: ClauseCatcher Voice Architecture — One Voice Agent Session vs. Two Connections

**Date**: 2026-09-13
**Status**: Accepted 2026-09-14 — Option B (two connections), confirmed by user after pre-registered Probe A (spikes/protocol/PROBE_A_SPEC.md + addendum): P3 strong prompt valid FAIL (4 transcripts, 4 replies); corrected P2 (vad_threshold 1.0, min_silence 1000, max_silence 10000) INVALID — accepted by server but 0 speech detected; P1 silence PASS (non-decisive); docs show no reply-suppression control.
**Deciders**: Vishal Patel

## Context

ClauseCatcher must transcribe a live sales rep continuously, stay silent unless
the rep contradicts an uploaded contract clause, then speak an alert, and
separately answer a human monitor's spoken questions ("what does clause X
say"). Deadline is Sep 30 2026 (17 days out), solo builder, $0 spend, demo is
a recorded video, entry is for the **AssemblyAI Voice Agent Hackathon**. Two
architectures were spiked and partially live-tested against
`spikes/protocol/PROTOCOL.md` and the run history in
`clausecatcher-assemblyai-hackathon.md`. The central open question is whether
one Voice Agent session can be made to "stay silent unless addressed" — this
was tested live and observed to fail.

## Decision Drivers (weighted)

| Driver | Weight | Why |
|---|---|---|
| Demo reliability | 35% | Single recorded take; a session that talks over the rep ruins it |
| Deadline risk | 25% | 17 days solo; unresolved unknowns cost real days |
| Judge perception of Voice Agent usage | 20% | Hackathon is Voice-Agent-specific (assumption, see Option C) |
| Cost vs. $50 credit | 10% | Both options are cheap relative to $50; low weight |
| Product truthfulness | 10% | Don't ship a "monitor" feature that can't actually stay quiet |

## Options

### A. One Voice Agent session (rep audio in, silent-unless-contradiction, alerts via `conversation.message`+`reply.create`, monitor Q&A via client-side tool)

**Pros**
- Single connection, simplest wiring.
- Q1 proved (N=1) that `conversation.message`(role user) + `reply.create`
  makes the agent speak on command with 0 user-transcript echo events.
- Maximizes visible Voice Agent API surface for judges (assumption).

**Cons — tied to evidence**
- The core premise, "stay silent unless addressed," was **live-tested and
  failed**: at 24 kHz with 23.5s of rep audio and a system prompt instructing
  silence, the agent auto-started 4 replies anyway (what it said was not
  recorded). This is a *known failure*, not a hypothesis.
- PROTOCOL.md's `turn-detection-and-interruptions` page was checked
  specifically for a listen-only / no-auto-reply mode and found none: no
  `mode`/`type` enum, only sensitivity/timing knobs (`vad_threshold`,
  `min_silence`, `max_silence`, `interrupt_response`). There is no documented
  off-switch for auto-reply — silence is prompt-only, and prompting already
  failed once live.
- 16 kHz input never reached `session.ready` in 3/3 sessions (2×
  `internal_error`/1011, 1× no-ready in 10s); only 24 kHz is confirmed
  working, so the rep's real audio pipeline must be resampled to 24 kHz
  regardless of option chosen.
- Q3 (client-side tool call, needed for monitor Q&A) was never validly
  tested — it only ran at 16 kHz, which crashed before the tool path could
  exercise.
- No documented speaker diarization on the Voice Agent API at all (confirmed
  absent from the full config-field list on `create-agent`) — a single
  session mixing rep + monitor audio has no protocol-level way to tell them
  apart.
- Billed for the full call duration at $4.50/hr even while silently
  listening, since it is the only connection open.

### B. Two connections: Streaming STT v3 (rep, always-on) → backend claim-check (Gemini free tier) → Voice Agent opened for alerts (`conversation.message`+`reply.create`) and monitor Q&A + tool

**Pros**
- Matches PROTOCOL.md's own documented-evidence conclusion: it explicitly
  states two-connection (Streaming v3 for rep + Voice Agent for monitor) is
  "the only combination fully backed by documented events," because
  Streaming v3 is a pure STT session with no LLM auto-reply behavior to
  fight — silence is structural, not prompted.
- Streaming v3 documents `speaker_labels`/`max_speakers`, giving a real
  rep-vs-monitor distinction Option A cannot produce.
- The one thing proven to work (Q1: inject `conversation.message` +
  `reply.create` → agent speaks, 0 echo) is used exactly as tested: as a
  short, on-demand utterance, not as a full-session "must stay quiet for
  minutes" behavior.
- Monitor Q&A is a case where auto-reply-on-user-speech is the *desired*
  Voice Agent behavior, not a bug being fought — so B routes Voice Agent to
  the one job the docs and Q1 actually validate it for.
- Cheaper for extended dev testing (see cost section) since the expensive
  connection only opens for short bursts.

**Cons — tied to evidence**
- The claim-check step (Gemini) is untested. T2 in the run history was only
  a keyword stub, not an LLM, and was wrong on at least 1 of 5 turns —
  contradiction detection accuracy is unproven with a real LLM.
- Streaming keyterms benefit is weak evidence: WER moved 0.155→0.121 but
  N=1 and half the delta was punctuation noise (WER doesn't strip
  punctuation), so only one real keyterm effect ("50"→"fifty") is confirmed.
- Never live-tested end-to-end: no run has gone Streaming transcript →
  Gemini claim-check → freshly-opened Voice Agent → spoken alert. Q1 opened
  the Voice Agent session as the *first* action of that test, not "opened
  reactively mid-call" — cold-open latency and reliability from that
  trigger point is unmeasured.
- Q3 (client-side tool call for monitor Q&A) still carries the same
  never-validly-tested status as in Option A — it crashed at 16 kHz before
  ever exercising, independent of which option owns it.
- Two connections is more moving parts to wire and debug than one, which
  costs solo-builder time against the 17-day deadline.

### C. Other option (flagged assumption: hackathon likely expects visible Voice Agent API use)

Variant considered: Streaming STT (rep) → backend claim-check → **plain TTS**
for alerts (no Voice Agent at all for alerts), Voice Agent used only for
monitor Q&A. This removes Option A's disproven "stay silent" LLM behavior
entirely — a plain TTS call is deterministic and cannot auto-reply, since
there is no LLM turn-taking involved for the alert path at all. It is
strictly more reliable than A for the alert half of the product.

**Why not chosen as the primary recommendation**: this reduces the alert
half of the product to zero Voice Agent API usage, which under the
assumption that judges score depth of Voice Agent API use, is a real risk
for a hackathon named specifically after that API. This assumption is not
verified against actual judging criteria — the user should check the
hackathon's judging rubric before ruling C out. If judging weighs
"solves the problem" over "which specific AssemblyAI product," C's
alert-reliability is the strongest technical choice of the three.

## Cost Estimate — arithmetic shown

Rates (PROTOCOL.md, quoting `pricing`): Voice Agent **$4.50/hr = $0.075/min**;
Streaming **$0.15/hr–$0.45/hr = $0.0025–$0.0075/min** (tier-dependent,
un­specified which tier T1 used). Billing is per websocket-open time, not
audio duration.

### Per 1 hour of dev testing

- **Option A**: one Voice Agent connection open the full hour (it carries
  all rep audio) → `1 hr × $4.50/hr = $4.50`.
- **Option B**: Streaming open the full hour (rep audio) + Voice Agent
  opened in short bursts for testing alerts/monitor — assume 5 min of
  Voice Agent time in a representative testing hour (assumption, stated):
  `Streaming: 60 min × $0.0025–$0.0075/min = $0.15–$0.45`
  `Voice Agent: 5 min × $0.075/min = $0.375`
  `Total: $0.525–$0.825`

### Per 3-minute demo take

- **Option A**: session open the whole take → `3 min × $0.075/min = $0.225`.
- **Option B, on-demand** (Voice Agent opens only for ~2 alerts + 1 monitor
  answer, ~30s total, assumption stated):
  `Streaming: 3 min × $0.0025–$0.0075/min = $0.0075–$0.0225`
  `Voice Agent: 0.5 min × $0.075/min = $0.0375`
  `Total: $0.045–$0.06`
- **Option B, kept-open** (Voice Agent connection held open the whole take
  with no mic audio fed, to avoid cold-open latency risk mid-recording):
  `Streaming: 3 min × $0.0025–$0.0075/min = $0.0075–$0.0225`
  `Voice Agent: 3 min × $0.075/min = $0.225`
  `Total: $0.2325–$0.2475` — effectively the same cost as Option A.

Both options are trivially inside the $50 credit for any realistic amount of
dev testing and demo takes (driver weight 10% reflects this — cost is not a
differentiator here; reliability is).

## Unknowns and Cheapest Live Probes

| Option | Unknown | Cheapest probe | Est. cost |
|---|---|---|---|
| A | Does any prompt/turn_detection variant (e.g. `interrupt_response: false`, `role: "system"` injection instead of `"user"`) actually hold silence, given the one tested variant failed? | 1–2 min session, 24 kHz, feed rep audio, vary one knob, check for unsolicited `reply.started` | $0.075–$0.15 |
| A / B (shared) | Does the client-side tool call (`lookup_clause`) actually round-trip (`tool.call`→`tool.result`) at 24 kHz? Never validly tested. | 1–2 min session, 24 kHz, trigger one tool call, confirm `tool.result` accepted and reply follows | $0.075–$0.15 |
| B | Does a Voice Agent session opened *reactively* (mid-flow, after a Streaming-detected contradiction) reliably reach `session.ready` and speak the alert with acceptable latency, vs. Q1's cold-start-first test? | 1 open + `conversation.message`+`reply.create`, timed from open to `reply.done` | ~$0.075 (1 min) |
| B | Does Gemini free-tier claim-check correctly flag contradictions vs. false positives, replacing the keyword stub that was wrong on 1/5? | Run Gemini prompts offline against the same 5 test turns T2 used, no AssemblyAI connection | $0 |
| B | Is the keyterms WER improvement real beyond N=1 and the punctuation artifact? | Re-run T1 with punctuation stripped before WER calc, N≥3 turns | $0 (reuses existing Streaming budget) |
| A / B (shared) | Does 16 kHz ever work, or is 24 kHz mandatory (forcing a resample step in both options)? | Retry one identical 16 kHz session (transient-failure check per run-history note) | ~$0.05 (30–40s session) |

## Recommendation

**Recommended: Option B**, confidence **Medium-High**.

Rationale: Option A's central premise — a Voice Agent session that stays
silent unless addressed — is not a hypothesis needing more testing, it is
an **observed live failure** (4 unsolicited replies despite an explicit
silence prompt), and PROTOCOL.md independently confirms there is no
documented off-switch for auto-reply to fall back on. Option B avoids this
failure mode structurally: Streaming v3 is pure STT with no reply behavior
to fight, and the one Voice Agent behavior that *is* proven working (Q1:
inject + `reply.create` → clean spoken output) is used in B exactly as
tested — a short, on-demand utterance — rather than stretched into a
full-session "must stay quiet" requirement it already failed at. B is also
cheaper for iterative dev testing, which matters more than the file's
demo-cost gap (both options cost fractions of a dollar per demo take).

The confidence is not "High" because B carries its own unresolved,
higher-stakes gap: the full pipeline (Streaming → Gemini claim-check →
reactively-opened Voice Agent alert) has never been run end-to-end, and the
claim-check accuracy is currently only a wrong-1-in-5 keyword stub. If the
cheapest probes above (total under ~$0.50) are run and either (a) an
Option-A silence variant is found that holds, or (b) B's reactive-open
alert path fails latency/reliability checks, this recommendation should be
revisited.
