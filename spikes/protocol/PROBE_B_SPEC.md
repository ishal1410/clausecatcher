# PROBE_B_SPEC — Option B (Two-Connection) Pre-Registered Probes

Pre-registered BEFORE any live run or code exercise of `claim_check.py`,
`alert_agent.py`, `spike_chain.py`. Style follows `PROBE_A_SPEC.md`. Cites
`PROTOCOL.md` + ADR-0001 (Accepted, Option B). No API calls made writing this.

Fixtures: `spikes/harness/fake_contract.json` (clauses 3.1, 4.2, 5.3, 6.1),
`rep_pitch.wav`/`.txt` (L1 correct/4.2, L2 contradiction/3.1 discount, L3
contradiction/6.1 24/7, L4 ambiguous/5.3), `monitor_question.wav`/`.txt`
("ClauseCatcher, what does clause four point two say about renewal?").

## B2 — Gemini claim-check accuracy (offline eval, $0, blocked on Gemini key)

**Blocker:** no Gemini key is set on this machine yet; free-tier RPM isn't
published, must be read in AI Studio when the key is created. Key creation
is a prerequisite, not part of PASS/FAIL.

**Labeled set:** `claim_check/labeled_claims.json`, ≥24 items over the 4
clauses: verbatim + paraphrased contradictions, numeric contradictions
(wrong number, e.g. "60 days"→"30 days"), hedged claims, true/consistent
restatements, and "unclear" items (no clause fits, or genuinely ambiguous
like L4). Min mix: ≥6 contradiction, ≥6 consistent, ≥4 unclear.

**Run:** `eval_claim_check.py` calls `check_claim(sentence, clauses)` per
item, default `client`/`model`.

**Metrics:** contradiction recall; false-alarm rate on consistent items;
clause_id accuracy on true-positive contradictions; p95 `latency_ms`.

**Thresholds:** false-alarm rate ≤ 0.1, recall ≥ 0.9, clause_id accuracy ≥
0.9, p95 latency ≤ 1500 ms. **Decision:** a false accusation live (wrongly
interrupting the rep) is worse for the demo than a missed one (silence) →
false-alarm rate is the binding threshold, checked first; recall is
required but secondary.

**PASS:** all 4 met. **FAIL:** any missed (report which). **INVALID:**
`error` non-null on >10% of calls → fix harness, rerun; don't count partial
data. **Cost:** $0 (free tier, Zero Budget Rule).

## B3 — Reactive Voice Agent alert (live, cold vs. warm)

Config (matches the one proven-working Q1 shape — `wss://agents.assemblyai.com/v1/ws`, 24 kHz, no mic audio):
```json
{"type":"session.update","session":{
  "system_prompt":"You are ClauseCatcher's alert voice. When given an alert message, speak it verbatim, then stop.",
  "input":{"format":{"encoding":"audio/pcm","sample_rate":24000}}
}}
```
Alert text (literal clause, fetched by id, never LLM-generated):
`"Contract alert: section 3.1 says: no automatic or verbal discounting."`
Sequence: `session.update` → wait `session.ready` → `conversation.message`
(`role:"user"`, content = alert text) → `reply.create` → capture to
`reply.done`.

**Cold (N=3):** fresh `AlertAgent.open()` → `speak(alert_text)` → `close()`
each run. **Warm (N=3):** one `AlertAgent` opened once, idle 5s, then
`speak()` 3×, no `close()` between.

**Metrics:** connect→`session.ready` ms; inject→first `reply.audio` ms;
`transcript.agent` contains the literal text (exact, or normalized —
lowercase/punctuation-stripped — substring).

**PASS (per run):** literal text present AND inject→first-audio ≤ 2000 ms.
**FAIL:** text missing or latency > 2000 ms. **INVALID:** no
`session.ready` within 10s, or `session.error` before ready → rerun once;
still invalid → record, don't count.

**Cost:** cold 3×20s=60s + warm 1×50s (5×(5s speak+5s idle)) = 110s ≈
1.83 min × $0.075/min = **$0.137**.

## B4 — Monitor tool call at 24 kHz

Register client-side tool `lookup_clause`: `{"type":"function","name":"lookup_clause","parameters":{"type":"object","properties":{"section_number":{"type":"string"}},"required":["section_number"]}}`.
`AlertAgent.ask()` resolves `tool.call` by looking up `section_number` in
`fake_contract.json`, replies `tool.result` with the literal `literal_text`.

**Path 1 (audio, primary):** stream `monitor_question.wav` after
`session.ready` (auto-reply is *desired* here, not fought). **Path 2 (text
fallback, recorded separately):** `conversation.message`(role user, content
= the `.txt` transcript) + `reply.create`, hedging against ASR mishearing
"four point two."

**Metrics (both paths):** `tool.call` fires with `arguments.section_number
== "4.2"`; `tool.result` sent; spoken `transcript.agent` contains 4.2's
literal text.

**N=2 per path (4 runs).** **PASS:** correct section_number called AND
literal text spoken back. **FAIL:** wrong/no section_number, or text
missing. **INVALID:** no `session.ready`, or `tool.call` never fires →
rerun once → still invalid → record, don't count.

**Cost:** 4 runs × 15s = 60s = 1 min × $0.075/min = **$0.075**.

## B1 — Full chain latency (live, last)

`spike_chain.py` streams `rep_pitch.wav` to Streaming STT
(`wss://streaming.assemblyai.com/v3/ws`, 24 kHz), calls `check_claim()` per
`end_of_turn:true` Turn, and on `"contradiction"` calls a **warm**
`AlertAgent.speak(literal_text)` (per B3). Records per-turn `end_of_turn_ts`,
`claim_check_done_ts`, `first_reply_audio_ts`.

**Metric:** `first_reply_audio_ts − end_of_turn_ts` per contradiction turn.

**N=2 full-pitch runs. PASS:** median latency ≤ 3.5s over the 4 samples
(2 runs × L2,L3) AND both L2+L3 alerted with literal text in both runs
(4/4) AND 0 alerts on L1/L4 in either run. **FAIL:** median > 3.5s, a
contradiction missed, or a false alert on L1/L4. **INVALID:** Streaming
never reaches ready, or `check_claim` errors on any turn → fix, rerun;
don't count.

**Cost:** Streaming 2×~20s=40s=0.667min×$0.0025/min=$0.0017. Voice Agent
4 speaks×~5s=20s=0.333min×$0.075/min=$0.025. **Total B1 ≈ $0.027.**

## Decision rules

1. **Order: B2 → B3 → B4 → B1.** B2 ($0, offline) gates whether
   claim-check is trustworthy before live spend; B3/B4 isolate the two live
   components `spike_chain.py` depends on; B1 integrates all three, run
   last, only after B2 PASS/near-PASS.
2. **B2 FAIL** → add a rule-based keyword pre-filter (numbers, negation) +
   Gemini hybrid, or tighten the prompt with few-shot examples from the
   failing items; re-run B2.
3. **B3 cold FAIL on latency, warm PASS** → adopt a warm pre-opened
   `AlertAgent` for the demo window. Idle billing applies even silent
   (PROTOCOL.md, $4.50/hr = $0.00125/s): a 10-min window = 600s×$0.00125 =
   **$0.75** idle overhead — acceptable against the $50 free credit.
4. **B4 audio FAIL, text PASS** → ship monitor Q&A as typed-text fallback,
   note as a known limitation.
5. **B4 both paths FAIL** → drop the monitor Q&A tool from demo scope;
   B3 alerts still ship standalone.
6. **B1 FAIL** → use `spike_chain.py`'s per-turn timestamps to isolate the
   slow stage (STT end-of-turn, `check_claim.latency_ms`, or Voice Agent
   inject→audio) and apply the matching fix (B2 hybrid for accuracy, B3
   warm session for Voice Agent latency).

**Total expected cost** (single pass, B2 free): B3 $0.137 + B4 $0.075 + B1
$0.027 = **$0.239**. **Worst case** (one INVALID rerun per live probe,
PROBE_A's rerun-once rule) ≈ 2× live cost = **$0.48** — within the $50 free
credit (Zero Budget Rule).
