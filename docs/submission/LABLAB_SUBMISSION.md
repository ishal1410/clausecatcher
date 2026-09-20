# lablab.ai submission: ClauseCatcher

Copy-paste content for the lablab.ai submission form, field by field, in the order the event page lists them.

- Event: AssemblyAI - Voice Agent Hackathon, https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon
- Deadline: **Wed Sep 30 2026, 11:00 AM EDT** (event data `endAt: 2026-09-30T15:00:00.000Z`)
- Field list: event page, "What to submit". Field limits: https://lablab.ai/delivering-your-hackathon-solution
- No placeholders remain. The application URL and the video link are both filled in and verified (the video returns HTTP 200 logged out; oEmbed reports 261 s).

---

## 1. Basic information

### Project title

```
ClauseCatcher
```

### Short description (limit: 255 characters)

```
A voice agent for live sales calls. When a rep promises something the signed contract doesn't allow, it reads the exact clause back out loud seconds later. It quotes the contract word for word and never makes up legal wording.
```

(226 characters.)

### Long description (minimum: 100 words)

```
IN ONE LINE
When a sales rep promises something the contract doesn't allow, ClauseCatcher reads the rep the actual clause out loud, word for word, seconds later, while the customer is still on the line.

THE PROBLEM
Sales reps improvise on live calls. One sentence ("we can do a verbal discount on the extra seats") can promise something the signed contract forbids. Nobody catches it while the call is happening, so it turns up weeks later as a customer dispute instead of a one-sentence correction. Today, compliance and sales-ops teams catch this, if they catch it at all, by spot-checking recordings after the fact.

WHAT CLAUSECATCHER DOES
ClauseCatcher runs in a browser tab next to the call. Upload the contract PDF and it pulls out every clause once, word for word. During the call:
1. Listen: the rep's microphone audio streams to AssemblyAI Streaming STT v3. The session is seeded with keyterms taken from the contract, which AssemblyAI documents as a recognition-accuracy hint; we wired it up but did not measure the gain.
2. Check: each finished sentence goes to Gemini (free tier) with the clauses attached. Gemini returns only a verdict and a clause ID. It never writes any text that gets shown or spoken.
3. Alert: when a sentence contradicts a clause, an alert card appears with the offending phrase underlined. The AssemblyAI Voice Agent API then speaks the literal clause, using a direct "say this exactly, word for word" instruction. The audio plays in the ClauseCatcher tab, through the rep's own headset or speakers. ClauseCatcher doesn't connect to the calling platform, so it doesn't inject anything into the call itself.
4. Answer: a manager on the call picks any clause by number from the cockpit rail and hears it read back the same verbatim way.
5. Report: when the call ends, the report lists every clause referenced and every contradiction caught.

WHY IT CAN BE TRUSTED
- Clause text is quoted, never generated. Gemini only picks a clause ID. The Voice Agent is told to read that exact text back word for word, and the server grades its reply against the source afterwards and flags any drift — a check after the fact, not a guarantee.
- If a check fails, times out or can't be parsed, the sentence is marked "unclear", never "contradiction". Falsely accusing a rep is worse than missing a line, so errors stay silent.
- Every alert cites one specific clause, and each clause can fire at most once every 20 seconds.

HOW IT USES ASSEMBLYAI
It opens two AssemblyAI connections, and each has one job. Streaming STT v3 transcribes the whole call and has no reply behavior. The Voice Agent API is opened only when there is something to say. We started with a single Voice Agent session that both listened and spoke. Tested live, it started replying over the rep on its own, even with an explicit instruction to stay silent. Splitting the roles removes that failure by design (see docs/adr/0001-voice-architecture.md). We also tried injecting the alert as a conversation message. The agent ignored it. Only the direct "say exactly" instruction gave a word-for-word spoken match. We use the Voice Agent as a speaker on purpose: its own LLM never picks the words, because on a sales call a paraphrased contract is a new promise.

MEASURED, NOT PROJECTED
Live end-to-end runs on 2026-09-15 and 2026-09-17, with real AssemblyAI and Gemini connections and scripted rep lines fed into the pipeline. The logs are committed in the repo under docs/evidence/, so every number here is checkable:
- Two false claims caught: a fake automatic discount (contract §3.1) and a fake 24/7 support promise (§6.1). Consistent lines raised no alerts.
- Alert 4 to 6.5 seconds after the sentence ended, across five logged alerts: 4.0 s, 4.3 s, 5.6 s, 6.2 s and 6.49 s. The Voice Agent's own transcript of its reply matched the contract text exactly (similarity 1.0), which is the server's post-speech check. Alert to first spoken word: 375 ms.
- A clause request for §4.2, picked from the cockpit rail, was read back correctly by voice.
- About $0.08 to $0.15 per call by the app's own cost estimate ($0.0755 for 55 s, $0.1535 for 1:52). That estimate prices AssemblyAI by connection time at list rate and does not meter Gemini, so it is an estimate rather than a bill.
- Claim-check accuracy, measured 2026-09-18 on 32 labelled sentences against the demo contract: 14 of 14 contradictions caught, 0 false alarms, correct clause ID on every one, median 3.5 s. The sentences were written against this contract, so it measures the checker on its own fixture - the number that carries is the zero false alarms, because every failure path resolves to "unclear" by design.
- One verdict and one clause ID per finalized sentence, by design, so a spoken alert always cites exactly one clause. A sentence that breaks two clauses at once flags one of them; multi-clause fan-out is a known gap.
- 151 backend tests and 42 frontend tests pass.
The browser-microphone path is verified end to end: an automated run on 2026-09-17 drove a real browser through getUserMedia, an AudioWorklet and 16 kHz PCM16 frames and passed all 17 of its live-path checks. The capture device was Chromium's fake audio device playing a WAV file, not physical microphone hardware. Every figure here comes from a single run, not an average.

The hosted instance at https://clausecatcher.onrender.com was deployed and driven end to end on 2026-09-20: a contradiction was flagged in 4.7 s on the live app. The figures above were measured on local runs, not on the hosted instance.

A note for anyone opening the link: it runs on Render's free tier, so the first request after an idle period takes about a minute to wake. No microphone is needed - click "Use the demo contract", start the call, and type a line into "Simulate rep line"; it runs the identical pipeline.

WHO IT'S FOR
Sales-ops and revenue-compliance teams at B2B companies whose reps quote pricing, renewal, data-retention or SLA terms on live calls. The first buyer is whoever owns contract risk today and learns about a bad promise only after the customer brings it up.

Most call-review tools analyze recordings after the call ends. ClauseCatcher differs in two ways: it acts during the call, and it checks the rep against this customer's signed contract, not a generic sales script. Business-model hypothesis (not yet validated with buyers): a per-rep monthly subscription sold to sales-ops. API cost is small next to that; measured demo calls used $0.08 to $0.15 each.

WHAT'S NEXT
A hardened browser-mic path, CRM and meeting-platform integration (for example Zoom or Google Meet audio), multi-contract accounts, and a per-seat pricing pilot with a sales team.
```

Word count: about 945. Keep the section headings in caps; lablab's editor may strip Markdown.

### Technology & category tags

Pick from lablab's tag picker. If a tag doesn't exist there, skip it. Don't invent tags. In priority order:

- Technology: `AssemblyAI`, `Gemini`, `FastAPI`, `Python`, `React`, `TypeScript`
- Category: `Voice AI` / `Voice Agents`, `Speech-to-Text`, `Sales`, `Compliance`, `Legal`, `Productivity`

---

## 2. Cover image and presentation

### Cover image

Upload `docs/submission/cover.png`: 1920 x 1080 PNG (16:9), about 0.6 MB. Source: `docs/submission/cover.html`. The official guide says "PNG or JPG" and "Recommended 16:9". It gives no pixel size.

### Video presentation

```
https://vimeo.com/1228498903
```

Rules from the guide: "A maximum 5-minute video in MP4 format. Begin with an introduction, discuss your PDF presentation, then showcase your project's functionalities." Keep the MP4 export at or under 5:00. Script: `docs/submission/DEMO_SCRIPT.md`. If the form wants an upload instead of a link, upload the same MP4.

### Slide presentation

Upload `docs/submission/ClauseCatcher.pdf` (the guide asks for PDF). Outline and speaker notes: `docs/submission/SLIDES.md`. Re-exported 2026-09-20 from `ClauseCatcher.pptx` after `tools/fix_deck.py` corrected the numbers the deck still carried from before `TRUTH_AUDIT.md` (slide 4 and 9 `~2 s`, slide 9 `~78 ms` and the similarity caption, `~$0.12` on 9 and 10) and updated the test count to 151.

---

## 3. App hosting and repository

### Public GitHub repository

```
https://github.com/ishal1410/clausecatcher
```

### Demo application platform

```
Render
```

(The guide suggests Streamlit, Replit or Vercel. It doesn't require them. The app is a FastAPI + WebSocket server serving the built React UI from one Docker image, so it runs on Render's free Docker web service. See `docs/DEPLOY.md`. If the form only offers those three, pick "Other" if it's there. Don't pick a platform the app isn't actually hosted on.)

### Application URL

```
https://clausecatcher.onrender.com
```

Render's free tier sleeps when idle. Open the URL about 1 minute before submitting, and again during judging, so the first judge doesn't hit a cold start.
