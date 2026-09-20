# ClauseCatcher truth audit

Audited 2026-09-17 against repo HEAD `a629536` (identical to `origin/main`, working tree clean).
Every verdict below is backed by code, a run log, a re-run test suite, or a provider page fetched today.

Method: pull each factual claim out of the listed files, then check it against primary evidence in this
repo (source, tests, measured logs) or the vendor's own page. Test counts were produced by running the
suites, not by reading the docs.

---

## Resolved since this audit (2026-09-20)

The audit's own wording was used for each fix; nothing below was re-argued, only applied.

| Row | Where it lived | What was done |
|---|---|---|
| 1, 2 | PDF p4/p9, pptx slide 4 and 9 | `~2 s` -> `~5 s`, caption now reads `(4-6.5 s, five alerts)` |
| 8 | PDF p9, pptx slide 9 | `~78 ms` -> `~0.2 s`, caption now reads `(78-890 ms)` |
| 9 | PDF p9 and p10, pptx slide 9 and 10 | `~$0.12` -> `~$0.15` and `$0.08-$0.15 API usage per call` |
| 17 | PDF p9 | similarity caption -> `agent transcript vs. clause text` |
| - | pptx slide 9 | `136 server tests passing` -> `151`; subtitle and run date now say runs, plural, 2026-09-15 to 2026-09-17 |
| 3, 4, 5, 6, 7 | `cover.html`, `SLIDES.md`, `DEMO_SCRIPT.md`, `README.md`, `LABLAB_SUBMISSION.md` | already corrected in commit `967bb25`; verified by grep on 2026-09-20 |

Mechanism: `python tools/fix_deck.py` (exact-paragraph replacements, each row annotated with the audit
row it satisfies, idempotent and `--check`-able), then a PowerPoint re-export to `ClauseCatcher.pdf`.
Verified by extracting the PDF text and by rendering slide 9 to PNG - the first attempt at row 8 made
the stat box break mid-word, which is why it reads `~0.2 s` rather than `~200 ms`.

Row 22 (the Voice Agent does generate the spoken utterance) is **not** fixed in the deck: slide 8 still
says the LLM never generates clause language. That is true of Gemini and not of the Voice Agent leg.

---

## Must fix before submitting (as written 2026-09-17 — rows 1, 2 and 7 are now closed; see "Resolved since this audit" above)

1. **The slide PDF and PPTX still carry the numbers we already retracted.** `ClauseCatcher.pdf` pages 4,
   9 and 10 (and the matching `slide4/9/10.xml` in the PPTX) say `~2 s`, `~78 ms` and `~$0.12`. The PDF
   is the file we upload to lablab. The README says 4 to 6 seconds and $0.08 to $0.15. A judge who
   reads both sees us contradict ourselves in the two documents we hand them.
2. **`cover.png` carries the same retracted numbers.** `cover.html` lines 64 and 66 still read `~2 s`
   and `~78 ms`, and `cover.png` was rendered from that file. The cover is the first thing on the
   project page.
3. **`~78 ms` is the best of eight measurements from one probe run.** The same run recorded 890 ms and
   4890 ms (`spikes/voice_agent/out/probe_gate_20260915T051527Z.json`). Presenting the minimum as the
   headline is the single most attackable number in the submission.
4. **"4 to 6 seconds" is contradicted by our own browser-mic log.** `tools/e2e_mic/out/run-live.json`
   puts the only alert at 6.49 s after the STT final, and `DEMO_NOTES.md` line 60 records a 6.2 s take.
   The honest range across all five logged alerts is about 4 to 6.5 s.
5. **"4.6 s" has no source anywhere in the repo.** README line 72 and LABLAB_SUBMISSION line 56 both
   quote it. The measured values on record are 6.2, 4.3, 5.6, 4.0 and 6.49.
6. **"A monitor's spoken clause question" is not what the app does.** The monitor picks a section from
   a dropdown (`frontend/src/components/cockpit/CommandBar.tsx` lines 45 to 61). Nothing about the
   question is spoken. Only the answer is.
7. **SLIDES.md line 84 still says "~2 s"**, and line 88 still says the browser-mic path is unfinished.
8. **CHECKLIST items 9, 10, 14 and the video row are all stale.** SLIDES.md says 136 tests, not 81; the
   repo is fully pushed; the mic path was verified; the video shipped.
9. **RISKS R-06 (line 147) and R-13 (line 279) repeat those same two stale facts.**
10. **Every measured number we cite lives in a gitignored directory.** `.gitignore` excludes `**/out/`,
    so `run-live.json` and the probe JSON are not in the public repo. A judge cannot check a single
    figure. Commit the two result files, or stop calling them verifiable.

---

## Test counts as re-run on 2026-09-17 (now 151 backend / 42 frontend, see the resolution table above)

| Suite | Command | Result |
|---|---|---|
| Backend | `python -m pytest server/tests -q`, with `ASSEMBLYAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY` and `CLAUSECATCHER_CLAIM_CHECK` unset | **136 passed**, 2 warnings, 21.3 s |
| Backend, as the README writes it | `python -m pytest server/ -q`, same clean env | **136 passed**, 21.7 s |
| Frontend | `cd frontend && npx vitest run` | **21 passed** in 4 files, 314 ms |

So "136 tests" was correct wherever it appeared **on 2026-09-17**. The demo-day fixes in `967bb25` added tests: the suites now report 151 backend and 42 frontend, and every doc was updated to match on 2026-09-20. "81 tests" appears in no current file: the two places
that claim it does (CHECKLIST line 25, RISKS line 279) are themselves wrong.

---

## Claim table

### Latency, cost and other measured numbers

| # | Claim | Location | Verdict | Evidence | Corrected wording |
|---|---|---|---|---|---|
| 1 | "§3.1 flagged in ~2 s" | `ClauseCatcher.pdf` p4 / `ClauseCatcher.pptx` slide4 | **WRONG** | Every logged alert is 4.0 s or slower: 5.6 / 4.0 (`DEMO_NOTES.md` 50-51), 6.2 / 4.3 (line 60), 6.49 (`run-live.json`, final at 6469 ms, alert at 12954 ms) | "§3.1 flagged in about 5 s" |
| 2 | "~2 s / sentence end to alert" | `ClauseCatcher.pdf` p9 / pptx slide9 | **WRONG** | As above | "4 to 6.5 s" |
| 3 | "~2 s" stat chip | `docs/submission/cover.html:64`, and `cover.png` rendered from it | **WRONG** | As above | "~5 s" |
| 4 | "Alerts ~2 seconds after the sentence" | `docs/submission/SLIDES.md:84` | **WRONG** | As above. DEMO_NOTES line 67 records this correction being made on the landing page but not here | "Alerts 4 to 6.5 s after the sentence, measured on five live alerts" |
| 5 | "The alert timing (~2 seconds from sentence to card)" | `docs/submission/DEMO_SCRIPT.md:10` | **WRONG** | As above. DEMO_NOTES line 65 says the voiceover was corrected; this recording note was missed | "The alert timing, about five seconds from sentence to card" |
| 6 | "Alerts arrived 4 to 6 seconds after the triggering sentence finished" | `README.md:72`, `LABLAB_SUBMISSION.md:56` | **WRONG** (range too narrow) | `run-live.json`: STT final 6469 ms, alert 12954 ms, so 6.49 s, and the script measures from the audio's sentence end, which is earlier still. `DEMO_NOTES.md:60`: 6.2 s | "Alerts arrived 4 to 6.5 s after the triggering sentence finished" |
| 7 | "4.6 s, 5.6 s and 4.0 s on separate alerts" | `README.md:72`, `LABLAB_SUBMISSION.md:56` | **UNSUPPORTED** | 5.6 and 4.0 are in `DEMO_NOTES.md:50-51`. "4.6" appears nowhere else in the repo. `grep -rn "4\.6"` over all docs, JSON and Python returns only these two sentences | "5.6 s and 4.0 s in the take that shipped, 6.2 s and 4.3 s in the first take, and 6.5 s in the browser-mic run" |
| 8 | "First voice audio came back about 78 ms after the speak request was sent" | `README.md:74`, PDF p9, pptx slide9, `cover.html:66` | **MISLEADING** (cherry-picked minimum) | `probe_gate_20260915T051527Z.json` warm run, all eight `first_audio_ms`: 156, 890, 203, **78**, 188, 203, 203, 4890. 78 is the fastest one. The browser-mic run's alert to first audio was 375 ms | "First voice audio arrived 78 to 890 ms after the speak request across seven probe steps, and 375 ms after the alert in the browser-mic run" |
| 9 | "~$0.12 / API usage, full demo call" | PDF p9 and p10, pptx slide9 and slide10 | **STALE** | Measured: $0.0755 (55 s), $0.1466 (first take), $0.1535 (1:52). README and the landing page already say $0.08 to $0.15 | "$0.08 to $0.15 of API usage per call" |
| 10 | "$0.0755 for a 55 s call" | `README.md:76`, `LABLAB_SUBMISSION.md:58` | **SUPPORTED** | `run-live.json` `session_ended.report.est_cost_usd = 0.07547…`, call 22:32:41 to 22:33:36 | no change |
| 11 | "$0.1535 for a 1:52 call" | `README.md:76`, `LABLAB_SUBMISSION.md:58` | **SUPPORTED** (single run, and the docs say so) | `DEMO_NOTES.md:57-58` | no change |
| 12 | The cost figure is "API usage" | README:76, PDF p9, p10 | **MISLEADING** | It is the app's own estimate, not a billed amount: `server/stt.py:44` uses a flat `COST_PER_HOUR_USD = 0.45` and `server/voice.py:43` a flat `4.50/3600`, both multiplied by wall-clock seconds. Gemini is not counted at all | "about $0.08 to $0.15 by the app's own cost estimate, which prices AssemblyAI at list rate by connection time and does not meter Gemini" |
| 13 | "alert->first voice audio at 375 ms" | `README.md:79`, `LABLAB_SUBMISSION.md:56` | **SUPPORTED** | `run-live.json`: alert `t_ms` 12954, first `agent_audio` `t_ms` 13329, difference 375 ms | no change |
| 14 | "passed 17 of 17 checks" | `README.md:79`, `LABLAB_SUBMISSION.md:60` | **SUPPORTED, with a caveat** | `run_mic_e2e.py` runs 17 `check()` calls on the live path (lines 234, 248, 266, 267, 272, 274, 285, 295, 299, 303, 311, 317, 319, 321, 332, 335, 338). Line 393 prints "checks not failing", so a skipped check would also count as passing; on the live path none are skipped | "passed all 17 of its live-path checks" |
| 15 | "136 server-side tests pass (`pytest server/`)" | `README.md:77`, `README.md:123`, `LABLAB_SUBMISSION.md:59`, PDF p9 | **SUPPORTED** | Re-run today: 136 passed both as `pytest server/tests` and `pytest server/` | no change |
| 16 | "Each figure above comes from a single run, so treat them as examples, not averages" | `README.md:79`, `LABLAB_SUBMISSION.md:60` | **SUPPORTED and good practice** | This is the right disclosure. It does not, however, excuse quoting the fastest of eight probe values as the headline (see #8) | no change |
| 17 | "The spoken alert matched the contract text exactly (similarity 1.0, flagged `literal_spoken: true` by the server's own check)" | `README.md:73`, `LABLAB_SUBMISSION.md:56`, PDF p9 | **MISLEADING** | `server/voice.py:200-219` grades against `agent_transcript`, which is the Voice Agent's own `transcript.agent` event, not a transcription of the audio that played. The audio was never independently checked | "the Voice Agent's own transcript of the reply matched the contract text exactly (similarity 1.0), which is the server's post-speech check" |
| 18 | "60% of lines on-contract" in the report | `DEMO_NOTES.md:43` | **UNVERIFIED** | `server/main.py:294-304` `_report()` returns no score field; the percentage is computed client side. Not wrong, just not backed by anything in this audit's scope | leave, or cite the frontend file that computes it |

### Architecture and safety claims

| # | Claim | Location | Verdict | Evidence | Corrected wording |
|---|---|---|---|---|---|
| 19 | "AssemblyAI Streaming STT v3" is used | `README.md:15,131`, PDF p1/p3/p6, `LABLAB_SUBMISSION.md:39` | **SUPPORTED** | `server/stt.py:42` `AAI_WS_URL = "wss://streaming.assemblyai.com/v3/ws"`, wired at `server/main.py:507` | no change |
| 20 | "AssemblyAI Voice Agent API" is used | same files | **SUPPORTED** | `server/voice.py:41` `WS_URL_BASE = "wss://agents.assemblyai.com/v1/ws"`, `reply.create` sent at `voice.py:467` | no change |
| 21 | "Clause text is always literal. Every clause the app can speak or display comes from the uploaded contract's own text, extracted once at upload time" | `README.md:63`, PDF p8, `SLIDES.md:71` | **SUPPORTED for displayed text** | `server/clauses.py` imports only `pdfplumber` and `re`, no model client. The alert payload sends `clause["literal_text"]` verbatim (`server/main.py:427,436`) | no change for the display half |
| 22 | "The LLM never generates clause language; it only picks which clause ID applies" | `README.md:63`, PDF p8, `SLIDES.md:71`, `LABLAB_SUBMISSION.md:46` | **MISLEADING as applied to speech** | True of Gemini (`claim_check.py:40-47` constrains the response to verdict, clause_id, confidence, and `main.py` never uses model text). Not true of the Voice Agent: its model produces the spoken utterance from a "say exactly" instruction (`voice.py:56,467`), and `voice.py:448-450` says outright that grading "runs after the audio already went out, so a low-similarity (injected/paraphrased) reply is only flagged, not stopped" | "Gemini never writes any text we show or speak: it returns a verdict and a clause ID. The clause on screen is the contract's literal text. The Voice Agent is told to read that exact text back word for word, and the server grades the reply against the source afterwards and flags it if it drifts" |
| 23 | "Nothing about the alert's wording passes through the LLM twice" | `README.md:17` | **WRONG** | The say-exactly string is sent to the Voice Agent's model as an instruction and that model emits the reply. That is a second model in the path | "The alert's wording is never rewritten by a model: Gemini picks the clause, the server supplies the contract's own words, and the Voice Agent is instructed to repeat them verbatim" |
| 24 | The spoken alert is the clause text | implied by `README.md:17`, `SLIDES.md:61`, PDF p6 | **INCOMPLETE** | `voice.py:222-223` speaks `"Contract alert: section {n} says: {literal_text}"`, and `voice.py:226-227` speaks `"Section {n}, {title}: {literal_text}"`. A framing sentence wraps the literal clause | "the Voice Agent reads a one-line frame plus the clause's literal text, word for word" |
| 25 | "Errors resolve to 'unclear,' never to an accusation" | `README.md:64`, PDF p8, `SLIDES.md:72`, `LABLAB_SUBMISSION.md:47` | **SUPPORTED** | Four independent guards: catch-all to unclear at `claim_check.py:203-208`; schema or type mismatch to unclear at `191-196`; clause_id not in the contract forces unclear at `193-196`; contradiction under 0.6 confidence downgrades at `197-198`. On the server side, `main.py:407-410` catches any checker failure and returns without alerting, and `main.py:413-416` only proceeds on verdict `contradiction` with a clause that resolves | no change |
| 26 | "each clause fires at most once per 20 seconds" | `README.md:65`, PDF p8, `LABLAB_SUBMISSION.md:48` | **SUPPORTED** | `main.py:48` `ALERT_DEDUPE_S = 20.0`; `main.py:418-422` keys the cooldown on `section`, so it is per clause, not global | no change |
| 27 | "A manager watching the call can ask about any clause by number" | `README.md:18`, `LABLAB_SUBMISSION.md:42` | **SUPPORTED but loosely worded** | `CommandBar.tsx:45-61` is a `<select>` of the contract's sections; picking one sends `{type:'ask', section_number}` (`useSession.ts:284`), and `main.py:444-453` looks the clause up and speaks it | "A manager watching the call can pick any clause from the rail and have it read aloud" |
| 28 | "A monitor's spoken clause question (§4.2) was answered correctly by voice" | `README.md:75` | **WRONG** | There is no speech input for questions. The only mic stream goes to Streaming STT for the rep transcript; `handle_ask` is reached only from the dropdown. `DEMO_NOTES.md:42` confirms: "Manager opens the command bar; 2:13 asks for §4.2" | "A monitor's clause request (§4.2), picked from the rail, was read back correctly by voice" |
| 29 | "A spoken question about clause §4.2 was answered correctly" | `LABLAB_SUBMISSION.md:57` | **WRONG** | Same as #28 | "A clause request for §4.2 was read back correctly by voice" |
| 30 | "A monitor's spoken question about §4.2 answered correctly by voice" | `ClauseCatcher.pdf` p9, pptx slide9 | **WRONG** | Same as #28 | "A monitor's §4.2 clause request, read back correctly by voice" |
| 31 | "There's no agent tool-calling round trip here, since that path proved unreliable in testing" | `README.md:18` | **SUPPORTED** | `voice.py:231-233` "Registers no tools". The probe recorded `warm_ask_wav` as verdict INVALID, similarity 0.0, first audio 4890 ms (`probe_gate_20260915T051527Z.json`) | no change |
| 32 | A single Voice Agent session "was tested live and found to talk over the rep on its own, even with a prompt telling it to stay silent" | `README.md:56`, PDF p6/p7, `SLIDES.md:53`, `LABLAB_SUBMISSION.md:51` | **SUPPORTED by our own record** | `docs/adr/0001-voice-architecture.md:4` and `:41-44`: P3 strong-prompt FAIL, "the agent auto-started 4 replies anyway (what it said was not recorded)". Note the ADR itself flags that the reply text was not captured, and the raw probe log is not committed | keep, but add "(one live session, N=1)" |
| 33 | "Auto-started 4 replies despite a silence prompt" | PDF p7, pptx slide7 | **SUPPORTED** | Same ADR record | no change |
| 34 | Injecting the alert as a conversation message "ignored the injected content entirely" | `README.md:57`, PDF p7, `SLIDES.md:64`, `LABLAB_SUBMISSION.md:51` | **SUPPORTED** | `probe_gate_20260915T051527Z.json`: `warm_speak_no_instructions` returned "Please provide the compliance alert or the contract clause section number you would like me to process", similarity 0.27; the cold run scored 0.179; the 800 ms delayed variant 0.258. All three graded FAIL | no change |
| 35 | "Only the direct instruction produces a spoken match to the source text" | `README.md:57`, `SLIDES.md:64` | **OVERSTATED** | The same probe shows `warm_speak_message_and_say_exactly` also scored similarity 1.0 with `literal_spoken: true`. What fails is injection *without* a say-exactly instruction. The instruction is necessary, but it is not the only configuration that includes one | "Only a direct say-exactly instruction produces a spoken match. Injecting the alert without one did not." |
| 36 | "seeded with keyterms pulled from the contract's own clauses, so section-specific language transcribes more reliably" | `README.md:15`, PDF p3/p5, `LABLAB_SUBMISSION.md:39`, `SLIDES.md:60` | **UNSUPPORTED effect** | The mechanism is real and wired (`stt.py:231` builds up to 100 terms, `main.py:507` passes them). The improvement is not measured anywhere, and `stt.py:221-224` says so itself: "regex heuristics, not NLP … upgrade to real NLP extraction if keyterm quality is ever measured directly" | "seeded with keyterms pulled from the contract's own clauses, which AssemblyAI documents as a recognition-accuracy hint. We did not measure the gain" |
| 37 | "Consent confirmed before listening. The call can't start until disclosure is checked" | PDF p5, pptx slide5 | **SUPPORTED in the UI only** | `frontend/src/components/setup/ConsentCard.tsx` gates the Start control. The server has no consent check: `/api/session/start` (`main.py:286`) accepts a session without one | "Consent is confirmed in the UI before the call can start" |
| 38 | "The browser mic streams PCM16 audio over a websocket … The spoken audio plays in the ClauseCatcher browser tab … ClauseCatcher doesn't connect to the calling platform" | `README.md:15,17`, `LABLAB_SUBMISSION.md:41` | **SUPPORTED** | `run_mic_e2e.py` check at line 267 confirms 3200-byte frames (1600 int16 at 16 kHz per 100 ms); agent audio returns as `agent_audio` WS messages; nothing in the repo touches a conferencing API | no change |
| 39 | "the session produces a report: every clause referenced, every contradiction caught, and basic call stats" | `README.md:19` | **SUPPORTED** | `main.py:294-304` returns referenced sections, contradictions, transcript count, timestamps, cost estimate, check counts and error counts | no change |

### Verification status claims

| # | Claim | Location | Verdict | Evidence | Corrected wording |
|---|---|---|---|---|---|
| 40 | "The browser-microphone path is verified: … an automated run drove a real browser (getUserMedia -> AudioWorklet -> 16 kHz PCM16 frames)" | `README.md:79`, `LABLAB_SUBMISSION.md:60` | **SUPPORTED but overstated** | `run_mic_e2e.py:206-215` launches Chromium with `--use-fake-device-for-media-stream` and `--use-file-for-fake-audio-capture`. The browser, getUserMedia, the worklet and the frame path are all real; the microphone is a synthetic capture device. No physical mic was used | "verified in a real browser end to end, with a synthetic capture device standing in for the microphone (Chromium's fake audio device playing a WAV into getUserMedia). Untested on physical mic hardware" |
| 41 | "The browser-microphone path and a hosted deployment are still being finished; we're not claiming those yet" | `SLIDES.md:88` | **STALE** | Contradicted by `README.md:79` and `run-live.json` | "The browser-mic path is verified end to end with a synthetic capture device. A hosted deployment is not up yet, and we claim nothing for one" |
| 42 | "the mic path has **not yet been verified end to end on real hardware**" | `docs/submission/RISKS.md:147` | **STALE for the pipeline, still true for hardware** | Same as #40 | "the mic path is verified end to end in a real browser with a synthetic capture device, and remains untested on physical mic hardware" |
| 43 | "NEXT: Browser-mic path, hardened end to end" | PDF p10, pptx slide10, `SLIDES.md:96` | **STALE** | Same as #40. "Hardened" is defensible, "browser-mic path" as a to-do is not | "NEXT: browser-mic path on real hardware" |
| 44 | Checklist item 14: "Browser-mic live path verified end to end / **pending** / Not verified yet. Every submission text says so." | `docs/submission/CHECKLIST.md:30` | **WRONG** | `README.md:79` and `LABLAB_SUBMISSION.md:60` both claim it as verified. The sentence is self-contradicting as written | "done: verified 2026-09-17 in a real browser with a synthetic capture device (`tools/e2e_mic/run_mic_e2e.py`, 17/17 live checks). Physical mic hardware is still untested." |
| 45 | Checklist item 9: "The older outline `SLIDES.md` still says 81, which is harmless but stale." | `docs/submission/CHECKLIST.md:25` | **WRONG** | `SLIDES.md:86` says "136 backend tests passing". The string "81 tests" appears nowhere in the repo | "`SLIDES.md` and the PDF both say 136 tests, which matches the suite." |
| 46 | R-13: "`SLIDES.md` still says 81 tests where the PDF says 136" | `docs/submission/RISKS.md:279` | **WRONG** | Same as #45 | delete the sentence |
| 47 | Checklist item 10: "done, but local work isn't pushed … uncommitted changes in `server/main.py`, `server/tests/test_session_flow.py` and `frontend/src/hooks/useSession.ts`" | `docs/submission/CHECKLIST.md:26` | **STALE** | `git rev-parse HEAD origin/main` returns the same SHA `a629536`; `git status --porcelain` on those three files is empty | "done: everything is pushed, `origin/main` is at `a629536`." |
| 48 | R-13: "Several submission-critical files were still unpushed when `CHECKLIST.md` item 10 was written" | `docs/submission/RISKS.md:269-272` | **STALE** | Same as #47 | "Everything is pushed as of `a629536`. Confirm the README images render in a logged-out browser." |
| 49 | Checklist item 8: video "pending / Record from `DEMO_SCRIPT.md`" | `docs/submission/CHECKLIST.md:24` | **STALE** | `docs/submission/demo.mp4` exists and `DEMO_NOTES.md` documents the shipped 2:54 take. Commit `a629536` is titled "Ship demo video" | "recorded: `docs/submission/demo.mp4`, 2:54. Still to do: upload to Vimeo and paste the link." |
| 50 | "Status: in development." | `README.md:5` | **STALE for a submission** | The app runs end to end, the deck and video are done, the tests pass | "Built for the lablab.ai AssemblyAI Voice Agent Hackathon (deadline Sep 30 2026)." |
| 51 | "Demo video: TODO (Vimeo)" / "Live app: TODO" | `README.md:140-141` | **TRUE but costly** | Both are genuinely outstanding. They are also the first two lines a judge reads at the bottom of a public README | fill both before submitting, or drop the Links section until they exist |
| 52 | "Not yet verified: a deployed hosted instance. Nothing above is claimed for one." | `README.md:81`, `LABLAB_SUBMISSION.md:62` | **SUPPORTED and honest** | No deployment exists (R-02, `RISKS.md:51`); LABLAB_SUBMISSION still has `[APP_URL]` | no change |
| 53 | "`URL=https://clausecatcher.onrender.com`" | `docs/submission/CHECKLIST.md:50` | **UNSUPPORTED** | Nothing is deployed; this hostname has never existed for us. It is presented as the URL to check, not as a placeholder | "`URL=<your Render URL>`" |
| 54 | "the Render image was built from the repo `Dockerfile` and run locally under `--memory 512m` … driven through the real UI with Playwright" | `docs/submission/RISKS.md:16-20` | **NOT VERIFIED HERE** | Docker was not run in this audit (out of scope, and the run logs are under a gitignored path). The claim is plausible but unverifiable from the repo as published | leave, but commit the container run log if a judge is meant to check it |

### External facts: models, pricing, platforms

| # | Claim | Location | Verdict | Evidence | Corrected wording |
|---|---|---|---|---|---|
| 55 | Claim-check model is `gemini-3.5-flash-lite` | `README.md:16,106,132`, `LABLAB_SUBMISSION.md:40` | **SUPPORTED** | `ai.google.dev/gemini-api/docs/models` fetched 2026-09-17 lists `gemini-3.5-flash-lite` as Stable, "Our fastest, most cost-effective 3.5 model". Code default at `claim_check.py:33` | no change |
| 56 | `gemini-3.5-flash-lite` is on the "free tier" | `README.md:16,132`, `LABLAB_SUBMISSION.md:40` | **PARTLY VERIFIED** | The model page confirms the model. The free-tier quota for this specific ID was not confirmed on a rate-limits page in this audit. `claim_check.py:15-17` records a measured free-tier finding for full "flash" models, not for this one | "Gemini `gemini-3.5-flash-lite`, run on a free-tier key" |
| 57 | AssemblyAI Streaming at $0.45/hr | `server/stt.py:44`, `docs/adr/0001-voice-architecture.md:124` | **SUPPORTED** | `assemblyai.com/pricing` fetched 2026-09-17: "Universal-3.5 Pro Realtime: $0.45/hr base". `stt.py:43` sets `DEFAULT_SPEECH_MODEL = "universal-3-5-pro"`, so the rate matches the model we actually request | no change |
| 58 | "Streaming $0.15/hr to $0.45/hr" | `docs/adr/0001-voice-architecture.md:124` | **SUPPORTED** | Same page: Universal-Streaming English and Multilingual both $0.15/hr | no change |
| 59 | Voice Agent at "$4.50/hr = $0.075/min" | `docs/adr/0001-voice-architecture.md:123,131`, `server/voice.py:43` | **SUPPORTED** | Same page: "Voice Agent API $4.50/hr ($0.075/min)" | no change |
| 60 | "5 winners · $1,000 cash + $1,000 in API credits each" | `docs/submission/CHECKLIST.md:9` | **CONSISTENT** | The event page renders "$10,000 Prize Pool ($5k cash + $5k in AAI credits)", which matches 5 × ($1k + $1k). The per-winner split was not visible in the fetched render | no change |
| 61 | Deadline "Wed Sep 30 2026, 11:00 AM EDT (endAt 2026-09-30T15:00:00.000Z)" | `LABLAB_SUBMISSION.md:6`, `CHECKLIST.md:3` | **UNVERIFIED externally, internally consistent** | The event page renders only "Sep 1-30, 2026" with no time. 15:00 UTC is 11:00 EDT, so the two halves of the claim agree | leave, and re-check the countdown on the logged-in dashboard |
| 62 | Field limits: 255-char short description, 100-word minimum long description, max 5-minute MP4, PDF slides, 16:9 cover | `LABLAB_SUBMISSION.md:20,28,88,96,100`, `CHECKLIST.md:20-25` | **UNVERIFIED externally** | `lablab.ai/delivering-your-hackathon-solution` returned only the site header when fetched; the guidance is JavaScript-rendered | re-check while logged in before submitting |
| 63 | HF Spaces Docker requires a paid plan; Fly.io requires a card; Render free tier sleeps after 15 min and wakes in about a minute | `docs/DEPLOY.md:7-28`, `RISKS.md:28-29` | **NOT RE-VERIFIED** | Each is quoted with a URL and a fetch date of 2026-09-16, which is good practice. Out of scope for this pass | leave |

### Documentation consistency

| # | Claim | Location | Verdict | Evidence | Corrected wording |
|---|---|---|---|---|---|
| 64 | ADR-0001 records the accepted architecture as "Voice Agent opened for alerts (`conversation.message`+`reply.create`) and monitor Q&A + tool" | `docs/adr/0001-voice-architecture.md:65` | **STALE** | The shipped design is the opposite: `voice.py:6-9` "no `conversation.message`", `voice.py:231-233` "Registers no tools". README line 54 points judges at this ADR as "the core architecture decision", and README line 57 then contradicts it | Add a dated amendment to the ADR: "Amended 2026-09-15: the accepted option ships without `conversation.message` and without tools. Probe `probe_gate_20260915T051527Z.json` showed message injection alone produced similarity 0.18 to 0.27, and the monitor tool round trip came back INVALID at 4890 ms. Alerts and clause answers both use `reply.create` with a say-exactly instruction." |
| 65 | "Built solo for this hackathon in 16 days" | `docs/submission/SLIDES.md:97` | **UNSUPPORTED** | `git log --reverse`: first commit 2026-09-14, latest 2026-09-17, 11 commits. The ADR is dated 2026-09-13. That is 4 to 5 days of work, not 16. 16 is the length of the submission window | "Built solo, in the week before submission" |
| 66 | "Built solo for the AssemblyAI Voice Agent Hackathon" | PDF p10, pptx slide10 | **SUPPORTED** | Single author across all 11 commits | no change |
| 67 | "Everything on screen is a real run … Nothing is simulated, staged, or re-timed" | `docs/submission/DEMO_NOTES.md:9,13` | **SUPPORTED, worth one caveat** | The take was produced by `record.py --server live --i-mean-live` against real upstreams, and DEMO_NOTES lines 100-102 openly disclose the 1.65 s audio/video offset correction. "Not re-timed" is slightly strong given that disclosed A/V shift | "Nothing is simulated or staged. The only edit is a 1.65 s audio/video sync correction, described below." |
| 68 | "Its slide 9 already says 136 tests" | `docs/submission/CHECKLIST.md:25`, `LABLAB_SUBMISSION.md:100` | **SUPPORTED** | PDF page 9 reads "136 server tests passing" | no change |
| 69 | "cover.png: 1920 x 1080 PNG (16:9), about 0.6 MB" | `LABLAB_SUBMISSION.md:88` | **NOT VERIFIED** | Dimensions were not measured in this pass. The stale stat chips in it (#3, #8) matter more | re-render the cover after fixing `cover.html` |
| 70 | "The demo contract has four clauses (§3.1 pricing, …)" | `docs/submission/RISKS.md:130` | **CONSISTENT** | DEMO_NOTES line 33 says "4 clauses quoted from the PDF"; §3.1, §4.2, §5.3 and §6.1 all appear across the logs | no change |
| 71 | "Every finalized sentence over 3 words is one Gemini call" | `docs/submission/RISKS.md:166` | **SUPPORTED** | `main.py:398`: skips when `len(sentence.split()) < MIN_CLAIM_CHECK_WORDS` or the per-session cap is hit | no change |
| 72 | "sentences are truncated to 400 chars, and there is a 12 s call timeout under a 15 s outer timeout" | `docs/submission/RISKS.md:175-176` | **SUPPORTED** | `main.py:49` `CLAIM_CHECK_TIMEOUT_S = 15.0`, comment cites `claim_check.TIMEOUT_MS` at 12 s; `main.py:397` truncates to `MAX_SENTENCE_CHARS` | no change |

---

## What I could not verify

- **lablab's own field limits and the exact deadline time.** Both pages are JavaScript-rendered and came
  back as a bare header. Re-check them from a logged-in session.
- **The container claims in RISKS.md** (373 MB image, 46 s no-cache build, 54 MB idle, security headers on
  the live container). Docker was not run here, and the evidence is not in the repo.
- **Free-tier quota specifically for `gemini-3.5-flash-lite`.** The model page confirms the ID and its
  Stable status; it does not state the free-tier request limit, and no rate-limits page was fetched.
- **`cover.png` pixel dimensions and file size.** Not measured.
- **The 4 auto-replies from the one-session probe.** Only the ADR's summary survives. The ADR itself
  notes "what it said was not recorded", and the raw log is not committed.
- **The report's "60% of lines on-contract" figure.** Computed in the frontend, outside the file list I
  was asked to audit.
- **Anything about a hosted instance.** Nothing is deployed, and the docs correctly say so.

## A structural problem worth fixing once

`.gitignore` line 21 excludes `**/out/`. That directory holds every number this submission rests on:
`tools/e2e_mic/out/run-live.json`, `spikes/voice_agent/out/probe_gate_*.json`, and the claim-check
evals. A judge who clones the repo gets the claims and none of the evidence. Either commit those three
result files under a tracked path such as `docs/evidence/`, or soften every "measured" line to "measured
locally, logs not published". The first option is a few kilobytes and makes the whole Measured Results
section checkable.
