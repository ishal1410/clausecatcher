# ClauseCatcher: slide deck outline

11 slides, built for a 3-minute pitch alongside the demo video. The "on slide" blocks are the deck's
actual text, page for page with `ClauseCatcher.pdf`; the speaker notes are what to say over them.

---

## Slide 1: Title / hook

**On slide:**
> CLAUSECATCHER
> Your reps go off-script. Your contract doesn't.
> ClauseCatcher listens to live sales calls, catches any line that contradicts the signed contract, and reads the exact clause aloud while the customer is still on the line.
>
> `AssemblyAI Streaming STT v3` · `AssemblyAI Voice Agent` · github.com/ishal1410/clausecatcher

**Speaker notes:** Open with the hook line cold, no "hi we're team X." A rep on a live call can promise something the contract doesn't allow, and right now nobody catches it until the call is long over.

---

## Slide 2: The problem — "A promise said out loud becomes the deal"

**On slide:**
> REP SAID, ON THE CALL: "If you sign this week, we can do a verbal discount on the extra seats."
> SIGNED CONTRACT §3.1 SAYS: "Flat $48,000 up to 50 seats; extra seats need signed written amendment; no automatic or verbal discounting."

- Nobody checks the call live
- The gap surfaces after signing
- Then it's a dispute, not a correction

**Speaker notes:** This isn't hypothetical: a discount a rep isn't authorized to offer, or a service-hours claim the contract doesn't back up, becomes the customer's expectation the second it's said out loud. Fixing it after the call means legal, not a sentence.

---

## Slide 3: The solution — "Listen. Check. Speak the clause."

**On slide:**
- 01 LISTEN — AssemblyAI Streaming STT v3: always-on transcript of the rep, seeded with keyterms from the contract
- 02 CHECK — Gemini claim-check: each finished sentence is checked; the model returns a verdict and a clause ID, never text
- 03 SPEAK — AssemblyAI Voice Agent: reads the contract's literal clause aloud, and the cockpit shows the alert card

**Speaker notes:** Three parts: always-on transcription, a per-sentence contradiction check against the contract, and a spoken correction using the contract's own words, not a summary of them.

---

## Slide 4: Live demo — "Caught mid-call. Spoken back word for word."

**On slide:**
- Rep offers a verbal discount
- §3.1 flagged in ~5 s
- Voice Agent reads §3.1 aloud
- Marked spoken verbatim

**Speaker notes:** Play roughly 1:00-1:35 of the demo video here: the rep offers an unauthorized discount, ClauseCatcher flags §3.1 within about five seconds, and the AssemblyAI Voice Agent speaks the clause back word for word. Let the audio play without talking over it.

---

## Slide 5: Before the call — "Upload the contract. Every clause, quoted exactly."

**On slide:**
- Clauses extracted once, at upload — the words on screen are the words in the PDF
- Clause language seeds STT keyterms — contract-specific terms transcribe more reliably
- Consent confirmed before listening — the call can't start until disclosure is checked

**Speaker notes:** Clause extraction is `pdfplumber` plus a regex, no model, which is why the clause text can be promised to be literal. The keyterm seeding is AssemblyAI's documented recognition hint; we did not measure the gain, so don't claim one. Consent is a hard gate, not a checkbox we log.

---

## Slide 6: Architecture — "Two AssemblyAI connections, one job each"

**On slide:**
> Rep mic (PCM16 audio) → AssemblyAI Streaming STT v3 (listens, never replies) → Gemini check (returns clause ID only) → FastAPI server (looks up literal text) → AssemblyAI Voice Agent (`reply.create`, say exactly)
>
> Signed contract clauses: the only source of spoken words
>
> *Footnote:* Why split? One Voice Agent session doing both jobs was tested live and started replying over the rep, even with a silence prompt. Streaming STT has no reply behavior, so silence is structural, not prompted. (ADR-0001)

**Speaker notes:** We tried one AssemblyAI Voice Agent session doing both listening and speaking first. Tested live, it started replying over the rep on its own, even with an explicit silence instruction. Splitting transcription and speaking into two connections removed that failure mode instead of prompting around it. That decision is written up in the repo's ADR.

---

## Slide 7: Why AssemblyAI, specifically — "We tested the easy paths. Both failed."

**On slide:**
- TRIED AND DROPPED — one Voice Agent session for everything: auto-started 4 replies despite a silence prompt
- TRIED AND DROPPED — alert injected as a fake user message: agent ignored the injected content
- SHIPPED — Streaming STT v3 listens all call: pure transcription, nothing to talk over
- SHIPPED — Voice Agent `reply.create`, "say exactly": spoken alert matched the clause, similarity 1.0
- *Footnote:* Both products are load-bearing. Cut Streaming STT and there is no transcript to check. Cut the Voice Agent and the alert is a silent card instead of an interruption the rep hears.

**Speaker notes:** We first tried injecting the alert as a fake conversation message and asking the agent to react to it. It ignored the content and asked us to provide the alert again. Instructing the agent directly to say a fixed string, word for word, is what actually produces a verbatim match. That's not a guess; we tested both and only one works. The two dead ends aren't padding — they're why the architecture looks the way it does.

---

## Slide 8: Safety by design — "It never puts words in a rep's mouth"

**On slide:**
- Literal clause text only — the words are the contract's own. Gemini picks the clause ID; the Voice Agent is told to say it verbatim.
- Errors ≠ accusations — a failed, timed-out or unparseable check resolves to "unclear", never a contradiction
- Evidence, or no alert — every alert cites a specific clause ID; each clause fires at most once per 20 seconds
- *Footnote:* A false accusation is worse than a missed one. The read-back is graded against the clause after it is spoken: drift is flagged, not blocked.

**Speaker notes:** Be precise about which model does what, because the two legs differ. Gemini is constrained to a verdict plus a clause ID — it never writes displayed text. The Voice Agent's model does produce the spoken audio, from a "say exactly this" instruction; the server then compares what it said against the clause and flags any drift. That check runs after the audio has gone out, so it flags rather than blocks, and the deck says so rather than implying a guarantee we don't have.

---

## Slide 9: Measured, not projected — "Live end-to-end runs, real connections"

**On slide:**
- ~5 s — sentence end to alert (4–6.5 s, five alerts)
- 1.0 — agent transcript vs. clause text
- ~0.2 s — speak request to first audio (78–890 ms)
- ~$0.15 — API usage, full call ($0.08–$0.15)
- False claims on §3.1 and §6.1 both caught; consistent lines raised nothing
- A monitor's clause request for §4.2, picked from the rail, answered by voice
- 14/14 contradictions caught, 0 false alarms; 151 server tests passing
- *Footnote:* Runs of 2026-09-15 to 2026-09-17: real AssemblyAI Streaming STT, Voice Agent and Gemini connections, scripted rep lines fed through the pipeline.

**Speaker notes:** These are numbers from real end-to-end runs, not projections, and the logs are in the repo under docs/evidence. Say the caveats once, plainly: the figures come from a handful of runs rather than a large sample, the browser-mic run used Chromium's fake capture device instead of a physical microphone, and the figures come from local runs rather than the hosted instance at https://clausecatcher.onrender.com.

---

## Slide 10: The market, sized bottom-up — "The category, and the slice we can name"

**On slide:**
- $1.6B–$32B — 2026 conversation-intelligence estimates
- 1.59M — US wholesale & manufacturing reps (BLS 2025)
- $0.6B–$1.1B — those reps at a $30–60 per-seat hypothesis
- 292k — technical & scientific reps: the beachhead
- Each firm draws the category differently — the spread is the honest number, not the top of it
- Beachhead: the 292,000 technical and scientific reps, who sell the hardest contracts
- $30–60 per seat per month is our hypothesis — no buyer has been asked to pay it yet
- *Footnote:* 1.59M = 1.3M except-technical-and-scientific + 292k technical and scientific, BLS Occupational Outlook Handbook 2025 employment (bls.gov/ooh). $0.6B–$1.1B = 1.59M × $30–60 × 12.

**Speaker notes:** Lead with the spread and say why it's a spread: published 2026 estimates for conversation-intelligence software range from about $1.6B to about $32B because every firm draws the category boundary somewhere different, and quoting only the top of that range would be choosing the flattering number. So size it bottom-up instead: BLS counts 1.59 million US wholesale and manufacturing sales reps, which at a $30–60 per-seat-per-month hypothesis is $0.6B–$1.1B a year. Say the word "hypothesis" out loud — that price has not been tested with a buyer. The beachhead is the 292,000 technical and scientific reps, because they sell the contracts with the most clauses to contradict. Same four numbers as the video's market card, so the deck and the video agree.

---

## Slide 11: Who it's for, and what's next

**On slide:**
- BUILT FOR — sales-ops teams running live calls; compliance teams who own the contract; $0.08–$0.15 API usage per call
- NEXT — physical-mic hardware (browser path verified 17/17); multiple contracts per call; CRM and meeting-platform audio
- The correction a rep hears is the contract itself, spoken while the call is still happening.
- github.com/ishal1410/clausecatcher · Built solo for the AssemblyAI Voice Agent Hackathon

**Speaker notes:** The team is one builder, working Sep 14 to 20 2026. The near-term roadmap is the parts the demo doesn't yet cover: the mic path on physical hardware rather than a synthetic capture device, and a deployed instance instead of a local one. Close on the product line: the correction a rep hears is the contract's own words, spoken back to them, while the call is still happening.
