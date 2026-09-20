# ClauseCatcher: slide deck outline

9 slides, built for a 3-minute pitch alongside the demo video. Exact on-slide text plus speaker notes for each.

---

## Slide 1: Title / hook

**On slide:**
> ClauseCatcher
> Your sales reps go off-script. Your contract doesn't.

**Speaker notes:** Open with this line cold, no "hi we're team X." A rep on a live call can promise something the contract doesn't allow, and right now nobody catches it until the call is long over.

---

## Slide 2: The problem

**On slide:**
- A rep's verbal promise and the signed contract can disagree
- Nobody is listening for the gap in real time
- By the time it surfaces, it's a dispute, not a correction

**Speaker notes:** This isn't a hypothetical: a 10 percent discount a rep isn't authorized to offer, or a service-hours claim the contract doesn't back up, becomes the customer's expectation the second it's said out loud. Fixing it after the call means legal, not a sentence.

---

## Slide 3: The solution

**On slide:**
> ClauseCatcher listens to the call, checks every sentence against the signed contract, and speaks the exact clause back the moment something doesn't match.

**Speaker notes:** Three parts: always-on transcription, a per-sentence contradiction check against the contract, and a spoken correction using the contract's own words, not a summary of them.

---

## Slide 4: Live demo

**On slide:** (no bullets, full-screen video or live app)

**Speaker notes:** Play roughly 1:00-1:35 of the demo video here: the rep offers an unauthorized discount, ClauseCatcher flags §3.1 within about five seconds, and the AssemblyAI Voice Agent speaks the clause back word for word. Let the audio play without talking over it.

---

## Slide 5: Architecture

**On slide:**
- Rep audio → AssemblyAI Streaming STT v3 (always-on transcript)
- Each sentence → Gemini claim-check against the contract
- Contradiction → AssemblyAI Voice Agent speaks the literal clause
- Two separate connections, one job each

**Speaker notes:** We tried one AssemblyAI Voice Agent session doing both listening and speaking first. Tested live, it started replying over the rep on its own, even with an explicit silence instruction. Splitting transcription and speaking into two connections removed that failure mode instead of prompting around it. That decision is written up in the repo's ADR.

---

## Slide 6: Why AssemblyAI, specifically

**On slide:**
- Streaming STT v3: keyterms from the contract, which AssemblyAI documents as a recognition hint (we did not measure the gain)
- Voice Agent API: `reply.create` with a "say this exactly" instruction, not generated speech
- The verbatim check only passes because of that instruction

**Speaker notes:** We first tried injecting the alert as a fake conversation message and asking the agent to react to it. It ignored the content and asked us to provide the alert again. Instructing the agent directly to say a fixed string, word for word, is what actually produces a verbatim match. That's not a guess; we tested both and only one works.

---

## Slide 7: Safety by design

**On slide:**
- Clause text is always the contract's literal words, never generated
- A failed or unclear check never becomes an accusation
- Every alert cites a specific clause ID, not a vibe

**Speaker notes:** A tool that puts words in a rep's mouth, or falsely accuses them, is worse than one that occasionally misses something. So the LLM's only job is picking which clause applies; it never writes what gets said or shown.

---

## Slide 8: Measured results

**On slide:**
- Live runs, real AssemblyAI + Gemini connections, Sep 15 and Sep 17 2026
- Two false claims caught (§3.1, §6.1); consistent lines raised nothing
- Alerts 4 to 6.5 s after the sentence, across five logged alerts; the agent's own transcript verified word for word against the clause
- Alert to first spoken word: 375 ms
- $0.08 to $0.15 per call by the app's own estimate; 136 backend tests passing
- Browser-mic path verified end to end, 17 of 17 automated checks (Sep 17 2026)

**Speaker notes:** These are numbers from real end-to-end runs, not projections, and the logs are in the repo under docs/evidence. Say the caveats once, plainly: each figure is a single run rather than an average, the browser-mic run used Chromium's fake capture device instead of a physical microphone, and there is no hosted deployment yet, so nothing here is claimed for one.

---

## Slide 9: Who this is for, and what's next

**On slide:**
- Buyer: sales-ops and compliance teams monitoring live calls
- Next: the mic path on physical hardware, deployment, multi-contract support
- Built solo, Sep 14 to 17 2026 (11 commits)

**Speaker notes:** The team is one builder. The near-term roadmap is the parts the demo doesn't yet cover: the mic path on physical hardware rather than a synthetic capture device, and a deployed instance instead of a local one. Close on the product line: the correction a rep hears is the contract's own words, spoken back to them, while the call is still happening.
