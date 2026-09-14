# ClauseCatcher Scope Reset — 2026-09-14, ~6PM

Deadline: Sep 30 2026 11:00 AM EDT. **16 days left.** Verified by directory
listing: `<home>\clausecatcher\` contains only `docs/` and `spikes/`.
No `app/`, `backend/`, `frontend/`, no git repo (`git status` → "not a git
repository"). Zero product code exists. Confirmed, not assumed.

## 1. Are we distracted from root? — Yes, moderately, but not wasted

**Necessary de-risking (keep the value, stop doing more of it):**
- ADR-0001 killed Option A ("one session stays silent unless addressed")
  with a **live-tested failure**, not a guess — 4 unsolicited replies despite
  an explicit silence prompt. Finding this on Sep 13 instead of on demo day
  was worth the session it cost.
- Q1 proved the actual alert mechanism (`conversation.message` role=`user` +
  `reply.create` → clean spoken output, 0 echo). The whole product depends
  on this one call working — proving it before building the UI around it
  was correct.
- 16 kHz never reaching `session.ready` (3/3) — would have caused a silent,
  hard-to-diagnose crash mid-build if discovered later. Forces resample to
  24 kHz now, cheaply.
- `spikes/claim_check` offline eval (32 labeled examples, `"fake": true`,
  **$0 spent**, gemini-2.5-flash): 78.6% contradiction recall, 0% false-alarm
  rate. This answers "can an LLM even do the core judgment call" before
  wiring a UI around it. Good, cheap, necessary.

**Over-investigation (the actual distraction):**
- 3 full days, 41+ background-agent transcripts, and a standing
  `spikes/protocol/` directory (PROBE_A_SPEC, PROBE_B_SPEC, TEST_PLAN,
  PROTOCOL.md) — for what ADR-0001's own table sizes as **3 remaining
  unknowns, each a single short session, total under ~$0.50**. The
  investigation grew its own scope (specs about specs) independent of the
  product.
- The Option A/C "can one session stay silent" debate kept getting re-argued
  after it was already disproven live. That's re-litigating a closed
  question, not de-risking.
- Zero app code after 3 of 16 days is the real tell: spike infrastructure
  was optimized for rigor, not for unblocking a build.

**Verdict:** stop spiking tonight. Everything still open is cheap and
gated — prove it in one short morning session, then build for real.

## 2. Hard Scope — IN / OUT / FAKE

| # | Feature | Status | Notes |
|---|---|---|---|
| IN | Streaming STT rep transcript (always-on) | Build | Reuse `spikes/two_path` pattern; 24 kHz mandatory |
| IN | Gemini claim-check per sentence | Build | Reuse `spikes/claim_check/claim_check.py` as-is; 78.6% recall already proven offline |
| IN | Spoken alert quoting literal clause | Build | Reuse `spikes/chain/spike_chain.py` + `alert_agent.py`; core wow factor, never cut |
| IN | PDF upload → clause list | Build | Simple heuristic splitter (numbered headings); fall back to `spikes/harness/fake_contract.pdf/.json` if live parsing is flaky on demo day — **[FAKE-OK]** |
| IN | End-of-call compliance report | Build, simplify | List of clauses referenced + contradictions caught; no PDF export, plain HTML/JSON |
| IN | Consent step | **[FAKE-OK]** | One checkbox/screen before recording starts — compliance optics, not enforcement |
| CONDITIONAL | Monitor voice Q&A ("what does clause 4.2 say") | Build only after live probe passes | Tool-call round-trip never validly tested; **[FAKE-OK fallback]**: text input box that hits the same clause-lookup function if voice tool call doesn't hold up by Sep 24 |
| OUT | Speaker diarization | Cut | Not in ADR's chosen path; STT connection is rep-only by design (separate monitor mic/text) |
| OUT | Multi-contract / account system / auth | Cut | Single hardcoded demo session |
| OUT | Persistent storage / DB | Cut | In-memory per session is enough for one recorded demo |
| OUT | Re-measuring keyterms WER benefit | Cut | Already free evidence (T1 passed); not worth more session time |
| OUT | Any further ADR/probe-spec writing | Cut, effective now | One gating session tomorrow, then no more architecture documents |

## 3. Day-by-Day Plan, Sep 15 → Sep 30

| Date | Focus | Hours |
|---|---|---|
| Sep 15 (Mon) | **AM: the one gating live session** — tool-call round-trip at 24 kHz + reactive Voice Agent cold-open latency (~$0.30 total, ADR's own probe table). PM: FastAPI skeleton, routes, local run. | 1.5 + 4 |
| Sep 16 (Tue) | PDF→clauses extraction (pdfplumber + heuristic split), test against `fake_contract.pdf` | 6 |
| Sep 17 (Wed) | Browser mic → websocket → Streaming STT, live transcript rendered client-side | 6 |
| Sep 18 (Thu) | Port `claim_check.py` into server as per-sentence callback; get real Gemini free-tier key (none yet) | 5 |
| Sep 19 (Fri) | Wire reactive Voice Agent alert path; fix role defect (use proven `"user"`, not `"system"`) | 6 |
| Sep 20 (Sat) | Monitor Q&A: fix tool param-name mismatch; wire text-input fallback in parallel | 5 |
| Sep 21 (Sun) | Full chain integration smoke test (mic→STT→check→spoken alert). **CHECKPOINT 1** | 5 |
| Sep 22 (Mon) | End-of-call report | 4 |
| Sep 23 (Tue) | UI polish: upload/consent/session/alert-banner/report screens | 5 |
| Sep 24 (Wed) | Deploy to free host with websockets (see below); fix prod CORS/env. **CHECKPOINT 2 / CUT LINE** | 5 |
| Sep 25 (Thu) | Bug bash on the deployed URL; full rehearsal of the 174s/7-beat demo script live | 5 |
| Sep 26 (Fri) | Record demo takes, rough edit, upload to Vimeo (unlisted, "Anyone") | 4 |
| Sep 27 (Sat) | Slides | 3 |
| Sep 28 (Sun) | Public GitHub cleanup (README, `.env.example`, secret scan), final QA on hosted URL | 4 |
| Sep 29 (Mon) | Submission form + buffer | 3 + 3 |
| Sep 30 (Tue) AM | Wake hosted app from sleep, final confirm, submit before 11:00 AM | 1 |

**Free hosts that hold websockets, $0, no card required:** Render.com free
Web Service (cold-start sleep after 15 min idle — wake it 10 min before
judging/recording) or Hugging Face Spaces with the Docker SDK (FastAPI +
websockets both work, no card). Avoid Vercel/Netlify serverless — no
persistent websocket support on their free tiers.

**Cut line — if behind by Sep 24 night (Checkpoint 2):**
1. Cut live-voice monitor Q&A → keep the text-input fallback only.
2. Cut the report down to a bare pass/fail clause list, no formatting.
3. If PDF parsing is still flaky, hardcode the demo to
   `spikes/harness/fake_contract.pdf` and keep the upload button cosmetic.
Never cut the spoken alert quoting the literal clause — that's the wow
factor and the only thing judges will remember.

## 4. Single most important thing tomorrow morning

Run the one remaining live probe (tool-call round-trip + reactive
Voice-Agent open latency, ≤$0.30, one session) **before 9 AM**, then close
`spikes/` for good and create `server/main.py`. No more ADRs, no more probe
specs — day 1 of 16 ends with FastAPI actually running.
